"""Unit tests for SolutionFillCheckHandler.

Outcomes:
1. Tank full + targets reached → solution_fill_stop_to_ready
2. Tank full + targets not reached → enter_correction
3. Deadline exceeded → solution_fill_timeout_stop
4. Still filling → poll
5. Level unavailable/stale → TaskExecutionError
6. IRR state mismatch → TaskExecutionError
7. PH/EC unavailable → TaskExecutionError
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=1)

_RUNTIME = {
    "solution_max_sensor_labels": ["sol_max"],
    "solution_min_sensor_labels": ["sol_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "irr_state_max_age_sec": 60,
    "irr_state_wait_timeout_sec": 0.0,
    "irr_state_wait_poll_interval_sec": 0.05,
    "level_poll_interval_sec": 10,
    "target_ph": 5.8,
    "target_ec": 1.4,
    "prepare_tolerance": {"ph_pct": 15, "ec_pct": 25},
    "correction": {
        "max_ec_correction_attempts": 4,
        "max_ph_correction_attempts": 3,
        "stabilization_sec": 90,
    },
}

_GOOD_IRR = {
    "has_snapshot": True,
    "is_stale": False,
    "snapshot": {"valve_clean_supply": True, "valve_solution_fill": True, "pump_main": True},
}


def _make_task(*, deadline: datetime = FUTURE) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 2, "zone_id": 20, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "solution_fill_check", "workflow_phase": "solution_fill",
        "stage_deadline_at": deadline, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 1, "corr_step": None,
    })


class _Monitor:
    def __init__(
        self,
        *,
        max_triggered: bool = False,
        min_triggered: bool = True,
        has_level: bool = True,
        level_stale: bool = False,
        ph: float = 5.8,
        ec: float = 1.4,
        has_ph: bool = True,
        has_ec: bool = True,
        irr_state: dict | None = None,
    ) -> None:
        self._level_call = 0
        self._max_triggered = max_triggered
        self._min_triggered = min_triggered
        self._has_level = has_level
        self._level_stale = level_stale
        self._ph = {"has_value": has_ph, "is_stale": False, "value": ph}
        self._ec = {"has_value": has_ec, "is_stale": False, "value": ec}
        self._irr = irr_state if irr_state is not None else _GOOD_IRR

    async def read_level_switch(self, *, sensor_labels: Any, **_kw: Any) -> dict:
        self._level_call += 1
        triggered = self._max_triggered if self._level_call <= 1 else self._min_triggered
        return {"has_level": self._has_level, "is_stale": self._level_stale, "is_triggered": triggered}

    async def read_latest_irr_state(self, **_kw: Any) -> dict:
        return self._irr

    async def read_metric(self, *, sensor_type: str, **_kw: Any) -> dict:
        return self._ph if sensor_type == "PH" else self._ec


class _Gateway:
    async def run_batch(self, **_kw: Any) -> dict:
        return {"success": True, "error_code": None, "error_message": None}


class _Plan:
    def __init__(self, runtime: dict | None = None) -> None:
        self.runtime = runtime or _RUNTIME
        self.named_plans = {"irr_state_probe": ("probe_cmd",)}


class _StageDef:
    on_corr_success = "solution_fill_stop_to_ready"
    on_corr_fail = "solution_fill_stop_to_prepare"


def _handler(monitor: _Monitor | None = None) -> SolutionFillCheckHandler:
    return SolutionFillCheckHandler(
        runtime_monitor=monitor or _Monitor(),
        command_gateway=_Gateway(),
    )


# ── 1. Tank full + targets reached ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tank_full_targets_reached_stops_to_ready() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True, ph=5.8, ec=1.4)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_stop_to_ready"


@pytest.mark.asyncio
async def test_tank_full_targets_within_tolerance() -> None:
    # ph_tol=15% of 5.8 = 0.87 → [4.93, 6.67]; ec_tol=25% of 1.4 = 0.35 → [1.05, 1.75]
    m = _Monitor(max_triggered=True, min_triggered=True, ph=6.5, ec=1.7)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert outcome.next_stage == "solution_fill_stop_to_ready"


# ── 2. Tank full + targets not reached → enter_correction ────────────────────

@pytest.mark.asyncio
async def test_tank_full_targets_not_reached_enters_correction() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True, ph=4.0, ec=0.5)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"  # sensors already active
    assert outcome.correction.return_stage_success == "solution_fill_stop_to_ready"
    assert outcome.correction.return_stage_fail == "solution_fill_stop_to_prepare"


@pytest.mark.asyncio
async def test_correction_state_uses_correction_config() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True, ph=4.0)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    corr = outcome.correction
    assert corr.ec_max_attempts == 4
    assert corr.ph_max_attempts == 3
    assert corr.max_attempts == 4  # max(4, 3)
    assert corr.stabilization_sec == 90


@pytest.mark.asyncio
async def test_correction_uses_stage_def_on_corr_fail() -> None:
    class _CustomStageDef:
        on_corr_success = "custom_success"
        on_corr_fail = "custom_fail"

    m = _Monitor(max_triggered=True, min_triggered=True, ph=4.0)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_CustomStageDef(), now=NOW)
    assert outcome.correction.return_stage_success == "custom_success"
    assert outcome.correction.return_stage_fail == "custom_fail"


# ── 3. Deadline exceeded → timeout_stop ──────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_exceeded_transitions_to_timeout() -> None:
    outcome = await _handler().run(task=_make_task(deadline=PAST), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_timeout_stop"


# ── 4. Still filling → poll ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_still_filling_returns_poll() -> None:
    outcome = await _handler().run(task=_make_task(deadline=FUTURE), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10


# ── 5. Level unavailable/stale ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_level_unavailable_raises() -> None:
    m = _Monitor(has_level=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "two_tank_solution_level_unavailable"


@pytest.mark.asyncio
async def test_level_stale_raises() -> None:
    m = _Monitor(level_stale=True)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "two_tank_solution_level_stale"


# ── 6. Sensor inconsistency (max=1, min=0) ────────────────────────────────────

@pytest.mark.asyncio
async def test_sensor_inconsistency_raises() -> None:
    m = _Monitor(max_triggered=True, min_triggered=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"


# ── 7. PH/EC unavailable ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ph_unavailable_raises() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True, has_ph=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "two_tank_prepare_targets_unavailable"


@pytest.mark.asyncio
async def test_ec_unavailable_raises() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True, has_ec=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "two_tank_prepare_targets_unavailable"
