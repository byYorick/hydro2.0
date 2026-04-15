"""Unit tests for CorrectionHandler (8-step state machine).

Steps:
 1. corr_activate   → sends activate command → corr_wait_stable
 2. corr_wait_stable → corr_check (immediate)
 3. corr_check within tolerance → exit_correction (success)
 4. corr_check max attempts exceeded → exit_correction (fail)
 5. corr_dose_ec → issues EC pulse → corr_wait_ec
 6. corr_wait_ec observes response → corr_check
 7. corr_wait_ph observes response → corr_check (attempt+1, dose plan cleared)
 8. corr_deactivate (activated_here=True) → corr_done → exit_correction
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import math
import pytest
from prometheus_client import REGISTRY

from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import DosePlan


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "telemetry_max_age_sec": 10,
    "solution_max_sensor_labels": ["level_solution_max"],
    "solution_min_sensor_labels": ["level_solution_min"],
    "level_switch_on_threshold": 0.5,
    "target_ph": 6.0,
    "target_ec": 2.0,
    "target_ec_prepare": 2.0,
    "npk_ec_share": 1.0,
    "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
    "process_calibrations": {
        "solution_fill": {
            "ec_gain_per_ml": 0.2,
            "ph_up_gain_per_ml": 0.2,
            "ph_down_gain_per_ml": 0.2,
            "ph_per_ec_ml": 0.0,
            "transport_delay_sec": 6,
            "settle_sec": 4,
            "meta": {
                "observe": {
                    "telemetry_period_sec": 2,
                    "window_min_samples": 3,
                    "decision_window_sec": 6,
                    "observe_poll_sec": 2,
                    "min_effect_fraction": 0.25,
                    "stability_max_slope": 0.2,
                    "no_effect_consecutive_limit": 3,
                }
            },
        },
        "tank_recirc": {
            "ec_gain_per_ml": 0.2,
            "ph_up_gain_per_ml": 0.2,
            "ph_down_gain_per_ml": 0.2,
            "ph_per_ec_ml": 0.0,
            "transport_delay_sec": 6,
            "settle_sec": 4,
            "meta": {
                "observe": {
                    "telemetry_period_sec": 2,
                    "window_min_samples": 3,
                    "decision_window_sec": 6,
                    "observe_poll_sec": 2,
                    "min_effect_fraction": 0.25,
                    "stability_max_slope": 0.2,
                    "no_effect_consecutive_limit": 3,
                }
            },
        },
    },
    "pid_state": {},
    "correction": {
        "max_ec_correction_attempts": 5,
        "max_ph_correction_attempts": 5,
        "prepare_recirculation_max_correction_attempts": 20,
        # Phase 3.1 / B-5e: retry delays now required (no Python defaults).
        # Tests overriding individual delays still work — these are the baseline.
        "telemetry_stale_retry_sec": 30,
        "decision_window_retry_sec": 30,
        "low_water_retry_sec": 60,
        "stabilization_sec": 60,
        "controllers": {
            "ec": {
                "telemetry_period_sec": 2,
                "window_min_samples": 3,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.2,
            },
            "ph": {
                "telemetry_period_sec": 2,
                "window_min_samples": 3,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.2,
            },
        },
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
        "corr_ec_component": corr.ec_component,
        "corr_ec_amount_ml": corr.ec_amount_ml,
        "corr_ec_dose_sequence_json": corr.ec_dose_sequence_json,
        "corr_ec_current_seq_index": corr.ec_current_seq_index,
        "corr_ph_amount_ml": corr.ph_amount_ml,
        "corr_snapshot_event_id": corr.snapshot_event_id,
        "corr_snapshot_created_at": corr.snapshot_created_at,
        "corr_snapshot_cmd_id": corr.snapshot_cmd_id,
        "corr_snapshot_source_event_type": corr.snapshot_source_event_type,
        "corr_limit_policy_logged": corr.limit_policy_logged,
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
        snapshot_event_id=None,
        snapshot_created_at=None,
        snapshot_cmd_id=None,
        snapshot_source_event_type=None,
        limit_policy_logged=False,
    )
    defaults.update(kwargs)
    return CorrectionState(**defaults)


class _MockPlan:
    def __init__(
        self,
        *,
        ph: float = 6.0,
        ec: float = 2.0,
        runtime: dict | None = None,
        include_irr_state_probe: bool = True,
    ):
        self.runtime = runtime or RUNTIME
        self.named_plans = {
            "sensor_mode_activate": (_SENSOR_CMD,),
            "sensor_mode_deactivate": (_SENSOR_CMD,),
        }
        if include_irr_state_probe:
            self.named_plans["irr_state_probe"] = (
                PlannedCommand(
                    step_no=1,
                    node_uid="irr-node",
                    channel="storage_state",
                    payload={"cmd": "state", "name": "irr_state_probe", "params": {}},
                ),
            )
        self.targets = {}
        self._ph = ph
        self._ec = ec


class _MockRuntimeMonitor:
    def __init__(
        self,
        *,
        ph: float = 6.0,
        ec: float = 2.0,
        ph_samples=None,
        ec_samples=None,
        ph_stale: bool = False,
        ec_stale: bool = False,
        solution_max_triggered: bool = False,
        solution_min_triggered: bool = True,
        has_level: bool = True,
        level_stale: bool = False,
        irr_snapshot: dict | None = None,
        irr_has_snapshot: bool = True,
        irr_is_stale: bool = False,
    ):
        self._ph = ph
        self._ec = ec
        self._ph_stale = ph_stale
        self._ec_stale = ec_stale
        self._solution_max_triggered = solution_max_triggered
        self._solution_min_triggered = solution_min_triggered
        self._has_level = has_level
        self._level_stale = level_stale
        self._irr_snapshot = dict(
            irr_snapshot
            or {
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "valve_solution_supply": True,
                "pump_main": True,
            }
        )
        self._irr_has_snapshot = irr_has_snapshot
        self._irr_is_stale = irr_is_stale
        self.irr_reads = 0
        self._ph_samples = list(ph_samples) if ph_samples is not None else [
            {"ts": NOW - timedelta(seconds=4), "value": ph},
            {"ts": NOW - timedelta(seconds=2), "value": ph},
            {"ts": NOW, "value": ph},
        ]
        self._ec_samples = list(ec_samples) if ec_samples is not None else [
            {"ts": NOW - timedelta(seconds=4), "value": ec},
            {"ts": NOW - timedelta(seconds=2), "value": ec},
            {"ts": NOW, "value": ec},
        ]

    async def read_metric(self, *, zone_id, sensor_type, telemetry_max_age_sec):
        value = self._ph if sensor_type == "PH" else self._ec
        is_stale = self._ph_stale if sensor_type == "PH" else self._ec_stale
        return {"has_value": True, "is_stale": is_stale, "value": value}

    async def read_metric_window(self, *, zone_id, sensor_type, since_ts, telemetry_max_age_sec, limit=64):
        samples = self._ph_samples if sensor_type == "PH" else self._ec_samples
        is_stale = self._ph_stale if sensor_type == "PH" else self._ec_stale
        filtered = tuple(sample for sample in samples if sample["ts"] >= since_ts)
        return {
            "has_sensor": True,
            "has_samples": bool(filtered),
            "is_stale": is_stale,
            "sensor_id": 1,
            "sensor_label": sensor_type.lower(),
            "samples": filtered,
            "latest_sample_ts": filtered[-1]["ts"] if filtered else NOW,
            "sample_age_sec": 0.0,
        }

    async def read_level_switch(
        self,
        *,
        zone_id,
        sensor_labels,
        threshold,
        telemetry_max_age_sec,
        allow_initial_event_fallback=False,
    ):
        labels = [str(label) for label in sensor_labels]
        is_max = "level_solution_max" in labels
        return {
            "has_level": self._has_level,
            "is_stale": self._level_stale,
            "is_triggered": self._solution_max_triggered if is_max else self._solution_min_triggered,
        }

    async def read_latest_irr_state(self, *, zone_id, max_age_sec, expected_cmd_id=None):
        self.irr_reads += 1
        return {
            "event_id": 501,
            "has_snapshot": self._irr_has_snapshot,
            "is_stale": self._irr_is_stale,
            "snapshot": dict(self._irr_snapshot) if self._irr_has_snapshot else None,
            "cmd_id": expected_cmd_id,
        }


class _MockGateway:
    def __init__(self, *, success: bool = True):
        self._success = success
        self.calls: list[dict] = []

    async def run_batch(self, *, task, commands, now, track_task_state: bool = True):
        self.calls.append({
            "task": task,
            "commands": tuple(commands),
            "now": now,
            "track_task_state": track_task_state,
        })
        return {
            "success": self._success,
            "error_code": "hw_error" if not self._success else None,
            "error_message": "err" if not self._success else None,
        }


class _MockPidStateRepository:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []
        self.feedforward_cleared: list[int] = []
        self.no_effect_resets: list[int] = []

    async def upsert_states(self, *, zone_id, now, updates):
        self.upsert_calls.append({"zone_id": zone_id, "updates": updates})

    async def clear_feedforward_bias(self, *, zone_id):
        self.feedforward_cleared.append(zone_id)

    async def reset_no_effect_counts(self, *, zone_id):
        self.no_effect_resets.append(zone_id)


def _make_handler(*, monitor=None, gateway=None, pid_repo=None, planner=None) -> CorrectionHandler:
    return CorrectionHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway or _MockGateway(),
        planner=planner,
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


async def test_corr_check_prepare_recirc_soft_tolerance_without_ready_band_keeps_dosing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))
    corr = _base_corr(
        corr_step="corr_check",
        attempt=1,
        max_attempts=5,
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
    )
    runtime = deepcopy(RUNTIME)
    runtime["target_ph_min"] = 5.6
    runtime["target_ph_max"] = 6.0
    runtime["target_ec_min"] = 1.6
    runtime["target_ec_max"] = 1.8
    runtime["correction"]["controllers"]["ec"].update(
        {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.01,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
        }
    )
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_up": {
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }
    monitor = _MockRuntimeMonitor(ph=5.8, ec=1.85)
    handler = _make_handler(monitor=monitor)

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dose_ec"


async def test_corr_check_inside_explicit_window_below_target_keeps_dosing(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    runtime = deepcopy(RUNTIME)
    runtime["prepare_tolerance"] = {"ph_pct": 1.0, "ec_pct": 1.0}
    runtime["target_ec_min"] = 1.9
    runtime["target_ec_max"] = 2.1
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.01,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
        },
        "ph": {
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.01,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
        },
    }
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
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=1.91,
        ph_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 6.0},
            {"ts": NOW - timedelta(seconds=5), "value": 6.0},
            {"ts": NOW - timedelta(seconds=3), "value": 6.0},
        ],
        ec_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 1.91},
            {"ts": NOW - timedelta(seconds=5), "value": 1.91},
            {"ts": NOW - timedelta(seconds=3), "value": 1.91},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dose_ec"
    assert outcome.correction.needs_ec is True


async def test_corr_check_fails_closed_when_prepare_recirc_flow_path_is_inactive():
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
    )
    monitor = _MockRuntimeMonitor(
        ph=6.3,
        ec=1.1,
        irr_snapshot={
            "pump_main": False,
            "valve_solution_fill": True,
            "valve_solution_supply": True,
        },
    )
    gateway = _MockGateway()
    handler = _make_handler(monitor=monitor, gateway=gateway)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(
            task=task,
            plan=_MockPlan(include_irr_state_probe=True),
            stage_def=None,
            now=NOW,
        )
    assert exc_info.value.code == "irr_state_mismatch"
    assert "pump_main" in str(exc_info.value)

    assert len(gateway.calls) == 1 + handler._IRR_STATE_PROBE_RETRY_COUNT
    assert gateway.calls[0]["commands"][0].channel == "storage_state"


async def test_corr_check_solution_fill_probe_mismatch_yields_to_raced_completed_event(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    handler = _make_handler(monitor=_MockRuntimeMonitor(ph=6.0, ec=2.0))
    handler._probe_irr_state = AsyncMock(side_effect=TaskExecutionError("irr_state_mismatch", "pump off"))

    reads = {"completion": 0}

    async def _fake_read(*, task, event_types, max_age_sec):
        if "SOLUTION_FILL_COMPLETED" not in event_types:
            return None
        reads["completion"] += 1
        if reads["completion"] == 1:
            return None
        return {"event_id": 27, "event_type": "SOLUTION_FILL_COMPLETED", "payload": {"channel": "storage_state"}}

    monkeypatch.setattr(handler, "_read_recent_storage_event", _fake_read)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_stop_to_ready"
    assert reads["completion"] >= 2


async def test_corr_check_ignores_attempt_caps_during_solution_fill():
    """solution_fill must remain in one correction window until no-effect or stage timeout."""
    corr = _base_corr(corr_step="corr_check", attempt=6, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)  # off target
    handler = _make_handler(monitor=monitor)
    create_event = AsyncMock(return_value=None)
    monkeypatch_target = "ae3lite.application.handlers.correction.create_zone_event"
    metric_labels = {"topology": "two_tank", "stage": "solution_fill_check", "cap_type": "overall"}
    before_metric = REGISTRY.get_sample_value("ae3_correction_cap_ignored_total", metric_labels) or 0.0
    runtime = deepcopy(RUNTIME)
    runtime["correction"]["controllers"]["ec"].update(
        {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
        }
    )
    runtime["correction"]["controllers"]["ph"].update(
        {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
        }
    )
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_up": {
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(monkeypatch_target, create_event)
        outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dose_ec"
    assert any(call.args[1] == "CORRECTION_ATTEMPT_CAP_IGNORED" for call in create_event.await_args_list)
    assert (REGISTRY.get_sample_value("ae3_correction_cap_ignored_total", metric_labels) or 0.0) == (
        before_metric + 1.0
    )


async def test_corr_check_logs_fill_limit_policy_on_first_tick():
    corr = _base_corr(corr_step="corr_check", attempt=0, max_attempts=5, ec_attempt=0, ph_attempt=0)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)
    handler = _make_handler(monitor=monitor)
    create_event = AsyncMock(return_value=None)
    runtime = deepcopy(RUNTIME)
    runtime["correction"]["controllers"]["ec"].update(
        {"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.05, "max_dose_ml": 10.0, "min_interval_sec": 0, "max_integral": 20.0}
    )
    runtime["correction"]["controllers"]["ph"].update(
        {"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.05, "max_dose_ml": 10.0, "min_interval_sec": 0, "max_integral": 20.0}
    )
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_up": {
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
        outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert any(call.args[1] == "CORRECTION_LIMIT_POLICY_APPLIED" for call in create_event.await_args_list)
    assert outcome.correction.limit_policy_logged is True


async def test_corr_check_does_not_repeat_limit_policy_event_when_already_logged(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_check",
        attempt=0,
        ec_attempt=0,
        ph_attempt=0,
        limit_policy_logged=True,
    )
    task = _make_task(
        corr=corr,
        current_stage="solution_fill_check",
        workflow_phase="tank_filling",
    )
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    handler = _make_handler(monitor=_MockRuntimeMonitor(ph=6.0, ec=2.0))

    await handler.run(task=task, plan=_MockPlan(runtime=deepcopy(RUNTIME)), stage_def=None, now=NOW)

    assert not any(call.args[1] == "CORRECTION_LIMIT_POLICY_APPLIED" for call in create_event.await_args_list)


async def test_corr_check_max_attempts_exceeded_still_sends_alert_in_prepare_recirc(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check", attempt=6, max_attempts=5)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
    )
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)
    handler = _make_handler(monitor=monitor)
    send_alert = AsyncMock(return_value=True)
    monkeypatch.setattr("ae3lite.application.handlers.correction.send_biz_alert", send_alert)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))

    await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    send_alert.assert_awaited_once()
    assert send_alert.await_args.kwargs["message"] == "Цикл коррекции исчерпал все настроенные попытки."


async def test_corr_check_keeps_ec_and_ph_in_same_correction_window(monkeypatch: pytest.MonkeyPatch):
    class _PlannerStub:
        def is_within_tolerance(self, **kwargs):
            return False

        def build_dose_plan(self, **kwargs):
            return DosePlan(
                needs_ec=True,
                ec_node_uid="ec-node",
                ec_channel="ec_pump",
                ec_amount_ml=2.0,
                ec_duration_ms=2000,
                needs_ph_down=True,
                ph_node_uid="ph-node",
                ph_channel="ph_down_pump",
                ph_amount_ml=1.5,
                ph_duration_ms=1500,
                pid_state_updates={
                    "ph": {
                        "last_measurement_at": NOW,
                        "last_measured_value": 6.2,
                    },
                    "ec": {
                        "last_measurement_at": NOW,
                        "last_measured_value": 1.7,
                    }
                },
            )

    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    corr = _base_corr(corr_step="corr_check", attempt=1)
    task = _make_task(corr=corr, current_stage="prepare_recirculation_check", workflow_phase="tank_recirc")
    pid_repo = _MockPidStateRepository()
    handler = _make_handler(
        monitor=_MockRuntimeMonitor(ph=6.2, ec=1.7),
        pid_repo=pid_repo,
        planner=_PlannerStub(),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=dict(RUNTIME)), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_dose_ec"
    assert outcome.correction.needs_ec is True
    assert outcome.correction.needs_ph_down is True
    assert outcome.correction.ph_channel == "ph_down_pump"
    decision_calls = [call for call in create_event.await_args_list if call.args[1] == "CORRECTION_DECISION_MADE"]
    assert len(decision_calls) == 1
    decision_payload = decision_calls[0].args[2]
    assert decision_payload["selected_action"] == "ec"
    assert decision_payload["decision_reason"] == "ec_first_in_window"
    assert decision_payload["correction_window_id"] == "task:6:tank_recirc:prepare_recirculation_check"
    assert decision_payload["needs_ec"] is True
    assert decision_payload["needs_ph_down"] is True
    assert pid_repo.upsert_calls == [
        {
            "zone_id": 60,
            "updates": [
                {
                    "pid_type": "ph",
                    "last_measurement_at": NOW,
                    "last_measured_value": 6.2,
                },
                {
                    "pid_type": "ec",
                    "last_measurement_at": NOW,
                    "last_measured_value": 1.7,
                }
            ],
        }
    ]
    assert not any(call.args[1] == "CORRECTION_ACTION_DEFERRED" for call in create_event.await_args_list)




async def test_corr_dose_ec_issues_command_and_goes_wait_ec():
    """corr_dose_ec: sends EC dose pulse, advances to corr_wait_ec."""
    corr = _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_amount_ml=2.0,
        ec_duration_ms=2000,
    )
    task = _make_task(corr=corr)
    gateway = _MockGateway()
    create_event = AsyncMock(return_value=None)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    handler = _make_handler(gateway=gateway)
    handler._last_probe_state = {
        "zone_id": 60,
        "task_id": 6,
        "stage": "solution_fill_check",
        "state": {
            "has_snapshot": True,
            "is_stale": False,
            "snapshot": {"pump_main": True},
            "sample_age_sec": 0.2,
            "created_at": NOW,
            "cmd_id": "probe-cmd-1",
            "event_id": 777,
        },
    }
    try:
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    finally:
        monkeypatch.undo()

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_ec"
    assert outcome.correction.ec_attempt == 1
    assert outcome.due_delay_sec == 10
    assert outcome.correction.wait_until == NOW + timedelta(seconds=10)
    assert len(gateway.calls) == 3
    reactivate_commands = gateway.calls[1]["commands"]
    assert len(reactivate_commands) == 1
    assert reactivate_commands[0].payload["cmd"] == "activate_sensor_mode"
    dose_commands = gateway.calls[2]["commands"]
    assert len(dose_commands) == 1
    assert dose_commands[0].payload == {
        "cmd": "dose",
        "params": {"ml": 2.0},
    }
    assert create_event.await_count == 2
    reactivate_call = create_event.await_args_list[0]
    assert reactivate_call.args[1] == "CORRECTION_SENSOR_MODE_REACTIVATED"
    reactivate_payload = reactivate_call.args[2]
    assert reactivate_payload["reason"] == "pre_dose_reactivation"
    assert reactivate_payload["failed_node_uid"] == "ec-node"
    assert reactivate_payload["failed_channel"] == "ec_pump"
    assert reactivate_payload["retry_cmd"] == "dose"
    dose_call = create_event.await_args_list[1]
    assert dose_call.args[1] == "EC_DOSING"
    payload = dose_call.args[2]
    assert payload["task_id"] == 6
    assert payload["stage"] == "solution_fill_check"
    assert payload["workflow_phase"] == "tank_filling"
    assert payload["correction_window_id"] == "task:6:tank_filling:solution_fill_check"
    assert payload["corr_step"] == "corr_dose_ec"
    assert payload["observe_seq"] == 1
    assert payload["attempt"] == 1
    assert payload["ec_attempt"] == 1
    assert payload["current_stage"] == "solution_fill_check"
    assert payload["event_schema_version"] == 2
    assert payload["snapshot_event_id"] == 501
    assert "snapshot_cmd_id" not in payload
    assert payload["caused_by_event_id"] == 501


async def test_corr_dose_ec_uses_persisted_snapshot_context_when_probe_belongs_to_other_handler():
    corr = _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_amount_ml=2.0,
        ec_duration_ms=2000,
        snapshot_event_id=888,
        snapshot_created_at=NOW,
        snapshot_cmd_id="probe-cmd-persisted",
        snapshot_source_event_type="IRR_STATE_SNAPSHOT",
    )
    task = _make_task(corr=corr, current_stage="irrigation_check", workflow_phase="irrigating")
    gateway = _MockGateway()
    create_event = AsyncMock(return_value=None)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    handler = _make_handler(gateway=gateway, pid_repo=_MockPidStateRepository())

    try:
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    finally:
        monkeypatch.undo()

    assert outcome.kind == "enter_correction"
    dose_call = create_event.await_args_list[-1]
    assert dose_call.args[1] == "EC_DOSING"
    payload = dose_call.args[2]
    assert payload["event_schema_version"] == 2
    assert payload["snapshot_event_id"] == 888
    assert payload["snapshot_cmd_id"] == "probe-cmd-persisted"
    assert payload["snapshot_source_event_type"] == "IRR_STATE_SNAPSHOT"
    assert payload["caused_by_event_id"] == 888


async def test_corr_dose_ph_issues_volume_command_and_goes_wait_ph():
    corr = _base_corr(
        corr_step="corr_dose_ph",
        needs_ph_up=True,
        ph_node_uid="ph-node",
        ph_channel="ph_up_pump",
        ph_amount_ml=1.5,
        ph_duration_ms=1500,
    )
    task = _make_task(corr=corr)
    gateway = _MockGateway()
    create_event = AsyncMock(return_value=None)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    handler = _make_handler(gateway=gateway)

    try:
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    finally:
        monkeypatch.undo()

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_ph"
    assert outcome.correction.ph_attempt == 1
    assert outcome.due_delay_sec == 10
    assert outcome.correction.wait_until == NOW + timedelta(seconds=10)
    assert len(gateway.calls) == 3
    reactivate_commands = gateway.calls[1]["commands"]
    assert len(reactivate_commands) == 1
    assert reactivate_commands[0].payload["cmd"] == "activate_sensor_mode"
    dose_commands = gateway.calls[2]["commands"]
    assert len(dose_commands) == 1
    assert dose_commands[0].payload == {
        "cmd": "dose",
        "params": {"ml": 1.5},
    }
    assert create_event.await_count == 2
    reactivate_call = create_event.await_args_list[0]
    assert reactivate_call.args[1] == "CORRECTION_SENSOR_MODE_REACTIVATED"
    reactivate_payload = reactivate_call.args[2]
    assert reactivate_payload["reason"] == "pre_dose_reactivation"
    assert reactivate_payload["failed_node_uid"] == "ph-node"
    assert reactivate_payload["failed_channel"] == "ph_up_pump"
    assert reactivate_payload["retry_cmd"] == "dose"
    dose_call = create_event.await_args_list[1]
    assert dose_call.args[1] == "PH_CORRECTED"
    payload = dose_call.args[2]
    assert payload["task_id"] == 6
    assert payload["stage"] == "solution_fill_check"
    assert payload["workflow_phase"] == "tank_filling"
    assert payload["correction_window_id"] == "task:6:tank_filling:solution_fill_check"
    assert payload["corr_step"] == "corr_dose_ph"
    assert payload["observe_seq"] == 1
    assert payload["attempt"] == 1
    assert payload["ph_attempt"] == 1
    assert payload["event_schema_version"] == 2


async def test_corr_wait_ec_observes_response_and_returns_to_check():
    """corr_wait_ec: after hold/observe returns to corr_check, without piggyback PH dose."""
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    pid_repo = _MockPidStateRepository()
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.35},
        {"ts": NOW - timedelta(seconds=2), "value": 1.4},
        {"ts": NOW, "value": 1.45},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)
    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.correction.attempt == 0   # reaction detected → counters reset
    assert outcome.correction.ec_attempt == 0
    assert outcome.correction.needs_ec is False
    assert pid_repo.feedforward_cleared == [60]


async def test_corr_wait_ec_preserves_pending_ph_for_next_corr_check():
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        needs_ph_down=True,
        ph_amount_ml=1.5,
        ph_node_uid="ph-node",
        ph_channel="ph_down_pump",
        ph_duration_ms=1500,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.35},
        {"ts": NOW - timedelta(seconds=2), "value": 1.4},
        {"ts": NOW, "value": 1.45},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.correction.needs_ec is False
    assert outcome.correction.needs_ph_down is True
    assert outcome.correction.ph_node_uid == "ph-node"
    assert outcome.correction.ph_channel == "ph_down_pump"
    assert outcome.correction.ph_amount_ml == 1.5


async def test_corr_wait_ec_interrupts_to_prepare_when_solution_fill_completed(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    task = _make_task(corr=corr, current_stage="solution_fill_check", workflow_phase="tank_filling")
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(
        ph=6.8,
        ec=0.7,
        solution_max_triggered=True,
        solution_min_triggered=True,
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=RUNTIME), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_stop_to_prepare"
    assert create_event.await_args.args[1] == "CORRECTION_INTERRUPTED_STAGE_COMPLETE"
    payload = create_event.await_args.args[2]
    assert payload["next_stage"] == "solution_fill_stop_to_prepare"
    assert payload["reason"] == "solution_tank_full"
    assert payload["targets_reached"] is False


async def test_corr_wait_ec_interrupts_to_ready_when_solution_fill_completed_and_targets_reached(
    monkeypatch: pytest.MonkeyPatch,
):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    task = _make_task(corr=corr, current_stage="solution_fill_check", workflow_phase="tank_filling")
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=2.0,
        solution_max_triggered=True,
        solution_min_triggered=True,
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=RUNTIME), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_stop_to_ready"
    payload = create_event.await_args.args[2]
    assert payload["next_stage"] == "solution_fill_stop_to_ready"
    assert payload["targets_reached"] is True


async def test_corr_wait_ec_stale_telemetry_retries_in_30s():
    """corr_wait_ec: stale telemetry в observe window должен ретраиться, а не фейлить таск."""
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ec_stale=True)
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_ec"
    assert outcome.due_delay_sec == 30.0


async def test_corr_check_stale_telemetry_logs_freshness_event(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check", attempt=2)
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ph_stale=True)
    handler = _make_handler(monitor=monitor)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.due_delay_sec == 30.0
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_FRESHNESS"
    payload = create_event.await_args.args[2]
    assert payload["sensor_scope"] == "decision_window"
    assert payload["retry_after_sec"] == 30.0
    assert payload["stage"] == "solution_fill_check"
    assert payload["workflow_phase"] == "tank_filling"


async def test_corr_check_window_not_ready_logs_event(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check", attempt=1)
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(
        ph_samples=[
          {"ts": NOW - timedelta(seconds=2), "value": 6.0},
          {"ts": NOW, "value": 6.0},
        ],
        ec_samples=[
          {"ts": NOW - timedelta(seconds=4), "value": 1.8},
          {"ts": NOW - timedelta(seconds=2), "value": 1.85},
          {"ts": NOW, "value": 1.9},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 2.0
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_WINDOW_NOT_READY"
    payload = create_event.await_args.args[2]
    assert payload["sensor_scope"] == "decision_window"
    assert payload["ph_reason"] == "insufficient_samples"
    assert payload["ph_sample_count"] == 2
    assert payload["ph_window_min_samples"] == 3
    assert payload["ph_telemetry_period_sec"] == 2
    assert payload["ph_since_ts"] is not None
    assert payload["ph_latest_sample_ts"] is not None
    assert payload["ec_reason"] is None
    assert payload["ec_window_min_samples"] is None
    assert payload["ec_telemetry_period_sec"] is None
    assert payload["ec_since_ts"] is None
    assert payload["ec_latest_sample_ts"] is None
    assert payload["retry_after_sec"] == 2.0


async def test_corr_check_zero_sample_window_reactivates_stage_owned_sensor_mode() -> None:
    corr = _base_corr(corr_step="corr_check", attempt=1, activated_here=False, stabilization_sec=45)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph_samples=[], ec_samples=[])
    gateway = _MockGateway()
    handler = _make_handler(monitor=monitor, gateway=gateway, pid_repo=_MockPidStateRepository())

    create_event = AsyncMock(return_value=None)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    try:
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    finally:
        monkeypatch.undo()

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_stable"
    assert outcome.correction.activated_here is False
    assert outcome.due_delay_sec == 45
    assert len(gateway.calls) == 2
    commands = gateway.calls[1]["commands"]
    assert len(commands) == 1
    assert commands[0].payload["cmd"] == "activate_sensor_mode"
    assert create_event.await_args.args[1] == "CORRECTION_SENSOR_MODE_REACTIVATED"


async def test_corr_check_irrigation_stage_does_not_reactivate_already_active_sensor_mode() -> None:
    corr = _base_corr(corr_step="corr_check", attempt=1, activated_here=False, stabilization_sec=45)
    task = _make_task(corr=corr, current_stage="irrigation_check", workflow_phase="irrigating")
    monitor = _MockRuntimeMonitor(ph_samples=[], ec_samples=[])
    gateway = _MockGateway()
    handler = _make_handler(monitor=monitor, gateway=gateway, pid_repo=_MockPidStateRepository())

    create_event = AsyncMock(return_value=None)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    try:
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    finally:
        monkeypatch.undo()

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 6.0
    assert len(gateway.calls) == 0
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_WINDOW_NOT_READY"


async def test_corr_check_low_water_logs_skip_event(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check", attempt=2)
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ph=6.3, ec=1.1, solution_min_triggered=False)
    handler = _make_handler(monitor=monitor)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.due_delay_sec == 60.0
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_WATER_LEVEL"
    payload = create_event.await_args.args[2]
    assert payload["water_level_pct"] == pytest.approx(0.0)
    assert payload["current_ph"] == pytest.approx(6.3)
    assert payload["current_ec"] == pytest.approx(1.1)
    assert payload["retry_after_sec"] == 60.0


async def test_corr_wait_ph_observes_response_and_clears_dose_plan():
    """corr_wait_ph: observe pH response, bump attempt, clear dose plan, go to corr_check."""
    corr = _base_corr(
        corr_step="corr_wait_ph",
        attempt=2,
        ph_attempt=1,
        needs_ph_up=True, ph_node_uid="ph-node", ph_channel="ph_up_pump", ph_duration_ms=1000,
        ph_amount_ml=2.0,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ph": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 5.6,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 5.8},
        {"ts": NOW - timedelta(seconds=2), "value": 5.95},
        {"ts": NOW, "value": 6.0},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())
    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    c = outcome.correction
    assert c.corr_step == "corr_check"
    assert c.attempt == 0    # reaction detected → counters reset
    assert c.ph_attempt == 0
    assert c.needs_ec is False
    assert c.ec_node_uid is None
    assert c.needs_ph_up is False
    assert c.ph_node_uid is None


async def test_corr_wait_ec_three_no_effect_attempts_fail_closed_solution_fill(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 2,
        }
    }
    task = _make_task(corr=corr)
    send_alert = AsyncMock(return_value=True)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.send_biz_alert", send_alert)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.01},
        {"ts": NOW - timedelta(seconds=2), "value": 1.02},
        {"ts": NOW, "value": 1.01},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_timeout_stop"
    send_alert.assert_awaited_once()
    assert send_alert.await_args.kwargs["message"] == (
        "Коррекция EC не дала наблюдаемого эффекта 3 раз подряд."
    )
    assert create_event.await_count == 2
    observation_call = create_event.await_args_list[0]
    assert observation_call.args[1] == "CORRECTION_OBSERVATION_EVALUATED"
    observation_payload = observation_call.args[2]
    assert observation_payload["pid_type"] == "ec"
    assert observation_payload["actual_effect"] == pytest.approx(0.01)
    assert observation_payload["expected_effect"] == pytest.approx(0.4)
    assert observation_payload["threshold_effect"] == pytest.approx(0.1)
    assert observation_payload["is_no_effect"] is True
    assert observation_payload["no_effect_count_next"] == 3
    assert observation_payload["dose_amount_ml"] == pytest.approx(2.0)
    assert observation_payload["observe_seq"] == 1
    assert observation_payload["correction_window_id"] == "task:6:tank_filling:solution_fill_check"
    no_effect_call = create_event.await_args_list[1]
    assert no_effect_call.args[1] == "CORRECTION_NO_EFFECT"
    payload = no_effect_call.args[2]
    assert payload["pid_type"] == "ec"
    assert payload["actual_effect"] == pytest.approx(0.02)
    assert payload["threshold_effect"] == pytest.approx(0.1)
    assert payload["no_effect_limit"] == 3


async def test_corr_wait_ec_logs_observation_evaluation_for_reaction(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=4,
        ec_attempt=3,
        ph_attempt=2,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 1,
        }
    }
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.35},
        {"ts": NOW - timedelta(seconds=2), "value": 1.40},
        {"ts": NOW, "value": 1.45},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.attempt == 0
    assert outcome.correction.ec_attempt == 0
    assert outcome.correction.ph_attempt == 0
    assert create_event.await_count == 1
    assert create_event.await_args.args[1] == "CORRECTION_OBSERVATION_EVALUATED"
    payload = create_event.await_args.args[2]
    assert payload["pid_type"] == "ec"
    assert payload["actual_effect"] == pytest.approx(0.4)
    assert payload["peak_effect"] == pytest.approx(0.45)
    assert payload["expected_effect"] == pytest.approx(0.4)
    assert payload["threshold_effect"] == pytest.approx(0.1)
    assert payload["is_no_effect"] is False
    assert payload["no_effect_count_next"] == 0
    assert payload["dose_amount_ml"] == pytest.approx(2.0)
    assert payload["observe_seq"] == 3
    assert payload["correction_window_id"] == "task:6:tank_filling:solution_fill_check"


async def test_corr_wait_ec_wave_response_does_not_increment_attempts(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=3,
        ec_attempt=2,
        ph_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 1,
        }
    }
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    pid_repo = _MockPidStateRepository()
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.14},
        {"ts": NOW - timedelta(seconds=2), "value": 1.07},
        {"ts": NOW, "value": 1.05},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.attempt == 0
    assert outcome.correction.ec_attempt == 0
    assert create_event.await_count == 1
    payload = create_event.await_args.args[2]
    assert payload["is_no_effect"] is False
    assert payload["wave_detected"] is True
    assert payload["peak_effect"] == pytest.approx(0.14)
    assert payload["actual_effect"] == pytest.approx(0.07)
    assert payload["retention_ratio"] == pytest.approx(0.5)
    assert pid_repo.upsert_calls
    adaptive_stats = pid_repo.upsert_calls[-1]["updates"][0]["stats"]["adaptive"]
    assert adaptive_stats["gains"]["ec_gain_per_ml"]["observations"] == 1
    assert adaptive_stats["wave_score_ema"] == pytest.approx(0.5)


async def test_corr_dose_ec_uses_learned_observation_timing_from_pid_state_stats():
    corr = _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=900,
        ec_amount_ml=2.0,
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "stats": {
                "adaptive": {
                    "timing": {
                        "transport_delay_sec_ema": 9,
                        "settle_sec_ema": 7,
                        "observations": 4,
                    }
                }
            }
        }
    }
    task = _make_task(corr=corr)
    pid_repo = _MockPidStateRepository()
    handler = _make_handler(pid_repo=pid_repo)

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.due_delay_sec == 16
    assert pid_repo.upsert_calls[-1]["updates"][0]["hold_until"] == NOW + timedelta(seconds=16)


async def test_corr_wait_ec_stale_telemetry_logs_freshness_event(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ec_stale=True)
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.due_delay_sec == 30.0
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_FRESHNESS"
    payload = create_event.await_args.args[2]
    assert payload["sensor_scope"] == "observe_window"
    assert payload["sensor_type"] == "EC"
    assert payload["pid_type"] == "ec"
    assert payload["retry_after_sec"] == 30.0


async def test_corr_wait_ec_window_not_ready_logs_event(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=2,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=2), "value": 1.4},
        {"ts": NOW, "value": 1.4},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=_make_task(corr=corr), plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_ec"
    assert outcome.due_delay_sec == 2
    create_event.assert_awaited_once()
    assert create_event.await_args.args[1] == "CORRECTION_SKIPPED_WINDOW_NOT_READY"
    payload = create_event.await_args.args[2]
    assert payload["sensor_scope"] == "observe_window"
    assert payload["sensor_type"] == "EC"
    assert payload["pid_type"] == "ec"
    assert payload["reason"] == "insufficient_samples"
    assert payload["retry_after_sec"] == 2


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


async def test_corr_prepare_recirc_imminent_deadline_skips_probe_and_exhausts_window():
    corr = _base_corr(corr_step="corr_check", attempt=4, ec_attempt=2, ph_attempt=1)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_deadline_at=NOW + timedelta(seconds=4),
        stage_retry_count=1,
    )
    monitor = _MockRuntimeMonitor(ph=6.4, ec=1.2)
    gateway = _MockGateway()
    handler = _make_handler(monitor=monitor, gateway=gateway)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 2
    assert gateway.calls == []
    assert monitor.irr_reads == 0


async def test_corr_prepare_recirc_six_seconds_to_deadline_still_skips_probe():
    corr = _base_corr(corr_step="corr_check", attempt=4, ec_attempt=2, ph_attempt=1)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_deadline_at=NOW + timedelta(seconds=6),
        stage_retry_count=1,
    )
    monitor = _MockRuntimeMonitor(ph=6.4, ec=1.2)
    gateway = _MockGateway()
    handler = _make_handler(monitor=monitor, gateway=gateway)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 2
    assert gateway.calls == []
    assert monitor.irr_reads == 0


async def test_corr_prepare_recirc_late_cooldown_retry_exhausts_window_before_next_probe():
    class _PlannerCooldownStub:
        def is_within_tolerance(self, **kwargs):
            return False

        def build_dose_plan(self, **kwargs):
            return DosePlan(retry_after_sec=2.0)

    corr = _base_corr(corr_step="corr_check", attempt=1, ec_attempt=2, ph_attempt=1)
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_deadline_at=NOW + timedelta(seconds=9),
        stage_retry_count=2,
    )
    monitor = _MockRuntimeMonitor(ph=6.8, ec=0.7)
    gateway = _MockGateway()
    handler = _make_handler(
        monitor=monitor,
        gateway=gateway,
        pid_repo=_MockPidStateRepository(),
        planner=_PlannerCooldownStub(),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=dict(RUNTIME)), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["commands"][0].channel == "storage_state"
    assert monitor.irr_reads == 1


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


async def test_corr_irrigation_deadline_preempts_to_ready_when_targets_reached():
    corr = _base_corr(corr_step="corr_wait_ph", attempt=4, ec_attempt=3, ph_attempt=3)
    task = _make_task(
        corr=corr,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_deadline_at=NOW - timedelta(seconds=1),
    )
    handler = _make_handler(monitor=_MockRuntimeMonitor(ph=6.0, ec=2.0))

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "irrigation_stop_to_ready"


async def test_corr_irrigation_deadline_preempts_to_recovery_when_targets_not_reached():
    corr = _base_corr(corr_step="corr_wait_ec", attempt=4, ec_attempt=3, ph_attempt=3)
    task = _make_task(
        corr=corr,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        stage_deadline_at=NOW - timedelta(seconds=1),
    )
    handler = _make_handler(monitor=_MockRuntimeMonitor(ph=6.4, ec=1.2))

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "irrigation_stop_to_recovery"


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
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.1,
            "kd": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
        "ph": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
    }
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
        named_plans = _MockPlan().named_plans

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


async def test_corr_check_logs_discarded_dose_with_runtime_details(monkeypatch: pytest.MonkeyPatch):
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
        "ph": {
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
    }
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 10.0, "min_effective_ml": 0.0},
        },
        "ph_up": {"node_uid": "ph-node", "channel": "ph_up_pump"},
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }
    runtime["prepare_tolerance"] = {"ph_pct": 1.0, "ec_pct": 0.1}
    runtime["target_ec_min"] = 2.0
    runtime["target_ec_max"] = 2.05
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    create_event = AsyncMock(return_value=None)
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", create_event)

    class _PlanWithDiscard:
        named_plans = _MockPlan().named_plans

    _PlanWithDiscard.runtime = runtime

    monitor = _MockRuntimeMonitor(ph=6.0, ec=1.98)
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_PlanWithDiscard(), stage_def=None, now=NOW)

    assert outcome.kind in {"exit_correction", "enter_correction"}
    assert create_event.await_count >= 1
    discarded_call = next(
        call for call in create_event.await_args_list
        if call.args[1] == "CORRECTION_SKIPPED_DOSE_DISCARDED"
    )
    discarded_payload = discarded_call.args[2]
    assert discarded_payload["reason"] == "below_min_dose_ms"
    assert discarded_payload["computed_duration_ms"] == 10
    assert discarded_payload["min_dose_ms"] == 50


async def test_corr_check_uses_decision_window_grace_for_late_sample_and_reaches_dose_step(
    monkeypatch: pytest.MonkeyPatch,
):
    """A fresh but slightly late telemetry cadence must not block dosing with only 2 samples in a strict 6s window."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.1,
            "kd": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
        "ph": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "min_effect_fraction": 0.25,
                "stability_max_slope": 0.05,
                "telemetry_period_sec": 2,
                "no_effect_consecutive_limit": 3,
            },
        },
    }
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
    runtime["correction_by_phase"] = dict(runtime.get("correction_by_phase") or {})
    runtime["correction_by_phase"]["solution_fill"] = dict(runtime["correction"])
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=0.5,
        ph_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 6.0},
            {"ts": NOW - timedelta(seconds=5), "value": 6.0},
            {"ts": NOW - timedelta(seconds=3), "value": 6.0},
        ],
        ec_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 0.5},
            {"ts": NOW - timedelta(seconds=5), "value": 0.5},
            {"ts": NOW - timedelta(seconds=3), "value": 0.5},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dose_ec"
    assert outcome.correction.needs_ec is True
    assert outcome.correction.ec_duration_ms is not None
    assert outcome.correction.ec_duration_ms > 0


