"""Unit tests for CommandHandler.

Covers:
 - Successful batch → transition to next_stage
 - Terminal error stage → fail outcome (after successful batch)
 - Batch failure → TaskExecutionError
 - No routing (no next_stage, no terminal_error) → TaskExecutionError
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.application.handlers.command import CommandHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import StageDef


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

_CMD = PlannedCommand(step_no=1, node_uid="node-1", channel="valve_a",
                      payload={"cmd": "set_relay", "params": {"state": True}})


def _make_task() -> AutomationTask:
    return AutomationTask.from_row({
        "id": 2, "zone_id": 20, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k2", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "clean_fill_start", "workflow_phase": "tank_filling",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": None, "clean_fill_cycle": 1,
        "corr_step": None,
    })


class _MockPlan:
    named_plans = {"clean_fill_start": (_CMD,)}
    runtime = {}
    targets = {}


class _MockGateway:
    def __init__(self, *, success: bool = True, error_code: str = "err"):
        self._success = success
        self._error_code = error_code

    async def run_batch(self, *, task, commands, now):
        return {
            "success": self._success,
            "error_code": self._error_code,
            "error_message": "batch failed",
        }


def _make_handler(*, gateway=None) -> CommandHandler:
    return CommandHandler(
        runtime_monitor=object(),  # not used by CommandHandler
        command_gateway=gateway or _MockGateway(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_command_handler_routes_to_next_stage():
    """run_batch succeeds + next_stage → transition outcome."""
    stage_def = StageDef(
        "clean_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
    )
    handler = _make_handler()
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=stage_def, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_check"


async def test_command_handler_terminal_error_fails():
    """run_batch succeeds + terminal_error → fail outcome with terminal error codes."""
    stage_def = StageDef(
        "clean_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        terminal_error=("clean_tank_not_filled_timeout", "Timeout exceeded"),
    )
    handler = _make_handler()
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=stage_def, now=NOW)

    assert outcome.kind == "fail"
    assert outcome.error_code == "clean_tank_not_filled_timeout"
    assert outcome.error_message == "Timeout exceeded"


async def test_command_handler_batch_failure_raises():
    """run_batch fails → TaskExecutionError propagated."""
    stage_def = StageDef(
        "clean_fill_start", "command",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
    )
    gateway = _MockGateway(success=False, error_code="hw_error")
    handler = _make_handler(gateway=gateway)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=stage_def, now=NOW)
    assert exc_info.value.code == "hw_error"


async def test_command_handler_no_routing_raises():
    """No next_stage and no terminal_error → ae3_command_no_routing error."""
    stage_def = StageDef("orphan_stage", "command", command_plans=("clean_fill_start",))
    handler = _make_handler()
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=stage_def, now=NOW)
    assert exc_info.value.code == "ae3_command_no_routing"
