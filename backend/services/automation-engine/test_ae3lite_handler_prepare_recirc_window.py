"""Unit tests for PrepareRecircWindowHandler.

Outcomes:
1. retry_count >= attempt_limit → fail (attempt_limit_reached)
2. retry_count < attempt_limit → transition (retry_count increments), run commands
3. Commands (stop phase) fail → TaskExecutionError
4. Commands (start phase) fail → TaskExecutionError
5. Alert emitted when limit reached (if repository provided)
6. Alert NOT emitted when repository=None
7. attempt_limit from correction_config.prepare_recirculation_max_attempts
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)

_CMD = object()  # placeholder command

_RUNTIME = {
    "correction": {"prepare_recirculation_max_attempts": 3},
}


def _make_task(*, retry_count: int = 0) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 6, "zone_id": 60, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "prepare_recirculation_window_exhausted",
        "workflow_phase": "tank_recirc",
        "stage_deadline_at": None, "stage_retry_count": retry_count,
        "stage_entered_at": NOW, "clean_fill_cycle": 1, "corr_step": None,
    })


class _Gateway:
    def __init__(self, *, fail_on_call: int | None = None, error_code: str = "command_send_failed") -> None:
        self._fail_on_call = fail_on_call
        self._error_code = error_code
        self.call_count = 0

    async def run_batch(self, **_kw: Any) -> dict:
        self.call_count += 1
        if self._fail_on_call is not None and self.call_count == self._fail_on_call:
            return {"success": False, "error_code": self._error_code, "error_message": "fail"}
        return {"success": True, "error_code": None, "error_message": None}


class _Plan:
    def __init__(self, *, attempt_limit: int = 3) -> None:
        self.runtime = {"correction": {"prepare_recirculation_max_attempts": attempt_limit}}
        self.named_plans = {
            "prepare_recirculation_stop": (_CMD,),
            "sensor_mode_deactivate": (_CMD,),
            "sensor_mode_activate": (_CMD,),
            "prepare_recirculation_start": (_CMD,),
        }


class _AlertRepository:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def raise_active(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _handler(
    gateway: _Gateway | None = None,
    alert_repo: Any | None = None,
) -> PrepareRecircWindowHandler:
    return PrepareRecircWindowHandler(
        runtime_monitor=None,  # type: ignore[arg-type]
        command_gateway=gateway or _Gateway(),
        alert_repository=alert_repo,
    )


# ── 1. retry_count >= attempt_limit → fail ────────────────────────────────────

@pytest.mark.asyncio
async def test_limit_reached_returns_fail() -> None:
    outcome = await _handler().run(
        task=_make_task(retry_count=3),
        plan=_Plan(attempt_limit=3),
        stage_def=None, now=NOW,
    )
    assert outcome.kind == "fail"
    assert outcome.error_code == "prepare_recirculation_attempt_limit_reached"


@pytest.mark.asyncio
async def test_limit_exceeded_also_returns_fail() -> None:
    outcome = await _handler().run(
        task=_make_task(retry_count=5),
        plan=_Plan(attempt_limit=3),
        stage_def=None, now=NOW,
    )
    assert outcome.kind == "fail"


# ── 2. retry_count < attempt_limit → rollover ────────────────────────────────

@pytest.mark.asyncio
async def test_below_limit_transitions_to_check() -> None:
    outcome = await _handler().run(
        task=_make_task(retry_count=1),
        plan=_Plan(attempt_limit=3),
        stage_def=None, now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_check"
    assert outcome.stage_retry_count == 2


@pytest.mark.asyncio
async def test_rollover_increments_exhausted_window_count() -> None:
    for initial in (1, 2):
        outcome = await _handler().run(
            task=_make_task(retry_count=initial),
            plan=_Plan(attempt_limit=3),
            stage_def=None, now=NOW,
        )
        assert outcome.stage_retry_count == initial + 1


# ── 3. Stop-phase command failure → TaskExecutionError ───────────────────────

@pytest.mark.asyncio
async def test_stop_commands_failure_raises() -> None:
    gw = _Gateway(fail_on_call=1, error_code="command_send_failed")
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(gw).run(
            task=_make_task(retry_count=0),
            plan=_Plan(), stage_def=None, now=NOW,
        )
    assert exc_info.value.code == "command_send_failed"


# ── 4. Start-phase command failure → TaskExecutionError ──────────────────────

@pytest.mark.asyncio
async def test_start_commands_failure_raises() -> None:
    gw = _Gateway(fail_on_call=2, error_code="command_send_failed")
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(gw).run(
            task=_make_task(retry_count=0),
            plan=_Plan(), stage_def=None, now=NOW,
        )
    assert exc_info.value.code == "command_send_failed"


# ── 5. Alert emitted when limit reached ──────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_emitted_on_limit_reached() -> None:
    alert_repo = _AlertRepository()
    await _handler(alert_repo=alert_repo).run(
        task=_make_task(retry_count=3),
        plan=_Plan(attempt_limit=3),
        stage_def=None, now=NOW,
    )
    assert len(alert_repo.calls) == 1
    call = alert_repo.calls[0]
    assert call["zone_id"] == 60
    assert call["code"] == "biz_prepare_recirculation_retry_exhausted"


# ── 6. No alert when repository=None ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_alert_without_repository() -> None:
    # Should not raise even without alert_repository
    outcome = await _handler(alert_repo=None).run(
        task=_make_task(retry_count=3),
        plan=_Plan(attempt_limit=3),
        stage_def=None, now=NOW,
    )
    assert outcome.kind == "fail"


# ── 7. attempt_limit from correction_config ───────────────────────────────────

@pytest.mark.asyncio
async def test_custom_attempt_limit_respected() -> None:
    # attempt_limit=1 → retry_count=1 is already at limit → fail
    outcome = await _handler().run(
        task=_make_task(retry_count=1),
        plan=_Plan(attempt_limit=1),
        stage_def=None, now=NOW,
    )
    assert outcome.kind == "fail"

    # attempt_limit=5 → retry_count=1 is below limit → rollover
    outcome2 = await _handler().run(
        task=_make_task(retry_count=1),
        plan=_Plan(attempt_limit=5),
        stage_def=None, now=NOW,
    )
    assert outcome2.kind == "transition"


# ── empty command plan ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_named_plans_raises() -> None:
    """If no commands are in named_plans, handler should raise ae3_empty_command_plan."""
    class _EmptyPlan:
        runtime = {"correction": {"prepare_recirculation_max_attempts": 3}}
        named_plans: dict = {}

    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler().run(
            task=_make_task(retry_count=0),
            plan=_EmptyPlan(),
            stage_def=None, now=NOW,
        )
    assert exc_info.value.code == "ae3_empty_command_plan"
