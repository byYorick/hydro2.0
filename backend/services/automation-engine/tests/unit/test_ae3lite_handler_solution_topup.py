from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.solution_topup import SolutionTopupCheckHandler, SolutionTopupGuardHandler
from ae3lite.config.schema import RuntimePlan


def _task(*, stage: str = "solution_topup_check", deadline: datetime | None = None) -> SimpleNamespace:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return SimpleNamespace(
        id=11,
        zone_id=5,
        topology="two_tank",
        workflow=SimpleNamespace(
            stage_deadline_at=deadline,
            stage_entered_at=now - timedelta(seconds=120),
            stage_retry_count=0,
            pending_manual_step="",
            control_mode="auto",
        ),
        intent_meta={"intent_payload": {"mode": "normal"}},
        workflow_phase="ready",
        current_stage=stage,
    )


def _plan(runtime: RuntimePlan | None = None) -> SimpleNamespace:
    return SimpleNamespace(runtime=runtime or make_runtime_plan())


@pytest.mark.asyncio
async def test_guard_transitions_to_start_when_need_topup() -> None:
    handler = SolutionTopupGuardHandler(
        runtime_monitor=AsyncMock(),
        command_gateway=AsyncMock(),
    )
    handler._read_level = AsyncMock(side_effect=[
        {"is_triggered": True},
        {"is_triggered": False},
    ])
    handler._cooldown_active = AsyncMock(return_value=False)

    outcome = await handler.run(
        task=_task(stage="solution_topup_guard"),
        plan=_plan(),
        stage_def=SimpleNamespace(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_topup_start"


@pytest.mark.asyncio
async def test_guard_skips_when_tank_already_full() -> None:
    handler = SolutionTopupGuardHandler(
        runtime_monitor=AsyncMock(),
        command_gateway=AsyncMock(),
    )
    handler._read_level = AsyncMock(side_effect=[
        {"is_triggered": True},
        {"is_triggered": True},
    ])

    outcome = await handler.run(
        task=_task(stage="solution_topup_guard"),
        plan=_plan(),
        stage_def=SimpleNamespace(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_topup_complete"


@pytest.mark.asyncio
async def test_check_transitions_to_stop_when_solution_max_triggered() -> None:
    handler = SolutionTopupCheckHandler(
        runtime_monitor=AsyncMock(),
        command_gateway=AsyncMock(),
    )
    handler._read_recent_storage_event = AsyncMock(return_value=None)
    handler._probe_irr_state = AsyncMock()
    handler._read_level = AsyncMock(return_value={"is_triggered": True})
    handler._check_sensor_consistency = AsyncMock()

    outcome = await handler.run(
        task=_task(),
        plan=_plan(),
        stage_def=SimpleNamespace(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_topup_stop"


@pytest.mark.asyncio
async def test_check_timeout_transitions_to_timeout_stop() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    handler = SolutionTopupCheckHandler(
        runtime_monitor=AsyncMock(),
        command_gateway=AsyncMock(),
    )
    handler._read_recent_storage_event = AsyncMock(return_value=None)
    handler._probe_irr_state = AsyncMock()
    handler._read_level = AsyncMock(side_effect=[
        {"is_triggered": True},
        {"is_triggered": True},
        {"is_triggered": False},
    ])
    handler._stage_elapsed_ms = lambda **_kw: 999_999

    outcome = await handler.run(
        task=_task(deadline=now - timedelta(seconds=5)),
        plan=_plan(),
        stage_def=SimpleNamespace(),
        now=now,
    )

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_topup_timeout_stop"
