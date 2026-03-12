"""Unit tests for CommandHandler.

Outcomes:
1. Batch succeeds + next_stage set → transition
2. Batch succeeds + terminal_error set → fail
3. Batch succeeds + neither next_stage nor terminal_error → TaskExecutionError (ae3_command_no_routing)
4. Batch fails → TaskExecutionError with gateway error_code
5. No commands resolved → TaskExecutionError (ae3_empty_command_plan)
6. Multiple command_plans merged into one batch
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ae3lite.application.handlers.command import CommandHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)

_CMD_A = PlannedCommand(step_no=1, node_uid="n1", channel="ch1", payload={"cmd": "set_relay", "params": {"state": True}})
_CMD_B = PlannedCommand(step_no=2, node_uid="n2", channel="ch2", payload={"cmd": "set_relay", "params": {"state": False}})


def _make_task() -> AutomationTask:
    return AutomationTask.from_row({
        "id": 4, "zone_id": 40, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "clean_fill_start", "workflow_phase": "clean_fill",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 1, "corr_step": None,
    })


class _Gateway:
    def __init__(self, *, success: bool = True, error_code: str = "test_error") -> None:
        self._success = success
        self._error_code = error_code
        self.received_commands: tuple = ()

    async def run_batch(self, *, commands: Any, **_kw: Any) -> dict:
        self.received_commands = commands
        return {
            "success": self._success,
            "error_code": self._error_code if not self._success else None,
            "error_message": "failure" if not self._success else None,
            "commands_total": len(commands),
        }


class _StageDef:
    def __init__(
        self,
        *,
        name: str = "clean_fill_start",
        command_plans: list[str] | None = None,
        next_stage: str | None = "clean_fill_check",
        terminal_error: tuple[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command_plans = command_plans or ["clean_fill_start"]
        self.next_stage = next_stage
        self.terminal_error = terminal_error


class _Plan:
    def __init__(self, named_plans: dict | None = None) -> None:
        self.runtime: dict = {}
        self.named_plans = named_plans or {"clean_fill_start": (_CMD_A,)}


def _handler(gw: _Gateway | None = None) -> CommandHandler:
    return CommandHandler(
        runtime_monitor=None,  # type: ignore[arg-type]
        command_gateway=gw or _Gateway(),
    )


# ── 1. Batch succeeds + next_stage → transition ───────────────────────────────

@pytest.mark.asyncio
async def test_batch_success_with_next_stage_returns_transition() -> None:
    gw = _Gateway()
    outcome = await _handler(gw).run(
        task=_make_task(),
        plan=_Plan(),
        stage_def=_StageDef(next_stage="clean_fill_check"),
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_check"


# ── 2. Batch succeeds + terminal_error → fail ────────────────────────────────

@pytest.mark.asyncio
async def test_batch_success_with_terminal_error_returns_fail() -> None:
    outcome = await _handler().run(
        task=_make_task(),
        plan=_Plan(),
        stage_def=_StageDef(
            next_stage=None,
            terminal_error=("ae3_stage_failed", "Stop intentional"),
        ),
        now=NOW,
    )
    assert outcome.kind == "fail"
    assert outcome.error_code == "ae3_stage_failed"
    assert outcome.error_message == "Stop intentional"


# ── 3. No routing → TaskExecutionError ───────────────────────────────────────

@pytest.mark.asyncio
async def test_no_routing_raises() -> None:
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler().run(
            task=_make_task(),
            plan=_Plan(),
            stage_def=_StageDef(next_stage=None, terminal_error=None),
            now=NOW,
        )
    assert exc_info.value.code == "ae3_command_no_routing"


# ── 4. Batch fails → TaskExecutionError ──────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_failure_raises_with_gateway_error_code() -> None:
    gw = _Gateway(success=False, error_code="command_send_failed")
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(gw).run(
            task=_make_task(),
            plan=_Plan(),
            stage_def=_StageDef(),
            now=NOW,
        )
    assert exc_info.value.code == "command_send_failed"


# ── 5. No commands resolved → TaskExecutionError ─────────────────────────────

@pytest.mark.asyncio
async def test_empty_command_plan_raises() -> None:
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler().run(
            task=_make_task(),
            plan=_Plan(named_plans={}),  # no commands in plan
            stage_def=_StageDef(command_plans=["nonexistent_plan"]),
            now=NOW,
        )
    assert exc_info.value.code == "ae3_empty_command_plan"


# ── 6. Multiple command_plans merged ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_plans_merged_into_one_batch() -> None:
    gw = _Gateway()
    await _handler(gw).run(
        task=_make_task(),
        plan=_Plan(named_plans={"plan_a": (_CMD_A,), "plan_b": (_CMD_B,)}),
        stage_def=_StageDef(command_plans=["plan_a", "plan_b"]),
        now=NOW,
    )
    assert len(gw.received_commands) == 2


@pytest.mark.asyncio
async def test_missing_plan_name_contributes_zero_commands() -> None:
    """Plan names that don't exist in named_plans are silently skipped."""
    gw = _Gateway()
    await _handler(gw).run(
        task=_make_task(),
        plan=_Plan(named_plans={"plan_a": (_CMD_A,)}),
        stage_def=_StageDef(command_plans=["plan_a", "missing_plan"]),
        now=NOW,
    )
    assert len(gw.received_commands) == 1