async def test_corr_check_prepare_recirc_keeps_ec_and_ph_in_same_correction_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
    )
    runtime = deepcopy(RUNTIME)
    runtime["prepare_tolerance"] = {"ph_pct": 1.0, "ec_pct": 1.0}
    runtime["target_ph_min"] = 5.9
    runtime["target_ph_max"] = 6.1
    runtime["target_ec_min"] = 1.9
    runtime["target_ec_max"] = 2.1
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.01,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
        },
        "ph": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.01,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
        },
    }
    runtime["correction"]["actuators"] = {
        "ec": {
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
        "ph_up": None,
        "ph_down": {
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0},
        },
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 50,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }
    runtime["correction_by_phase"] = dict(runtime.get("correction_by_phase") or {})
    runtime["correction_by_phase"]["tank_recirc"] = dict(runtime["correction"])
    monitor = _MockRuntimeMonitor(
        ph=6.4,
        ec=1.6,
        ph_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 6.4},
            {"ts": NOW - timedelta(seconds=5), "value": 6.4},
            {"ts": NOW - timedelta(seconds=3), "value": 6.4},
        ],
        ec_samples=[
            {"ts": NOW - timedelta(seconds=7), "value": 1.6},
            {"ts": NOW - timedelta(seconds=5), "value": 1.6},
            {"ts": NOW - timedelta(seconds=3), "value": 1.6},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dose_ec"
    assert outcome.correction.needs_ec is True
    assert outcome.correction.needs_ph_down is True
    assert outcome.correction.ph_channel == "ph_down_pump"
    assert outcome.correction.ph_duration_ms is not None
    assert outcome.correction.ph_duration_ms > 0


async def test_corr_check_prioritizes_pending_ph_after_ec_observe_when_both_still_needed():
    class _PlannerStub:
        def is_within_tolerance(self, **kwargs):
            return False

        def build_dose_plan(self, **kwargs):
            return DosePlan(
                needs_ec=True,
                ec_node_uid="ec-node",
                ec_channel="ec_pump",
                ec_amount_ml=2.0,
                ec_duration_ms=2000,
                needs_ph_down=True,
                ph_node_uid="ph-node",
                ph_channel="ph_down_pump",
                ph_amount_ml=1.5,
                ph_duration_ms=1500,
            )

    corr = _base_corr(
        corr_step="corr_check",
        needs_ph_down=True,
        ph_node_uid="ph-node",
        ph_channel="ph_down_pump",
        ph_duration_ms=1500,
        ph_amount_ml=1.5,
    )
    task = _make_task(corr=corr, current_stage="prepare_recirculation_check", workflow_phase="tank_recirc")
    handler = _make_handler(
        monitor=_MockRuntimeMonitor(ph=6.4, ec=1.6),
        pid_repo=_MockPidStateRepository(),
        planner=_PlannerStub(),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=dict(RUNTIME)), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_dose_ph"
    assert outcome.correction.needs_ec is True
    assert outcome.correction.needs_ph_down is True
    assert outcome.correction.ec_channel == "ec_pump"
    assert outcome.correction.ph_channel == "ph_down_pump"


async def test_corr_check_unready_decision_window_retries_on_telemetry_period_when_missing_one_sample() -> None:
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["controllers"] = {
        "ec": {
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "telemetry_period_sec": 2,
                "stability_max_slope": 0.05,
            },
        },
        "ph": {
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {
                "observe_poll_sec": 2,
                "window_min_samples": 3,
                "decision_window_sec": 6,
                "telemetry_period_sec": 2,
                "stability_max_slope": 0.05,
            },
        },
    }
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=0.5,
        ph_samples=[
            {"ts": NOW - timedelta(seconds=5), "value": 6.0},
            {"ts": NOW - timedelta(seconds=3), "value": 6.0},
        ],
        ec_samples=[
            {"ts": NOW - timedelta(seconds=5), "value": 0.5},
            {"ts": NOW - timedelta(seconds=3), "value": 0.5},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    # При нехватке ровно одного sample correction не должна зависать на coarse 30s retry.
    assert outcome.kind == "enter_correction"
    assert outcome.due_delay_sec == 2.0
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"


async def test_corr_check_no_pid_repo_does_not_crash():
    """corr_check must not fail when pid_state_repository is None (backward compat)."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # within tolerance → no dose
    handler = _make_handler(monitor=monitor, pid_repo=None)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    # Should succeed regardless (no crash when repo is None)
    assert outcome.kind in {"enter_correction", "exit_correction"}


async def test_corr_check_stale_telemetry_retries_in_30s():
    """corr_check: stale decision window telemetry должен ретраиться, а не падать."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph_stale=True)
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 30.0


async def test_corr_check_stale_telemetry_uses_configured_retry_delay():
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["telemetry_stale_retry_sec"] = 17
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    monitor = _MockRuntimeMonitor(ph_stale=True)
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 17


# ── Баг #4: проверка NaN/Inf телеметрии ──────────────────────────────────────


async def test_corr_check_non_finite_ph_retries_in_30s(monkeypatch):
    """NaN в pH-телеметрии должен вызывать retry через 30s, не исключение."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=math.nan, ec=2.0)
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 30.0


async def test_corr_check_non_finite_ec_retries_in_30s(monkeypatch):
    """Inf в EC-телеметрии должен вызывать retry через 30s, не исключение."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=math.inf)
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 30.0


async def test_corr_check_non_finite_telemetry_uses_configured_decision_window_retry(monkeypatch):
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["decision_window_retry_sec"] = 19
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    monitor = _MockRuntimeMonitor(ph=math.nan, ec=2.0)
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 19


# ── Баг #5: проверка уровня воды перед коррекцией ────────────────────────────


async def test_corr_check_low_water_level_skips_correction_60s(monkeypatch):
    """Низкий уровень воды должен пропускать коррекцию с задержкой 60s."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5, solution_min_triggered=False)  # явно вне допуска
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 60.0


async def test_corr_check_low_water_level_uses_configured_retry_delay(monkeypatch):
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["low_water_retry_sec"] = 91
    runtime["correction_by_phase"] = {"solution_fill": dict(runtime["correction"])}
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5, solution_min_triggered=False)
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 91


async def test_corr_check_ok_water_level_allows_correction(monkeypatch):
    """Нормальный уровень воды не блокирует коррекцию — тест продолжается до tolerance-check."""
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # within tolerance
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    # Нормальный уровень воды → не задержка 60s, а нормальный выход (success)
    assert not (outcome.kind == "enter_correction" and outcome.due_delay_sec == 60.0)


async def test_corr_check_uses_probe_snapshot_for_solution_min(monkeypatch):
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr, current_stage="solution_fill_check", workflow_phase="tank_filling")
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=2.0,
        solution_min_triggered=False,
        has_level=True,
        level_stale=True,
        irr_snapshot={
            "valve_clean_supply": True,
            "valve_solution_fill": True,
            "valve_solution_supply": True,
            "pump_main": True,
            "level_solution_min": True,
        },
    )
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind in {"enter_correction", "exit_correction"}


async def test_corr_check_irrigation_phase_falls_back_to_solution_fill_process_calibration(monkeypatch):
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr, current_stage="irrigation_check", workflow_phase="irrigating")
    runtime = deepcopy(RUNTIME)
    runtime["process_calibrations"] = {
        "solution_fill": deepcopy(RUNTIME["process_calibrations"]["solution_fill"]),
    }
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)
    handler = _make_handler(monitor=monitor)
    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        AsyncMock(return_value=None),
    )

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind in {"enter_correction", "exit_correction"}


async def test_corr_dose_ec_invalid_sequence_json_fails_closed() -> None:
    corr = _base_corr(corr_step="corr_dose_ec", ec_dose_sequence_json="{bad-json")
    task = _make_task(corr=corr)
    handler = _make_handler()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "corr_dose_ec_bad_sequence"


async def test_corr_check_fails_when_pid_state_persist_fails() -> None:
    class _FailingPidRepo(_MockPidStateRepository):
        async def upsert_states(self, *, zone_id, now, updates):
            raise RuntimeError("db down")

    pid_repo = _FailingPidRepo()
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = dict(RUNTIME)
    runtime["correction"] = dict(runtime["correction"])
    runtime["correction"]["controllers"] = {
        "ec": {
            "kp": 1.0,
            "ki": 0.1,
            "kd": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {"decision_window_sec": 6, "window_min_samples": 3, "telemetry_period_sec": 2},
        },
        "ph": {
            "kp": 1.0,
            "ki": 0.0,
            "kd": 0.0,
            "deadband": 0.05,
            "max_dose_ml": 10.0,
            "min_interval_sec": 0,
            "max_integral": 20.0,
            "telemetry_period_sec": 2,
            "window_min_samples": 3,
            "observe": {"decision_window_sec": 6, "window_min_samples": 3, "telemetry_period_sec": 2},
        },
    }
    runtime["correction"]["actuators"] = {
        "ec": {"node_uid": "ec-node", "channel": "ec_pump", "calibration": {"ml_per_sec": 2.0, "min_effective_ml": 0.0}},
        "ph_up": {"node_uid": "ph-node", "channel": "ph_up_pump"},
        "ph_down": None,
    }
    runtime["correction"]["pump_calibration"] = {
        "min_dose_ms": 200,
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 100.0,
    }

    class _PlanWithCalib:
        named_plans = _MockPlan().named_plans

    _PlanWithCalib.runtime = runtime

    monitor = _MockRuntimeMonitor(ph=6.0, ec=0.5)
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_PlanWithCalib(), stage_def=None, now=NOW)
    assert exc_info.value.code == "corr_pid_state_persist_failed"


async def test_corr_check_fails_closed_when_observe_decision_window_missing() -> None:
    corr = _base_corr(corr_step="corr_check")
    task = _make_task(corr=corr)
    runtime = deepcopy(RUNTIME)
    del runtime["process_calibrations"]["solution_fill"]["meta"]["observe"]["decision_window_sec"]
    monitor = _MockRuntimeMonitor(ph=6.0, ec=0.5)
    handler = _make_handler(monitor=monitor)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert exc_info.value.code == "zone_correction_config_missing_critical"


# ---------------------------------------------------------------------------
# Attempt reset on reaction / accumulation on no-reaction
# ---------------------------------------------------------------------------

async def test_corr_wait_ec_solution_fill_reaction_detected_resets_all_attempt_counters():
    """В solution_fill после дозы EC с измеримой реакцией счётчики сбрасываются в 0.

    Это позволяет циклу коррекции работать неограниченно долго, пока дозирующее
    оборудование даёт отклик. Счётчик no_effect_count (отдельный) накапливается
    только при отсутствии реакции и вызывает алерт после no_effect_limit раз.
    """
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=4,
        ec_attempt=3,
        ph_attempt=2,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 1,
        }
    }
    task = _make_task(corr=corr)
    # EC jump 1.0 → 1.45: effect = 0.45, expected = 0.2 * 2.0 = 0.4, fraction = 0.25 → has effect
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.35},
        {"ts": NOW - timedelta(seconds=2), "value": 1.40},
        {"ts": NOW, "value": 1.45},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    c = outcome.correction
    assert c.corr_step == "corr_check"
    assert c.attempt == 0     # сброшен
    assert c.ec_attempt == 0  # сброшен
    assert c.ph_attempt == 0  # сброшен


async def test_corr_wait_ec_prepare_recirc_reaction_resets_attempt_counters_and_next_check_continues():
    class _PlannerNeedsEcOnly:
        def is_within_tolerance(self, **kwargs):
            return False

        def build_dose_plan(self, **kwargs):
            return DosePlan(
                needs_ec=True,
                ec_node_uid="ec-node",
                ec_channel="ec_pump",
                ec_amount_ml=2.0,
                ec_duration_ms=1000,
            )

    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=1,
        max_attempts=5,
        ec_attempt=1,
        ec_max_attempts=1,
        ph_attempt=0,
        ph_max_attempts=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_retry_count=2,
    )
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=1.4,
        ec_samples=[
            {"ts": NOW - timedelta(seconds=4), "value": 1.35},
            {"ts": NOW - timedelta(seconds=2), "value": 1.4},
            {"ts": NOW, "value": 1.45},
        ],
    )
    handler = _make_handler(
        monitor=monitor,
        pid_repo=_MockPidStateRepository(),
        planner=_PlannerNeedsEcOnly(),
    )

    observe_outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert observe_outcome.kind == "enter_correction"
    assert observe_outcome.correction is not None
    assert observe_outcome.correction.corr_step == "corr_check"
    assert observe_outcome.correction.attempt == 0
    assert observe_outcome.correction.ec_attempt == 0
    assert observe_outcome.correction.ph_attempt == 0

    check_outcome = await handler.run(
        task=_make_task(
            corr=observe_outcome.correction,
            current_stage="prepare_recirculation_check",
            workflow_phase="tank_recirc",
            stage_retry_count=2,
        ),
        plan=_MockPlan(runtime=runtime),
        stage_def=None,
        now=NOW,
    )

    assert check_outcome.kind == "enter_correction"
    assert check_outcome.correction is not None
    assert check_outcome.correction.corr_step == "corr_dose_ec"


async def test_corr_wait_ec_prepare_recirc_late_reaction_exhausts_window_before_next_check():
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=1,
        max_attempts=5,
        ec_attempt=1,
        ec_max_attempts=3,
        ph_attempt=0,
        ph_max_attempts=3,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(
        corr=corr,
        current_stage="prepare_recirculation_check",
        workflow_phase="tank_recirc",
        stage_deadline_at=NOW + timedelta(seconds=8),
        stage_retry_count=2,
    )
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=1.4,
        ec_samples=[
            {"ts": NOW - timedelta(seconds=4), "value": 1.35},
            {"ts": NOW - timedelta(seconds=2), "value": 1.4},
            {"ts": NOW, "value": 1.45},
        ],
    )
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler._run_wait_observe(
        task=task,
        plan=_MockPlan(runtime=runtime),
        corr=corr,
        now=NOW,
        pid_type="ec",
        sensor_type="EC",
    )

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"


async def test_corr_wait_ec_no_reaction_increments_attempt_counter():
    """При отсутствии реакции счётчик attempt должен накапливаться (не сбрасываться).

    Когда attempt достигнет max_attempts, сработает exhausted-алерт.
    """
    corr = _base_corr(
        corr_step="corr_wait_ec",
        attempt=1,
        ec_attempt=1,
        needs_ec=True,
        ec_amount_ml=2.0,
        ec_node_uid="ec-node",
        ec_channel="ec_pump",
        ec_duration_ms=1000,
        wait_until=NOW - timedelta(seconds=1),
    )
    runtime = dict(RUNTIME)
    runtime["pid_state"] = {
        "ec": {
            "last_dose_at": NOW - timedelta(seconds=12),
            "last_measured_value": 1.0,
            "no_effect_count": 0,
        }
    }
    task = _make_task(corr=corr)
    # EC barely moves 1.0 → 1.01: effect = 0.01, expected = 0.4, fraction = 0.25 → no effect
    monitor = _MockRuntimeMonitor(ec_samples=[
        {"ts": NOW - timedelta(seconds=4), "value": 1.00},
        {"ts": NOW - timedelta(seconds=2), "value": 1.01},
        {"ts": NOW, "value": 1.01},
    ])
    handler = _make_handler(monitor=monitor, pid_repo=_MockPidStateRepository())

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "enter_correction"
    c = outcome.correction
    assert c.corr_step == "corr_check"
    assert c.attempt == 2     # накоплен (1 + 1)
    assert c.ec_attempt == 1  # не изменился (не сброшен)


# ── B7: PlannerConfigurationError translation ───────────────────────

async def test_corr_check_translates_planner_config_error(monkeypatch) -> None:
    """build_dose_plan raising PlannerConfigurationError → typed TaskExecutionError.

    Regression for audit B7: previously the error bubbled up unmapped and
    execute_task translated it into an anonymous Ae3LiteError with whatever
    code the planner happened to carry. The handler now catches it, logs a
    CORRECTION_PLANNER_CONFIG_INVALID zone event, and raises
    TaskExecutionError("corr_planner_config_invalid", ...).
    """
    from ae3lite.domain.errors import PlannerConfigurationError
    from ae3lite.domain.services.correction_planner import CorrectionPlanner

    class _FailingPlanner(CorrectionPlanner):
        def build_dose_plan(self, **kwargs):  # type: ignore[override]
            raise PlannerConfigurationError(
                "Для ec component calcium в режиме multi_sequential требуется process gain"
            )

    events: list[tuple[int, str, dict]] = []

    async def _capture_event(zone_id, event_type, payload):
        events.append((zone_id, event_type, dict(payload)))

    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        _capture_event,
    )

    corr = _base_corr(corr_step="corr_check", attempt=0, max_attempts=5)
    task = _make_task(corr=corr)
    # PH=8.0, EC=0.5 — far from targets (6.0 / 2.0, tolerance 15/25%).
    # Ensures the handler reaches build_dose_plan instead of early success.
    monitor = _MockRuntimeMonitor(ph=8.0, ec=0.5)
    handler = _make_handler(monitor=monitor, planner=_FailingPlanner())

    with pytest.raises(TaskExecutionError) as excinfo:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert excinfo.value.code == "corr_planner_config_invalid"
    assert "process gain" in str(excinfo.value)

    # And a CORRECTION_PLANNER_CONFIG_INVALID zone event must be logged for ops.
    planner_invalid_events = [
        event for event in events if event[1] == "CORRECTION_PLANNER_CONFIG_INVALID"
    ]
    assert len(planner_invalid_events) == 1
    payload = planner_invalid_events[0][2]
    assert "process gain" in payload["reason"]
    assert payload["current_ph"] == 8.0


# ══════════════════════════════════════════════════════════════════════════════
# Safety gates: E-STOP, no-effect block, auto-resolve no_effect_count
# ══════════════════════════════════════════════════════════════════════════════


async def test_corr_check_raises_on_recent_emergency_stop(monkeypatch: pytest.MonkeyPatch):
    """L1: если в zone_events есть свежий EMERGENCY_STOP_ACTIVATED,
    correction прерывается с TaskExecutionError('emergency_stop_activated')."""
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=5.8, ec=1.85)
    handler = _make_handler(monitor=monitor)

    # Мокаем _read_recent_storage_event чтобы вернуть свежий E-STOP event.
    async def _fake_read(*, task, event_types, max_age_sec):
        if "EMERGENCY_STOP_ACTIVATED" in event_types:
            return {"event_id": 12345, "type": "EMERGENCY_STOP_ACTIVATED"}
        return None
    monkeypatch.setattr(handler, "_read_recent_storage_event", _fake_read)

    from ae3lite.domain.errors import TaskExecutionError
    with pytest.raises(TaskExecutionError) as excinfo:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert excinfo.value.code == "emergency_stop_activated"


async def test_corr_check_success_resets_no_effect_counts(monkeypatch: pytest.MonkeyPatch):
    """M5: успешный CORRECTION_COMPLETE вызывает reset_no_effect_counts в pid_state_repository.
    Автоматически снимает block_on_active_no_effect_alert для следующего tick."""
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # в пределах tolerance
    pid_repo = _MockPidStateRepository()
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "exit_correction"
    assert outcome.correction.outcome_success is True
    # Critical: после успеха no_effect_count сброшен для этой зоны.
    assert pid_repo.no_effect_resets == [task.zone_id]


async def test_corr_check_blocked_by_active_no_effect_alert(monkeypatch: pytest.MonkeyPatch):
    """M6: если safety.block_on_active_no_effect_alert=True и pid_state.no_effect_count
    достиг no_effect_consecutive_limit, correction skip'ается с retry=60s
    и пишется CORRECTION_SKIPPED_BY_ALERT_BLOCK event."""
    events: list[tuple[int, str, dict]] = []

    async def _capture_event(zone_id, event_type, payload):
        events.append((zone_id, event_type, dict(payload) if payload else {}))

    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", _capture_event)
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=5.8, ec=1.85)
    handler = _make_handler(monitor=monitor)

    runtime = deepcopy(RUNTIME)
    # Включаем safety gate и задаём limit для EC observe.
    runtime["correction"]["safety"] = {"block_on_active_no_effect_alert": True}
    runtime["correction"]["controllers"]["ec"]["observe"] = {"no_effect_consecutive_limit": 3}
    # pid_state показывает что лимит достигнут.
    runtime["pid_state"] = {"ec": {"no_effect_count": 3}}

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)

    assert outcome.kind == "retry"
    assert outcome.due_delay_sec == 60
    block_events = [e for e in events if e[1] == "CORRECTION_SKIPPED_BY_ALERT_BLOCK"]
    assert len(block_events) == 1
    payload = block_events[0][2]
    assert payload["pid_type"] == "ec"
    assert payload["no_effect_count"] == 3
    assert payload["no_effect_limit"] == 3
    assert payload["reason"] == "active_no_effect_alert_blocks_correction"


async def test_corr_check_not_blocked_when_block_flag_false(monkeypatch: pytest.MonkeyPatch):
    """M6 negative: если block_on_active_no_effect_alert=False, коррекция идёт
    нормально даже при no_effect_count >= limit (только alert, не block)."""
    monkeypatch.setattr("ae3lite.application.handlers.correction.create_zone_event", AsyncMock(return_value=None))
    corr = _base_corr(corr_step="corr_check", attempt=1, max_attempts=5)
    task = _make_task(corr=corr)
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)  # в tolerance → exit success
    pid_repo = _MockPidStateRepository()
    handler = _make_handler(monitor=monitor, pid_repo=pid_repo)

    runtime = deepcopy(RUNTIME)
    runtime["correction"]["safety"] = {"block_on_active_no_effect_alert": False}
    runtime["correction"]["controllers"]["ec"]["observe"] = {"no_effect_consecutive_limit": 3}
    runtime["pid_state"] = {"ec": {"no_effect_count": 5}}

    outcome = await handler.run(task=task, plan=_MockPlan(runtime=runtime), stage_def=None, now=NOW)
    # НЕ retry — флаг выключен, коррекция прошла до success.
    assert outcome.kind == "exit_correction"
