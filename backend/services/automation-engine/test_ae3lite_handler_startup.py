"""Unit tests for StartupHandler.

Outcomes:
1. IRR OK + clean tank full → solution_fill_start (skip clean fill)
2. IRR OK + clean tank not full → clean_fill_start (cycle=1)
3. IRR state unavailable/stale → safe fallback → clean_fill_start
4. IRR mismatch (pump_main=True) → run safety stop → re-check → clean_fill_start
5. IRR mismatch (pump_main=True) → safety stop fails → TaskExecutionError
6. IRR mismatch (pump_main=True) + no safety plan → TaskExecutionError
7. Level unavailable → TaskExecutionError
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)

_RUNTIME = {
    "clean_max_sensor_labels": ["clean_max"],
    "clean_min_sensor_labels": ["clean_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "irr_state_max_age_sec": 60,
    "irr_state_wait_timeout_sec": 0.0,
    "irr_state_wait_poll_interval_sec": 0.05,
    "level_poll_interval_sec": 5,
}


def _make_task(
    *,
    control_mode: str = "auto",
    pending_manual_step: str | None = None,
) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 3, "zone_id": 30, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "startup",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 0,
        "control_mode_snapshot": control_mode,
        "pending_manual_step": pending_manual_step,
        "corr_step": None,
    })


class _Monitor:
    def __init__(
        self,
        *,
        irr_states: list[dict] | None = None,
        clean_max_triggered: bool = False,
        clean_min_triggered: bool = True,
        has_level: bool = True,
    ) -> None:
        # irr_states is a list consumed sequentially (for multi-probe scenarios)
        self._irr_states = irr_states or [
            {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": False}}
        ]
        self._irr_call = 0
        self._level_call = 0
        self._clean_max_triggered = clean_max_triggered
        self._clean_min_triggered = clean_min_triggered
        self._has_level = has_level

    async def read_latest_irr_state(self, **_kw: Any) -> dict:
        idx = min(self._irr_call, len(self._irr_states) - 1)
        self._irr_call += 1
        return self._irr_states[idx]

    async def read_level_switch(self, **_kw: Any) -> dict:
        self._level_call += 1
        triggered = self._clean_max_triggered if self._level_call <= 1 else self._clean_min_triggered
        return {"has_level": self._has_level, "is_stale": False, "is_triggered": triggered}

    async def read_metric(self, **_kw: Any) -> dict:
        return {"has_value": True, "is_stale": False, "value": 6.0}


class _Gateway:
    def __init__(self, *, success: bool = True, error_code: str = "") -> None:
        self._success = success
        self._error_code = error_code
        self.call_count = 0

    async def run_batch(self, **_kw: Any) -> dict:
        self.call_count += 1
        return {
            "success": self._success,
            "error_code": self._error_code if not self._success else None,
            "error_message": "fail" if not self._success else None,
        }


class _Plan:
    def __init__(
        self,
        *,
        runtime: dict | None = None,
        has_safety_plan: bool = True,
    ) -> None:
        self.runtime = runtime or _RUNTIME
        self.named_plans: dict = {
            "irr_state_probe": ("probe_cmd",),
        }
        if has_safety_plan:
            self.named_plans["solution_fill_stop"] = ("stop_cmd",)


def _handler(monitor: _Monitor | None = None, gateway: _Gateway | None = None) -> StartupHandler:
    return StartupHandler(
        runtime_monitor=monitor or _Monitor(),
        command_gateway=gateway or _Gateway(),
    )


# ── 1. IRR OK + clean tank full → skip to solution_fill ──────────────────────

@pytest.mark.asyncio
async def test_clean_tank_full_skips_to_solution_fill() -> None:
    m = _Monitor(clean_max_triggered=True, clean_min_triggered=True)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_start"


# ── 2. IRR OK + clean tank not full → clean_fill_start ───────────────────────

@pytest.mark.asyncio
async def test_clean_tank_not_full_starts_clean_fill() -> None:
    m = _Monitor(clean_max_triggered=False)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_start"
    assert outcome.clean_fill_cycle == 1


@pytest.mark.asyncio
async def test_manual_startup_without_pending_step_polls() -> None:
    m = _Monitor(clean_max_triggered=False)
    outcome = await _handler(m).run(
        task=_make_task(control_mode="manual"),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 5


@pytest.mark.asyncio
async def test_manual_startup_with_pending_clean_fill_start_transitions() -> None:
    m = _Monitor(clean_max_triggered=False)
    outcome = await _handler(m).run(
        task=_make_task(control_mode="manual", pending_manual_step="clean_fill_start"),
        plan=_Plan(),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_start"


# ── 3. IRR state unavailable/stale → fail-closed ─────────────────────────────

@pytest.mark.asyncio
async def test_irr_state_unavailable_raises() -> None:
    m = _Monitor(irr_states=[{"has_snapshot": False, "is_stale": False, "snapshot": None}])
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "irr_state_unavailable"


@pytest.mark.asyncio
async def test_irr_state_stale_raises() -> None:
    m = _Monitor(irr_states=[{"has_snapshot": True, "is_stale": True, "snapshot": None}])
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "irr_state_stale"


@pytest.mark.asyncio
async def test_irr_state_stale_emits_probe_failure_event(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _Monitor(irr_states=[{"has_snapshot": True, "is_stale": True, "snapshot": None}])
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.base.create_zone_event", create_event)

    with pytest.raises(TaskExecutionError):
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)

    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "IRR_STATE_PROBE_FAILED"
    payload = create_event.await_args.args[2]
    assert payload["reason"] == "stale"
    assert payload["stage"] == "startup"


# ── 4. IRR mismatch (pump_main on) → safety stop → re-check → proceed ────────

@pytest.mark.asyncio
async def test_pump_main_on_triggers_safety_stop() -> None:
    # First probe: pump on (mismatch). After safety stop: pump off (ok).
    pump_on = {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": True}}
    pump_off = {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": False}}
    m = _Monitor(irr_states=[pump_on, pump_off])
    gw = _Gateway(success=True)
    outcome = await _handler(m, gw).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert gw.call_count >= 1  # safety stop was called
    assert outcome.next_stage in ("clean_fill_start", "solution_fill_start")


# ── 5. Safety stop fails → TaskExecutionError ────────────────────────────────

@pytest.mark.asyncio
async def test_safety_stop_failure_raises() -> None:
    pump_on = {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": True}}
    m = _Monitor(irr_states=[pump_on, pump_on])
    gw = _Gateway(success=False, error_code="command_send_failed")
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m, gw).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "command_send_failed"


# ── 6. No safety plan configured → TaskExecutionError ────────────────────────

@pytest.mark.asyncio
async def test_no_safety_plan_raises_on_pump_mismatch() -> None:
    pump_on = {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": True}}
    m = _Monitor(irr_states=[pump_on])
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(has_safety_plan=False), stage_def=None, now=NOW)
    assert exc_info.value.code == "irr_state_mismatch"


# ── 7. Level unavailable ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_level_unavailable_raises() -> None:
    m = _Monitor(has_level=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "two_tank_clean_level_unavailable"


# ── 8. Sensor inconsistency (max=1, min=0) ────────────────────────────────────

@pytest.mark.asyncio
async def test_sensor_inconsistency_raises() -> None:
    """Clean max triggered but min not triggered → sensor_state_inconsistent."""
    m = _Monitor(clean_max_triggered=True, clean_min_triggered=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"


# ── 9. Probe command fails → TaskExecutionError ───────────────────────────────

@pytest.mark.asyncio
async def test_probe_command_failure_raises() -> None:
    """Probe gateway fails (pump_main=False path) → TaskExecutionError propagated."""
    m = _Monitor()  # default: pump_main=False (no mismatch)
    gw = _Gateway(success=False, error_code="fail")
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m, gw).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "fail"
