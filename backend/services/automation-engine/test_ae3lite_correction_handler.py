"""Unit tests for CorrectionHandler (8-step state machine).

Steps:
 1. corr_activate   → sends activate command → corr_wait_stable
 2. corr_wait_stable → corr_check (immediate)
 3. corr_check within tolerance → exit_correction (success)
 4. corr_check max attempts exceeded → exit_correction (fail)
 5. corr_dose_ec → issues EC pulse → corr_wait_ec
 6. corr_wait_ec with PH needed → corr_dose_ph
 7. corr_wait_ph → corr_check (attempt+1, dose plan cleared)
 8. corr_deactivate (activated_here=True) → corr_done → exit_correction
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "telemetry_max_age_sec": 300,
    "target_ph": 6.0,
    "target_ec": 2.0,
    "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
    "correction": {
        "ec_mix_wait_sec": 120,
        "ph_mix_wait_sec": 60,
        "max_ec_correction_attempts": 5,
        "max_ph_correction_attempts": 5,
        "prepare_recirculation_max_correction_attempts": 32767,
        "stabilization_sec": 60,
        "actuators": {
            "ec": {"node_uid": "ec-node", "channel": "ec_pump"},
            "ph_up": {"node_uid": "ph-node", "channel": "ph_up_pump"},
            "ph_down": None,
        },
    },
}

_SENSOR_CMD = PlannedCommand(step_no=1, node_uid="sensor-1", channel="sensor_mode",
                              payload={"cmd": "activate_sensor_mode", "params": {}})


def _make_task(
    *,
    corr: CorrectionState,
    current_stage: str = "solution_fill_check",
    workflow_phase: str = "tank_filling",
    stage_deadline_at: datetime | None = None,
    stage_retry_count: int = 0,
) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 6, "zone_id": 60, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k6", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": current_stage, "workflow_phase": workflow_phase,
        "stage_deadline_at": stage_deadline_at, "stage_retry_count": stage_retry_count,
        "stage_entered_at": None, "clean_fill_cycle": 1,
        # Correction state fields
        "corr_step": corr.corr_step,
        "corr_attempt": corr.attempt,
        "corr_max_attempts": corr.max_attempts,
        "corr_ec_attempt": corr.ec_attempt,
        "corr_ec_max_attempts": corr.ec_max_attempts,
        "corr_ph_attempt": corr.ph_attempt,
        "corr_ph_max_attempts": corr.ph_max_attempts,
        "corr_activated_here": corr.activated_here,
        "corr_stabilization_sec": corr.stabilization_sec,
        "corr_return_stage_success": corr.return_stage_success,
        "corr_return_stage_fail": corr.return_stage_fail,
        "corr_outcome_success": corr.outcome_success,
        "corr_needs_ec": corr.needs_ec,
        "corr_ec_node_uid": corr.ec_node_uid,
        "corr_ec_channel": corr.ec_channel,
        "corr_ec_duration_ms": corr.ec_duration_ms,
        "corr_needs_ph_up": corr.needs_ph_up,
        "corr_needs_ph_down": corr.needs_ph_down,
        "corr_ph_node_uid": corr.ph_node_uid,
        "corr_ph_channel": corr.ph_channel,
        "corr_ph_duration_ms": corr.ph_duration_ms,
        "corr_wait_until": corr.wait_until,
    })


def _base_corr(**kwargs) -> CorrectionState:
    defaults = dict(
        corr_step="corr_check",
        attempt=1,
        max_attempts=5,
        ec_attempt=0,
        ec_max_attempts=5,
        ph_attempt=0,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=None,
        needs_ec=False,
        ec_node_uid=None,
        ec_channel=None,
        ec_duration_ms=None,
        needs_ph_up=False,
        needs_ph_down=False,
        ph_node_uid=None,
        ph_channel=None,
        ph_duration_ms=None,
        wait_until=None,
    )
    defaults.update(kwargs)
    return CorrectionState(**defaults)


class _MockPlan:
    def __init__(self, *, ph: float = 6.0, ec: float = 2.0):
        self.runtime = RUNTIME
        self.named_plans = {
            "sensor_mode_activate": (_SENSOR_CMD,),
            "sensor_mode_deactivate": (_SENSOR_CMD,),
        }
        self.targets = {}
        self._ph = ph
        self._ec = ec


class _MockRuntimeMonitor:
    def __init__(self, *, ph: float = 6.0, ec: float = 2.0):
        self._ph = ph
        self._ec = ec

    async def read_metric(self, *, zone_id, sensor_type, telemetry_max_age_sec):
        value = self._ph if sensor_type == "PH" else self._ec
        return {"has_value": True, "is_stale": False, "value": value}


class _MockGateway:
    def __init__(self, *, success: bool = True):
        self._success = success

    async def run_batch(self, *, task, commands, now):
        return {
            "success": self._success,
            "error_code": "hw_error" if not self._success else None,
            "error_message": "err" if not self._success else None,
        }


class _MockPidStateRepository:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []

    async def upsert_states(self, *, zone_id, now, updates):
        self.upsert_calls.append({"zone_id": zone_id, "updates": updates})


def _make_handler(*, monitor=None, gateway=None, pid_repo=None) -> CorrectionHandler:
    return CorrectionHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway or _MockGateway(),
        pid_state_repository=pid_repo,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_corr_activate_issues_command_and_goes_wait_stable():
    """corr_activate: sends sensor activate command, advances to corr_wait_stable."""
    corr = _base_corr(corr_step="corr_activate", activated_here=True, stabilization_sec=30)
    task = _make_task(corr=corr)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_stable"
    assert outcome.due_delay_sec == 30  # stabilization_sec


async def test_corr_wait_stable_transitions_to_check():
    """corr_wait_stable: immediately advances to corr_check."""
    corr = _base_corr(corr_step="corr_wait_stable")
    task = _make_task(corr=corr)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"


async def test_corr_check_within_tolerance_exits_success():
    """corr_check: PH/EC within tolerance → exit_correction (success)."""
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # exact targets → within tolerance
    handler = _make_handler(monitor=monitor)
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "exit_correction"
    assert outcome.next_stage == "solution_fill_stop_to_ready"
    assert outcome.correction is not None
    assert outcome.correction.outcome_success is True


async def test_corr_check_max_attempts_exceeded_solution_fill_requeues_without_new_correction_cycle():
    """solution_fill exhaustion must not restart correction with fresh attempt counters."""
    corr = _base_corr(corr_step="corr_check", attempt=6, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)  # off target
    handler = _make_handler(monitor=monitor)
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_check"
    assert outcome.stage_retry_count == 1
    assert outcome.due_delay_sec == 10




async def test_corr_dose_ec_issues_command_and_goes_wait_ec():
    """corr_dose_ec: sends EC dose pulse, advances to corr_wait_ec."""
    corr = _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=2000,
    )
    task = _make_task(corr=corr)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_ec"
    assert outcome.correction.ec_attempt == 1
    assert outcome.due_delay_sec == 120  # ec_mix_wait_sec


async def test_corr_wait_ec_routes_to_dose_ph_when_needed():
    """corr_wait_ec: PH also needed → advance to corr_dose_ph."""
    corr = _base_corr(
        corr_step="corr_wait_ec",
        needs_ph_up=True,
        ph_node_uid="ph-node",
        ph_channel="ph_up_pump",
        ph_duration_ms=1000,
    )
    task = _make_task(corr=corr)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_dose_ph"


async def test_corr_wait_ph_bumps_attempt_and_clears_dose_plan():
    """corr_wait_ph: bumps attempt counter, clears dose plan, goes to corr_check."""
    corr = _base_corr(
        corr_step="corr_wait_ph",
        attempt=2,
        needs_ec=True, ec_node_uid="ec-node", ec_channel="ec_pump", ec_duration_ms=2000,
        needs_ph_up=True, ph_node_uid="ph-node", ph_channel="ph_up_pump", ph_duration_ms=1000,
    )
    task = _make_task(corr=corr)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    c = outcome.correction
    assert c.corr_step == "corr_check"
    assert c.attempt == 3  # bumped
    assert c.needs_ec is False
    assert c.ec_node_uid is None
    assert c.needs_ph_up is False
    assert c.ph_node_uid is None


async def test_corr_check_prepare_recirc_retry_limit_transitions_window_exhausted():
    corr = _base_corr(corr_step="corr_check", attempt=2, max_attempts=1)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_retry_count=2,
    )
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)
    handler = _make_handler(monitor=monitor)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3


async def test_corr_prepare_recirc_deadline_preempts_active_correction_window():
    corr = _base_corr(corr_step="corr_wait_ec", attempt=4, ec_attempt=4, ph_attempt=3)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_deadline_at=NOW - timedelta(seconds=1),
        stage_retry_count=1,
    )
    handler = _make_handler()

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 2


async def test_corr_solution_fill_deadline_preempts_active_correction_window():
    corr = _base_corr(corr_step="corr_wait_ph", attempt=4, ec_attempt=3, ph_attempt=3)
    task = _make_task(
        corr=corr,
        current_stage="solution_fill_check",
        workflow_phase="tank_filling",
        stage_deadline_at=NOW - timedelta(seconds=1),
    )
    handler = _make_handler()

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_timeout_stop"


async def test_corr_deactivate_sets_done_and_exits():
    """corr_deactivate (activated_here=True): deactivates sensors, sets corr_done, then exit_correction."""
    corr = _base_corr(
        corr_step="corr_deactivate",
        activated_here=True,
        outcome_success=True,
    )
    task = _make_task(corr=corr)
    handler = _make_handler()
    # First call: deactivate → corr_done
    outcome1 = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert outcome1.kind == "enter_correction"
    assert outcome1.correction.corr_step == "corr_done"

    # Second call (corr_done): exit_correction
    task2 = _make_task(corr=outcome1.correction)
    outcome2 = await handler.run(task=task2, plan=_MockPlan(), stage_def=None, now=NOW)
    assert outcome2.kind == "exit_correction"
    assert outcome2.next_stage == "solution_fill_stop_to_ready"
    assert outcome2.correction is not None
    assert outcome2.correction.outcome_success is True


async def test_corr_check_persists_pid_state_updates_when_dose_needed():
    """Regression BUG-19: corr_check must persist dose_plan.pid_state_updates to DB."""
    pid_repo = _MockPidStateRepository()
    # ec=0.5 is below target_ec=2.0 → dose needed
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_up": {"node_uid": "ph-node", "channel": "ph_up_pump"},
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 200,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }

    class _PlanWithCalib:
        named_plans = {}

    _PlanWithCalib.runtime = runtime

    monitor = _MockRuntimeMonitor(ph=6.0, ec=0.5)
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)

    outcome = await handler.run(task=task, plan=_PlanWithCalib(), stage_def=None, now=NOW)

    # pid_state_repository.upsert_states must have been called
    assert len(pid_repo.upsert_calls) == 1, "pid_state_updates must be persisted after corr_check"
    call = pid_repo.upsert_calls[0]
    assert call["zone_id"] == 60
    pid_types_saved = {u["pid_type"] for u in call["updates"]}
    # EC dose was needed → "ec" pid state should be in the update
    assert "ec" in pid_types_saved


async def test_corr_check_no_pid_repo_does_not_crash():
    """corr_check must not fail when pid_state_repository is None (backward compat)."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # within tolerance → no dose
    handler = _make_handler(monitor=monitor, pid_repo=None)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    # Should succeed regardless (no crash when repo is None)
    assert outcome.kind in {"enter_correction", "exit_correction"}
