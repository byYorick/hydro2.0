"""Unit tests: irrigation pH-only (needs_ec=false)."""

from __future__ import annotations

from ae3lite.application.services.workflow_topology import TWO_TANK
from ae3lite.domain.services.correction_transition_policy import CorrectionTransitionPolicy
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_planner import CorrectionPlanner


def _cfg() -> dict:
    return {
        "controllers": {
            "ph": {"kp": 5, "ki": 0, "kd": 0, "deadband": 0.05, "max_dose_ml": 20, "min_interval_sec": 0},
            "ec": {"kp": 30, "ki": 0, "kd": 0, "deadband": 0.1, "max_dose_ml": 50, "min_interval_sec": 0},
        },
        "dose_ec_channel": "pump_a",
        "dose_ph_up_channel": "pump_base",
        "dose_ph_down_channel": "pump_acid",
        "max_ec_dose_ml": 50,
        "max_ph_dose_ml": 20,
        "solution_volume_l": 100.0,
        "pump_calibration": {"min_dose_ms": 50, "ml_per_sec_min": 0.01, "ml_per_sec_max": 100},
    }


def test_irrigation_planner_needs_ec_false() -> None:
    planner = CorrectionPlanner()
    plan = planner.build_dose_plan(
        current_ph=5.5,
        current_ec=0.8,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_cfg(),
        workflow_phase="irrigating",
        process_calibrations={"irrigation": {"ph_up_gain_per_ml": 0.1, "ec_gain_per_ml": 0.2}},
        ph_up_actuator={"node_uid": "ph-1", "channel": "pump_base", "calibration": {"ml_per_sec": 1.0}},
        ec_actuators={
            "calcium": {"node_uid": "ec-1", "channel": "pump_b", "calibration": {"ml_per_sec": 1.0}},
        },
    )
    assert plan.needs_ec is False
    assert plan.needs_ph_up is True


def test_topology_has_no_irrigation_recovery() -> None:
    assert "irrigation_recovery_check" not in TWO_TANK
    assert "irrigation_stop_to_recovery" not in TWO_TANK
    assert "irrigation_stop_to_ready" in TWO_TANK


def test_deadline_policy_always_ready() -> None:
    corr = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=5,
        ec_max_attempts=0,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=30,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
    )
    outcome = CorrectionTransitionPolicy.decide_stage_deadline_transition(
        corr=corr,
        current_stage="irrigation_check",
        stage_retry_count=0,
        deadline_reached=True,
        targets_reached=False,
        recovery_enabled=True,
    )
    assert outcome is not None
    assert outcome.next_stage == "irrigation_stop_to_ready"
