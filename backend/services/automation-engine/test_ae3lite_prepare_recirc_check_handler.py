"""Unit tests for PrepareRecircCheckHandler.

Outcomes:
 1. Deadline exceeded → prepare_recirculation_window_exhausted (stage_retry_count++)
 2. Targets reached → prepare_recirculation_stop_to_ready
 3. Targets not reached → enter_correction
 4. Probe fails with non-stale error → re-raises TaskExecutionError
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=1)

RUNTIME = {
    "solution_max_sensor_labels": ["sol_max"],
    "solution_min_sensor_labels": ["sol_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "irr_state_max_age_sec": 60,
    "irr_state_wait_timeout_sec": 0.0,
    "irr_state_wait_poll_interval_sec": 0.05,
    "target_ph": 5.8,
    "target_ec": 1.4,
    "prepare_tolerance": {"ph_pct": 15, "ec_pct": 25},
    "correction": {
        "max_ec_correction_attempts": 3,
        "max_ph_correction_attempts": 3,
        "prepare_recirculation_max_correction_attempts": 20,
        "stabilization_sec": 60,
    },
}


def _make_task(*, deadline=FUTURE, retry_count=0):
    return AutomationTask.from_row({
        "id": 5, "zone_id": 50, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k5", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "prepare_recirculation_check",
        "workflow_phase": "tank_recirc",
        "stage_deadline_at": deadline, "stage_retry_count": retry_count,
        "stage_entered_at": NOW, "clean_fill_cycle": 1, "corr_step": None,
    })


class _Monitor:
    def __init__(self, *, ph=5.8, ec=1.4, has_ph=True, has_ec=True, irr_state=None):
        self._ph = {"has_value": has_ph, "is_stale": False, "value": ph}
        self._ec = {"has_value": has_ec, "is_stale": False, "value": ec}
        self._irr = irr_state or {
            "has_snapshot": True, "is_stale": False,
            "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True},
        }

    async def read_metric(self, *, zone_id, sensor_type, telemetry_max_age_sec):
        return self._ph if sensor_type == "PH" else self._ec

    async def read_latest_irr_state(self, **_kw):
        return self._irr

    async def read_level_switch(self, **_kw):
        return {"has_level": True, "is_stale": False, "is_triggered": True}


class _MockGateway:
    async def run_batch(self, *, task, commands, now):
        return {"success": True, "error_code": None, "error_message": None}


class _MockPlan:
    def __init__(self, runtime=None):
        self.runtime = runtime or RUNTIME
        self.named_plans = {
            "irr_state_probe": ("probe_cmd",),
        }


def _make_handler(monitor=None, gateway=None):
    return PrepareRecircCheckHandler(
        runtime_monitor=monitor or _Monitor(),
        command_gateway=gateway or _MockGateway(),
    )


class _StageDef:
    on_corr_success = "prepare_recirculation_stop_to_ready"
    on_corr_fail = "prepare_recirculation_window_exhausted"


# ── Deadline exceeded ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_exceeded_returns_window_exhausted():
    handler = _make_handler()
    task = _make_task(deadline=PAST, retry_count=2)
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3  # retry_count + 1


@pytest.mark.asyncio
async def test_deadline_exceeded_increments_retry_count():
    handler = _make_handler()
    for initial_retry in (0, 1, 5):
        task = _make_task(deadline=PAST, retry_count=initial_retry)
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
        assert outcome.stage_retry_count == initial_retry + 1


# ── Targets reached ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_targets_reached_transitions_to_stop_ready():
    # ph=5.8, ec=1.4 are exactly at target → within tolerance
    handler = _make_handler(monitor=_Monitor(ph=5.8, ec=1.4))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_targets_reached_within_tolerance():
    # target_ph=5.8, tol=15% → min=4.93, max=6.67
    handler = _make_handler(monitor=_Monitor(ph=6.0, ec=1.2))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


# ── Targets not reached → enter_correction ────────────────────────────────────

@pytest.mark.asyncio
async def test_targets_not_reached_enters_correction():
    # ph=4.0 is way below target 5.8 → not reached
    handler = _make_handler(monitor=_Monitor(ph=4.0, ec=1.4))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"  # sensors already active
    assert outcome.correction.return_stage_success == "prepare_recirculation_stop_to_ready"
    assert outcome.correction.return_stage_fail == "prepare_recirculation_window_exhausted"


@pytest.mark.asyncio
async def test_correction_state_uses_max_correction_attempts():
    handler = _make_handler(monitor=_Monitor(ph=4.0))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.correction.max_attempts == 20  # prepare_recirculation_max_correction_attempts


# ── Telemetry unavailable ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ph_unavailable_raises():
    handler = _make_handler(monitor=_Monitor(has_ph=False))
    with pytest.raises(TaskExecutionError, match="unavailable"):
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)


@pytest.mark.asyncio
async def test_ec_unavailable_raises():
    handler = _make_handler(monitor=_Monitor(has_ec=False))
    with pytest.raises(TaskExecutionError, match="unavailable"):
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)


# ── stage_def fallback ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_correction_uses_stage_def_on_corr_fail():
    class _CustomStageDef:
        on_corr_success = "custom_success"
        on_corr_fail = "custom_fail"

    handler = _make_handler(monitor=_Monitor(ph=4.0))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_CustomStageDef(), now=NOW)
    assert outcome.correction.return_stage_success == "custom_success"
    assert outcome.correction.return_stage_fail == "custom_fail"
