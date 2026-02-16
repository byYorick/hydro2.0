"""Unit tests for application.executor_run helpers."""

import asyncio
from unittest.mock import AsyncMock, Mock

from domain.models.decision_models import DecisionOutcome
from application.executor_run import run_executor_execute_flow


def _decision(action_required: bool) -> DecisionOutcome:
    return DecisionOutcome(
        action_required=action_required,
        decision="run" if action_required else "skip",
        reason_code="ok",
        reason="ok",
    )


def test_run_executor_execute_flow_runs_no_action_branch():
    result = asyncio.run(
        run_executor_execute_flow(
            zone_id=1,
            task_type="irrigation",
            payload={"x": 1},
            task_context={"task_id": "st-1"},
            prepare_execution_inputs_fn=lambda **_: ("irrigation", {"x": 1}, {"mapping": True}),
            build_task_context_fn=lambda _: {"task_id": "st-1"},
            log_execution_started_fn=Mock(),
            emit_execution_started_events_fn=AsyncMock(return_value=None),
            run_decision_phase_fn=AsyncMock(return_value=_decision(False)),
            execute_no_action_branch_fn=AsyncMock(return_value={"success": True, "mode": "no_action"}),
            execute_action_required_branch_fn=AsyncMock(return_value={"success": True, "mode": "action"}),
            apply_decision_defaults_fn=lambda **kwargs: kwargs["result"],
            finalize_execution_fn=AsyncMock(side_effect=lambda **kwargs: kwargs["result"]),
        )
    )
    assert result["mode"] == "no_action"


def test_run_executor_execute_flow_runs_action_branch():
    result = asyncio.run(
        run_executor_execute_flow(
            zone_id=1,
            task_type="irrigation",
            payload={"x": 1},
            task_context={"task_id": "st-1"},
            prepare_execution_inputs_fn=lambda **_: ("irrigation", {"x": 1}, {"mapping": True}),
            build_task_context_fn=lambda _: {"task_id": "st-1"},
            log_execution_started_fn=Mock(),
            emit_execution_started_events_fn=AsyncMock(return_value=None),
            run_decision_phase_fn=AsyncMock(return_value=_decision(True)),
            execute_no_action_branch_fn=AsyncMock(return_value={"success": True, "mode": "no_action"}),
            execute_action_required_branch_fn=AsyncMock(return_value={"success": True, "mode": "action"}),
            apply_decision_defaults_fn=lambda **kwargs: kwargs["result"],
            finalize_execution_fn=AsyncMock(side_effect=lambda **kwargs: kwargs["result"]),
        )
    )
    assert result["mode"] == "action"
