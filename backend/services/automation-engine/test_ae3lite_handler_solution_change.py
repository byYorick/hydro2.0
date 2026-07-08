from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.solution_change import SolutionChangeOperatorGateHandler
from ae3lite.application.use_cases.manual_control_contract import allowed_manual_steps_for_task


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
