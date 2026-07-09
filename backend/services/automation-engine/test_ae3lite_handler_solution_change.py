from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.solution_change import (
    SolutionChangeOperatorGateHandler,
    SolutionDrainCheckHandler,
)
from ae3lite.application.use_cases.manual_control_contract import allowed_manual_steps_for_task
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 14, 15, 30, 0, tzinfo=timezone.utc)


def _drain_plan() -> SimpleNamespace:
    return SimpleNamespace(
        runtime=make_runtime_plan(
            solution_min_sensor_labels=["level_solution_min"],
            level_poll_interval_sec=5,
            telemetry_max_age_sec=10,
        ),
        named_plans={"irr_state_probe": ("probe_cmd",)},
    )


def _drain_task(*, deadline: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=2,
        zone_id=10,
        task_type="solution_change",
        topology="two_tank",
        current_stage="solution_drain_check",
        workflow=SimpleNamespace(
            pending_manual_step="",
            stage_deadline_at=deadline,
        ),
    )


@pytest.mark.asyncio
async def test_operator_gate_transitions_on_drain_confirm() -> None:
    handler = SolutionChangeOperatorGateHandler(runtime_monitor=AsyncMock(), command_gateway=AsyncMock())
    task = SimpleNamespace(
        id=1,
        zone_id=10,
        task_type="solution_change",
        topology="two_tank",
        workflow=SimpleNamespace(
            pending_manual_step="solution_drain_confirm",
            stage_deadline_at=None,
        ),
    )
    plan = SimpleNamespace(runtime=SimpleNamespace(level_poll_interval_sec=5))
    stage_def = SimpleNamespace(name="await_operator_drain_confirm")

    handler._require_runtime_plan = lambda plan=plan: plan.runtime  # type: ignore[method-assign]
    handler._check_solution_change_abort = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._deadline_reached = lambda **kwargs: False  # type: ignore[method-assign]

    outcome = await handler.run(task=task, plan=plan, stage_def=stage_def, now=datetime.now(timezone.utc).replace(tzinfo=None))

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_drain_start"


def test_allowed_manual_steps_for_solution_change_gate_in_auto_mode() -> None:
    steps = allowed_manual_steps_for_task(
        task_type="solution_change",
        control_mode="auto",
        current_stage="await_operator_drain_confirm",
        pending_manual_step=None,
    )
    assert "solution_drain_confirm" in steps
    assert "solution_change_abort" in steps


@pytest.mark.asyncio
async def test_solution_drain_check_probe_unavailable_raises() -> None:
    handler = SolutionDrainCheckHandler(runtime_monitor=AsyncMock(), command_gateway=AsyncMock())
    task = _drain_task()
    plan = _drain_plan()
    handler._check_solution_change_abort = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._probe_irr_state = AsyncMock(  # type: ignore[method-assign]
        side_effect=TaskExecutionError("irr_state_unavailable", "snapshot missing"),
    )

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=plan, stage_def=None, now=NOW)

    assert exc_info.value.code == "irr_state_unavailable"


@pytest.mark.asyncio
async def test_solution_drain_check_probe_mismatch_with_empty_tank_transitions() -> None:
    handler = SolutionDrainCheckHandler(runtime_monitor=AsyncMock(), command_gateway=AsyncMock())
    task = _drain_task()
    plan = _drain_plan()
    handler._check_solution_change_abort = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._probe_irr_state = AsyncMock(  # type: ignore[method-assign]
        side_effect=TaskExecutionError("irr_state_mismatch", "valve_drain off"),
    )
    handler._read_level = AsyncMock(return_value={"is_triggered": False})  # type: ignore[method-assign]

    outcome = await handler.run(task=task, plan=plan, stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_drain_stop_to_clean_fill"
    handler._read_level.assert_awaited_once()


@pytest.mark.asyncio
async def test_solution_drain_check_probe_mismatch_with_solution_remaining_raises() -> None:
    handler = SolutionDrainCheckHandler(runtime_monitor=AsyncMock(), command_gateway=AsyncMock())
    task = _drain_task()
    plan = _drain_plan()
    handler._check_solution_change_abort = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._probe_irr_state = AsyncMock(  # type: ignore[method-assign]
        side_effect=TaskExecutionError("irr_state_mismatch", "valve_drain off"),
    )
    handler._read_level = AsyncMock(return_value={"is_triggered": True})  # type: ignore[method-assign]

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=plan, stage_def=None, now=NOW)

    assert exc_info.value.code == "irr_state_mismatch"


@pytest.mark.asyncio
async def test_solution_drain_check_empty_tank_transitions_after_successful_probe() -> None:
    handler = SolutionDrainCheckHandler(runtime_monitor=AsyncMock(), command_gateway=AsyncMock())
    task = _drain_task()
    plan = _drain_plan()
    handler._check_solution_change_abort = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._probe_irr_state = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._read_level = AsyncMock(return_value={"is_triggered": False})  # type: ignore[method-assign]

    outcome = await handler.run(task=task, plan=plan, stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_drain_stop_to_clean_fill"
