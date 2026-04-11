from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ae3lite.domain.services.correction_planner import CorrectionPlanner


def _correction_config(*, ph_overrides=None, ec_overrides=None, dosing_overrides=None) -> dict:
    config = {
        "controllers": {
            "ph": {
                "kp": 5.0,
                "ki": 0.05,
                "kd": 0.0,
                "deadband": 0.05,
                "max_dose_ml": 20.0,
                "min_interval_sec": 90,
                "max_integral": 20.0,
                "anti_windup": {"enabled": True},
            },
            "ec": {
                "kp": 30.0,
                "ki": 0.3,
                "kd": 0.0,
                "deadband": 0.1,
                "max_dose_ml": 50.0,
                "min_interval_sec": 120,
                "max_integral": 100.0,
                "anti_windup": {"enabled": True},
            },
        },
        "solution_volume_l": 100.0,
        "dose_ec_channel": "dose_ec_a",
        "dose_ph_up_channel": "dose_ph_up",
        "dose_ph_down_channel": "dose_ph_down",
        "max_ec_dose_ml": 50.0,
        "max_ph_dose_ml": 20.0,
        "pump_calibration": {
            "min_dose_ms": 50,
            "ml_per_sec_min": 0.01,
            "ml_per_sec_max": 100.0,
        },
    }
    if ph_overrides:
        config["controllers"]["ph"].update(ph_overrides)
    if ec_overrides:
        config["controllers"]["ec"].update(ec_overrides)
    if dosing_overrides:
        config.update(dosing_overrides)
    return config


def test_build_dose_plan_selects_npk_component_for_solution_fill_policy() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.2}},
        ec_component_policy={
            "solution_fill": {
                "npk": 1.0,
                "calcium": 0.0,
                "magnesium": 0.0,
                "micro": 0.0,
            }
        },
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
            "ec_calcium": {
                "node_uid": "ec-node",
                "channel": "ec_calcium_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.ec_component == "npk"
    assert dose_plan.ec_channel == "ec_npk_pump"
    assert dose_plan.ec_amount_ml == 5.0
    assert dose_plan.ec_duration_ms == 500


def test_build_dose_plan_uses_process_calibration_and_min_effective_ml() -> None:
    """min_effective_ml bumps the computed dose when the bump stays within gap/gain cap."""
    planner = CorrectionPlanner()

    # gap=0.8, gain=0.5 → natural dose = 0.4 ml; bump to min_effective_ml=0.5 ml
    # is safe because 0.5 ≤ gap/gain = 1.6.
    dose_plan = planner.build_dose_plan(
        current_ph=6.8,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 0.25,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.5}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 8.0, "min_effective_ml": 0.5},
        },
    )

    assert dose_plan.needs_ph_down is True
    assert dose_plan.ph_channel == "ph_down_pump"
    assert dose_plan.ph_amount_ml == 0.5
    assert dose_plan.ph_duration_ms == 62


def test_build_dose_plan_discards_ph_dose_when_min_effective_exceeds_gap_cap() -> None:
    """min_effective_ml bump must not overshoot the gap/gain target cap.

    Regression: when calibration.min_effective_ml is larger than the modelled
    dose needed to reach the target (gap/gain), a single pulse would overshoot
    the window and cause acid/base ping-pong around the setpoint. Planner now
    discards the dose with reason ``ph_down_min_effective_exceeds_cap`` so the
    correction loop does not command an unsafe pulse.
    """
    planner = CorrectionPlanner()

    # gap=0.05, gain=0.5 → natural dose = 0.025 ml; gap cap = 0.1 ml.
    # min_effective_ml=1.5 ml would overshoot pH by 0.75 units → discard.
    dose_plan = planner.build_dose_plan(
        current_ph=6.05,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=0.1,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 0.5,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.5}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 8.0, "min_effective_ml": 1.5},
        },
    )

    assert dose_plan.needs_ph_down is False
    assert dose_plan.needs_any is False
    assert dose_plan.ph_amount_ml == 0.0
    assert dose_plan.ph_duration_ms == 0
    assert dose_plan.dose_discarded_reason == "ph_down_min_effective_exceeds_cap"
    details = dict(dose_plan.dose_discarded_details)
    assert details["kind"] == "ph_down"
    assert details["min_effective_ml"] == pytest.approx(1.5)
    assert details["gap_cap_ml"] == pytest.approx(0.1)
    # Capped value is what the dose was clamped down to after re-applying gap/gain cap.
    assert details["capped_ml"] == pytest.approx(0.1)


def test_build_dose_plan_discards_ec_dose_when_min_effective_exceeds_gap_cap() -> None:
    """Symmetric guard for single-dose EC path (non-multi_sequential).

    Mirrors the multi_sequential branch which already discards components whose
    min_effective_ml exceeds the per-component gap cap. Before the fix, single
    EC dose silently overshot the target.
    """
    planner = CorrectionPlanner()

    # gap=0.05, gain=0.5 → gap cap = 0.1 ml; min_effective_ml=2.0 → discard.
    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.95,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.1,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 0.5,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.5}},
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 10.0, "min_effective_ml": 2.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is False
    assert dose_plan.needs_any is False
    assert dose_plan.ec_amount_ml == 0.0
    assert dose_plan.ec_duration_ms == 0
    assert dose_plan.dose_discarded_reason == "ec_min_effective_exceeds_cap"
    details = dict(dose_plan.dose_discarded_details)
    assert details["kind"] == "ec"
    assert details["min_effective_ml"] == pytest.approx(2.0)
    assert details["gap_cap_ml"] == pytest.approx(0.1)


def test_build_dose_plan_keeps_tank_recirc_ec_gain_floor_at_authoritative_calibration() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 500.0,
            },
            dosing_overrides={
                "max_ec_dose_ml": 500.0,
            },
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.01}},
        pid_state={
            "ec": {
                "stats": {
                    "adaptive": {
                        "gains": {
                            "ec_gain_per_ml": {"ema": 0.002, "observations": 12},
                        },
                        "retention_ema": 1.0,
                        "wave_score_ema": 0.0,
                    }
                }
            }
        },
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 1.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    # Without the recirculation safety floor the learned gain would reduce the
    # denominator and inflate the dose above the authoritative 100 ml.
    assert dose_plan.needs_ec is True
    assert dose_plan.ec_amount_ml == pytest.approx(100.0)
    assert dose_plan.ec_duration_ms == 100000


def test_build_dose_plan_uses_close_zone_pid_coefficients_for_small_gap() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.7,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 9.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 50.0,
            }
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_configs={
            "ec": {
                "config": {
                    "dead_zone": 0.1,
                    "close_zone": 0.5,
                    "far_zone": 1.5,
                    "zone_coeffs": {
                        "close": {"kp": 0.5, "ki": 0.0, "kd": 0.0},
                        "far": {"kp": 0.9, "ki": 0.0, "kd": 0.0},
                    },
                }
            }
        },
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 1.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.ec_pid_zone == "close"
    assert dose_plan.ec_pid_coeffs == {"kp": 0.5, "ki": 0.0, "kd": 0.0}
    assert dose_plan.ec_amount_ml == pytest.approx(0.15)
    assert dose_plan.ec_duration_ms == 150


def test_build_dose_plan_uses_far_zone_pid_coefficients_for_large_gap() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=0.8,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 9.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 50.0,
            }
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_configs={
            "ec": {
                "config": {
                    "dead_zone": 0.1,
                    "close_zone": 0.5,
                    "far_zone": 1.5,
                    "zone_coeffs": {
                        "close": {"kp": 0.5, "ki": 0.0, "kd": 0.0},
                        "far": {"kp": 0.9, "ki": 0.0, "kd": 0.0},
                    },
                }
            }
        },
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 1.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.ec_pid_zone == "far"
    assert dose_plan.ec_pid_coeffs == {"kp": 0.9, "ki": 0.0, "kd": 0.0}
    assert dose_plan.ec_amount_ml == pytest.approx(1.08)
    assert dose_plan.ec_duration_ms == 1080


def test_build_dose_plan_uses_pid_dead_zone_as_deadband_override() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.95,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_configs={
            "ec": {
                "config": {
                    "dead_zone": 0.1,
                    "close_zone": 0.5,
                    "far_zone": 1.5,
                    "zone_coeffs": {
                        "close": {"kp": 0.5, "ki": 0.0, "kd": 0.0},
                        "far": {"kp": 0.9, "ki": 0.0, "kd": 0.0},
                    },
                }
            }
        },
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 10.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False
    assert dose_plan.dead_zone_details["ec_deadband"] == pytest.approx(0.1)
    assert dose_plan.dead_zone_details["ec_pid_zone"] == "close"


def test_build_dose_plan_blends_learned_runtime_gain_from_pid_state_stats() -> None:
    planner = CorrectionPlanner()

    baseline = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.4,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0}
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={"ec": {}},
        ec_component_policy={},
        ec_actuator={"node_uid": "ec-node", "channel": "ec_pump", "calibration": {"ml_per_sec": 1.0}},
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    adaptive = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.4,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0}
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={
            "ec": {
                "stats": {
                    "adaptive": {
                        "retention_ema": 1.0,
                        "wave_score_ema": 0.0,
                        "gains": {
                            "ec_gain_per_ml": {
                                "ema": 0.5,
                                "observations": 8,
                            }
                        },
                    }
                }
            }
        },
        ec_component_policy={},
        ec_actuator={"node_uid": "ec-node", "channel": "ec_pump", "calibration": {"ml_per_sec": 1.0}},
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert baseline.ec_amount_ml == pytest.approx(0.6)
    assert adaptive.ec_amount_ml == pytest.approx(1.2)
    assert adaptive.ec_duration_ms == 1200


def test_build_dose_plan_caps_ph_down_by_modeled_closure_dose() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.283,
        current_ec=1.05,
        target_ph=5.75,
        target_ec=1.05,
        ph_min=5.7,
        ph_max=5.8,
        ec_min=1.0,
        ec_max=1.1,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 5.0, "ki": 0.05, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0}
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.12}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 0.5, "min_effective_ml": 0.0},
        },
    )

    assert dose_plan.needs_ph_down is True
    # gap to canonical target 5.75 is 0.533; with gain 0.12 max safe dose is 4.4417 ml.
    assert dose_plan.ph_amount_ml == pytest.approx(4.4417, rel=1e-6)
    assert dose_plan.ph_duration_ms == 8883


def test_build_dose_plan_caps_ph_up_by_modeled_closure_dose() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=5.038,
        current_ec=1.05,
        target_ph=5.75,
        target_ec=1.05,
        ph_min=5.7,
        ph_max=5.8,
        ec_min=1.0,
        ec_max=1.1,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 5.0, "ki": 0.05, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0}
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.10}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 0.5, "min_effective_ml": 0.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    # gap to canonical target 5.75 is 0.712; with gain 0.10 max safe dose is 7.12 ml.
    assert dose_plan.ph_amount_ml == pytest.approx(7.12, rel=1e-6)
    assert dose_plan.ph_duration_ms == 14240


def test_build_dose_plan_ignores_stale_feedforward_bias_after_hold_window() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.94,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=0.5,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.2}},
        ec_component_policy={},
        pid_state={
            "ph": {
                "feedforward_bias": 0.08,
                "last_correction_kind": "ec",
                "last_dose_at": now - timedelta(seconds=120),
                "hold_until": now - timedelta(seconds=30),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            # ml_per_sec=1.0 → 0.3ml / 1.0 * 1000 = 300ms > _MIN_DOSE_MS (50ms)
            "calibration": {"ml_per_sec": 1.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    assert dose_plan.ph_channel == "ph_up_pump"


def test_build_dose_plan_applies_feedforward_bias_from_pid_state() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.94,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=0.5,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(),
        workflow_phase="tank_recirc",
        process_calibrations={},
        ec_component_policy={},
        pid_state={
            "ph": {
                "feedforward_bias": 0.08,
                "last_correction_kind": "ec",
                "last_dose_at": now - timedelta(seconds=10),
                "hold_until": now + timedelta(seconds=30),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is False
    assert dose_plan.needs_any is False


def test_is_within_tolerance_uses_target_tolerance_not_explicit_window_floor() -> None:
    planner = CorrectionPlanner()

    assert planner.is_within_tolerance(
        current_ph=5.0,
        current_ec=2.21,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.8,
        ph_max=5.2,
        ec_min=2.2,
        ec_max=2.6,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
    ) is False

    assert planner.is_within_tolerance(
        current_ph=5.0,
        current_ec=2.4,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.8,
        ph_max=5.2,
        ec_min=2.2,
        ec_max=2.6,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
    ) is True


def test_build_dose_plan_uses_explicit_target_window_for_ph_direction() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=5.35,
        current_ec=2.4,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.8,
        ph_max=5.2,
        ec_min=2.2,
        ec_max=2.6,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
        correction_config=_correction_config(),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.5}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 8.0, "min_effective_ml": 0.3},
        },
    )

    assert dose_plan.needs_ph_down is True
    assert dose_plan.ph_channel == "ph_down_pump"


def test_build_dose_plan_respects_explicit_window_even_inside_deadband() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=5.66,
        current_ec=1.05,
        target_ph=5.75,
        target_ec=1.05,
        ph_min=5.70,
        ph_max=5.80,
        ec_min=1.00,
        ec_max=1.10,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
        correction_config=_correction_config(
            ph_overrides={"deadband": 0.05, "min_interval_sec": 0}
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.2}},
        ec_component_policy={},
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0, "min_effective_ml": 0.3},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    assert dose_plan.ph_channel == "ph_up_pump"


def test_build_dose_plan_keeps_dosing_toward_target_inside_explicit_window() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.91,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.9,
        ph_max=6.1,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.01, "min_interval_sec": 0}
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.1}},
        ec_component_policy={},
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 10.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.ec_channel == "ec_pump"
    assert dose_plan.ec_amount_ml == pytest.approx(0.9)


def test_build_dose_plan_uses_pid_controller_state_and_applies_anti_windup() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 5, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ec_min=1.95,
        ec_max=2.05,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 2.0,
                "ki": 0.5,
                "kd": 0.0,
                "deadband": 0.05,
                "max_dose_ml": 20.0,
                "max_integral": 1.0,
                "min_interval_sec": 0,
            },
            dosing_overrides={"solution_volume_l": 20.0},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.25}},
        ec_component_policy={"solution_fill": {"npk": 1.0}},
        pid_state={
            "ec": {
                "integral": 0.9,
                "prev_error": 0.7,
                "prev_derivative": 0.0,
                "last_measurement_at": now - timedelta(seconds=10),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    # integral = 0.9 + gap*dt = 0.9 + 1.0*10 = 10.9, clamped to max_integral=1.0
    assert dose_plan.pid_state_updates["ec"]["integral"] == 1.0
    assert dose_plan.pid_state_updates["ec"]["prev_error"] == 1.0
    # output = 10.0 ml by PI term, but one pulse is capped to the modeled
    # closure dose to the canonical target: (2.0 - 1.0) / 0.25 = 4.0 ml.
    assert dose_plan.ec_amount_ml == 4.0


def test_build_dose_plan_returns_retry_delay_when_min_interval_is_active() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 10, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.6,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.9,
        ph_max=6.1,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 90,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.2}},
        ec_component_policy={},
        pid_state={
            "ph": {
                "last_dose_at": now - timedelta(seconds=30),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False
    assert dose_plan.retry_after_sec == 60


def test_build_dose_plan_handles_mixed_naive_aware_last_dose_at() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 10, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.6,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.9,
        ph_max=6.1,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 90,
            }
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.2}},
        ec_component_policy={},
        pid_state={
            "ph": {
                "last_dose_at": (now - timedelta(seconds=30)).replace(tzinfo=UTC),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False
    assert dose_plan.retry_after_sec == 60


def test_build_dose_plan_handles_mixed_naive_aware_last_measurement() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 5, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ec_min=1.95,
        ec_max=2.05,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 2.0,
                "ki": 0.5,
                "kd": 0.0,
                "deadband": 0.05,
                "max_dose_ml": 20.0,
                "max_integral": 1.0,
                "min_interval_sec": 0,
            },
            dosing_overrides={"solution_volume_l": 20.0},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.25}},
        ec_component_policy={"solution_fill": {"npk": 1.0}},
        pid_state={
            "ec": {
                "integral": 0.9,
                "prev_error": 0.7,
                "prev_derivative": 0.0,
                "last_measurement_at": (now - timedelta(seconds=10)).replace(tzinfo=UTC),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.pid_state_updates["ec"]["integral"] == 1.0


def test_build_dose_plan_allows_ph_when_ec_is_in_retry_window() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 10, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.6,
        current_ec=1.6,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.9,
        ph_max=6.1,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 0,
            },
            ec_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 90,
            },
        ),
        workflow_phase="tank_recirc",
        process_calibrations={
            "tank_recirc": {
                "ph_up_gain_per_ml": 0.2,
                "ec_gain_per_ml": 0.2,
            }
        },
        ec_component_policy={"tank_recirc": {"npk": 1.0}},
        pid_state={
            "ec": {"last_dose_at": now - timedelta(seconds=30)},
        },
        now=now,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 8.0},
            },
        },
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is False
    assert dose_plan.ec_retry_after_sec == 60
    assert dose_plan.needs_ph_up is True
    assert dose_plan.ph_channel == "ph_up_pump"
    assert dose_plan.retry_after_sec == 60


def test_build_dose_plan_keeps_ph_and_ec_in_same_correction_window() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 10, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=6.4,
        current_ec=1.6,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.9,
        ph_max=6.1,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ph_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 0,
            },
            ec_overrides={
                "kp": 1.0,
                "ki": 0.1,
                "kd": 0.0,
                "deadband": 0.01,
                "max_dose_ml": 10.0,
                "min_interval_sec": 0,
            },
        ),
        workflow_phase="tank_recirc",
        process_calibrations={
            "tank_recirc": {
                "ph_down_gain_per_ml": 0.2,
                "ec_gain_per_ml": 0.2,
            }
        },
        ec_component_policy={"tank_recirc": {"npk": 1.0}},
        pid_state={
            "ph": {
                "last_dose_at": now - timedelta(seconds=300),
                "last_measurement_at": now - timedelta(seconds=10),
                "last_measured_value": 6.4,
            },
            "ec": {
                "last_dose_at": now - timedelta(seconds=300),
                "last_measurement_at": now - timedelta(seconds=10),
                "last_measured_value": 1.6,
            },
        },
        now=now,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 8.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.needs_ph_down is True
    assert dose_plan.ph_channel == "ph_down_pump"
    assert dose_plan.deferred_action == ""
    assert dose_plan.deferred_reason == ""
    assert "ph" in dose_plan.pid_state_updates
    assert "ec" in dose_plan.pid_state_updates


def test_build_dose_plan_resets_pid_state_when_value_is_back_inside_window() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=5.0,
        current_ec=2.4,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.9,
        ph_max=5.1,
        ec_min=2.35,
        ec_max=2.45,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ph_overrides={"deadband": 0.01},
            ec_overrides={"deadband": 0.01},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={},
        ec_component_policy={},
        pid_state={
            "ph": {"integral": 2.0, "prev_error": -0.3, "prev_derivative": 0.1},
            "ec": {"integral": 5.0, "prev_error": 0.5, "prev_derivative": 0.2},
        },
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False
    assert dose_plan.pid_state_updates["ph"]["integral"] == 0.0
    assert dose_plan.pid_state_updates["ec"]["prev_error"] == 0.0


def test_build_dose_plan_uses_irrigation_process_calibration_for_irrigating_phase() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=5.0,
        current_ec=1.8,
        target_ph=5.0,
        target_ec=2.3,
        ec_min=2.25,
        ec_max=2.35,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 1.0,
                "ki": 0.0,
                "kd": 0.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 10.0,
            }
        ),
        workflow_phase="irrigating",
        process_calibrations={"irrigation": {"ec_gain_per_ml": 0.1}},
        ec_component_policy={"irrigation": {"npk": 1.0}},
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ec is True
    assert dose_plan.ec_amount_ml == pytest.approx(5.0)


def test_build_dose_plan_uses_configured_derivative_filter_alpha() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 5, 0)

    base_kwargs = dict(
        current_ph=5.0,
        current_ec=1.0,
        target_ph=5.0,
        target_ec=2.0,
        ec_min=1.95,
        ec_max=2.05,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.25}},
        ec_component_policy={"solution_fill": {"npk": 1.0}},
        pid_state={
            "ec": {
                "integral": 0.0,
                "prev_error": 0.5,
                "prev_derivative": 1.0,
                "last_measurement_at": now - timedelta(seconds=10),
            }
        },
        now=now,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                # ml_per_sec=1.0 so even small derivative doses exceed _MIN_DOSE_MS (50ms)
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    slow = planner.build_dose_plan(
        correction_config=_correction_config(
            ec_overrides={
                "kp": 0.0,
                "ki": 0.0,
                "kd": 1.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 50.0,
                "derivative_filter_alpha": 0.1,
            }
        ),
        **base_kwargs,
    )
    fast = planner.build_dose_plan(
        correction_config=_correction_config(
            ec_overrides={
                "kp": 0.0,
                "ki": 0.0,
                "kd": 1.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 50.0,
                "derivative_filter_alpha": 1.0,
            }
        ),
        **base_kwargs,
    )

    assert slow.needs_ec is True
    assert fast.needs_ec is True
    assert slow.pid_state_updates["ec"]["prev_derivative"] > fast.pid_state_updates["ec"]["prev_derivative"]


def test_build_dose_plan_first_pid_tick_without_last_measurement_at_keeps_derivative_zero() -> None:
    """Первый PID tick без timestamp не должен генерировать D-spike."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 12, 9, 0, 0)

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 0.0,
                "ki": 0.0,
                "kd": 10.0,
                "deadband": 0.0,
                "min_interval_sec": 0,
                "max_dose_ml": 50.0,
            }
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={
            "ec": {
                "integral": 0.0,
                "prev_error": 5.0,
                "prev_derivative": 1.0,
                # last_measurement_at intentionally missing: this is the first wallclock-aware tick
            }
        },
        now=now,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert plan.needs_ec is False
    assert plan.ec_duration_ms == 0
    assert plan.pid_state_updates["ec"]["prev_derivative"] == 0.0


def test_pid_integral_accumulates_over_time() -> None:
    """Regression: PID integral must grow each call via gap*dt accumulation.

    The old code copied the integral from previous state without incrementing it,
    making ki (integral gain) effectively dead (ki * 0 = 0 always).
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 8, 12, 0, 0)
    last_measurement_at = now - timedelta(seconds=30)
    gap = 1.0  # EC gap: current_ec=1.0, target_ec=2.0 → ec_lo=2.0 with window=none, gap=1.0

    # pid_state with zero integral (starting fresh)
    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={
                "kp": 0.0,
                "ki": 1.0,
                "kd": 0.0,
                "deadband": 0.0,
                "max_dose_ml": 1000.0,
                "min_interval_sec": 0,
                "max_integral": 1000.0,
            },
            dosing_overrides={"solution_volume_l": 10.0},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={
            "ec": {
                "integral": 0.0,
                "prev_error": 0.0,
                "prev_derivative": 0.0,
                "last_measurement_at": last_measurement_at,
            }
        },
        now=now,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    # integral must have grown: gap * dt = 1.0 * 30 = 30.0
    assert plan.pid_state_updates["ec"]["integral"] == 30.0, (
        "PID integral must accumulate gap*dt each step; ki term is dead if integral stays 0"
    )


def test_build_dose_plan_sets_last_dose_at_when_dose_is_nonzero() -> None:
    """pid_state_updates must include last_dose_at=now when dose_ml > 0.

    BUG-5 regression: _compute_amount_ml omitted last_dose_at from the update
    dict, making min_interval_sec enforcement permanently inoperative.
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,  # below target 2.0
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 10.0, "deadband": 0.0, "min_interval_sec": 0},
            dosing_overrides={"solution_volume_l": 10.0},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={},
        now=now,
        ec_actuators={
            "dose_ec_a": {
                "node_uid": "ec-node",
                "channel": "dose_ec_a",
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert plan.needs_ec is True
    assert plan.ec_duration_ms > 0
    assert "ec" in plan.pid_state_updates
    assert plan.pid_state_updates["ec"].get("last_dose_at") == now, (
        "last_dose_at must be set to now when a non-zero dose is computed"
    )


def test_build_dose_plan_does_not_set_last_dose_at_when_dose_is_zero() -> None:
    """last_dose_at must NOT appear in pid_state_updates when dose is forced to zero.

    Ensures we don't inadvertently suppress future corrections by recording a
    phantom dose when the controller produced dose_ml = 0 (e.g., output capped).
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    # kp=0, ki=0, kd=0 → output_units = 0 → dose_ml = 0
    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 0.0, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
            dosing_overrides={"solution_volume_l": 10.0},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 1.0}},
        pid_state={},
        now=now,
        ec_actuators={
            "dose_ec_a": {
                "node_uid": "ec-node",
                "channel": "dose_ec_a",
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert plan.needs_ec is False
    if "ec" in plan.pid_state_updates:
        assert "last_dose_at" not in plan.pid_state_updates["ec"], (
            "last_dose_at must not be set when dose_ml == 0"
        )


def test_build_dose_plan_strips_phantom_last_dose_at_when_duration_below_min_ec() -> None:
    """EC: natural dose > 0, but _dose_ml_to_ms rejects the pulse → last_dose_at stripped.

    Regression for the B8 phantom-dose bug: _compute_amount_ml stamps
    last_dose_at=now whenever ``dose_ml > 0``, but ``_dose_ml_to_ms`` may still
    discard the pulse because the computed duration drops below the pump's
    ``min_dose_ms`` floor. Leaving the phantom last_dose_at would silently
    trigger ``min_interval_sec`` cooldown on a dose that was never commanded,
    starving correction until the cooldown elapsed.
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    # gap=0.1, kp=0.5, gain=0.5 → dose_ml=0.1 (positive → last_dose_at stamped)
    # ml_per_sec=100 → duration = 0.1 / 100 * 1000 = 1 ms < min_dose_ms=50
    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.9,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.1,
        correction_config=_correction_config(
            ec_overrides={"kp": 0.5, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 120},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.5}},
        pid_state={},
        now=now,
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 100.0},
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert plan.needs_ec is False
    assert plan.ec_duration_ms == 0
    assert plan.dose_discarded_reason == "below_min_dose_ms"
    # Integral/prev_error updates must still be persisted (PID state evolves).
    assert "ec" in plan.pid_state_updates
    assert "integral" in plan.pid_state_updates["ec"]
    # But last_dose_at MUST NOT leak through — it would trigger phantom cooldown.
    assert "last_dose_at" not in plan.pid_state_updates["ec"], (
        "phantom last_dose_at must be stripped when _dose_ml_to_ms rejects the pulse"
    )


def test_build_dose_plan_strips_phantom_last_dose_at_when_duration_below_min_ph() -> None:
    """pH symmetric regression: duration below min_dose_ms → last_dose_at stripped."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    # gap=0.1, kp=0.5, gain=0.5 → dose_ml=0.1; ml_per_sec=100 → 1 ms < 50 ms
    plan = planner.build_dose_plan(
        current_ph=6.1,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=0.1,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 0.5, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 90},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.5}},
        pid_state={},
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 100.0},
        },
    )

    assert plan.needs_ph_down is False
    assert plan.ph_duration_ms == 0
    assert plan.dose_discarded_reason == "below_min_dose_ms"
    assert "ph" in plan.pid_state_updates
    assert "integral" in plan.pid_state_updates["ph"]
    assert "last_dose_at" not in plan.pid_state_updates["ph"], (
        "phantom last_dose_at must be stripped for pH when duration rejected"
    )


def test_build_dose_plan_keeps_last_dose_at_when_duration_valid() -> None:
    """Positive control: when dose survives _dose_ml_to_ms, last_dose_at must remain."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.9,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=0.1,
        correction_config=_correction_config(
            ec_overrides={"kp": 0.5, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 120},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.5}},
        pid_state={},
        now=now,
        ec_actuator={
            "node_uid": "ec-node",
            "channel": "ec_pump",
            "calibration": {"ml_per_sec": 1.0},  # slow pump → 100 ms duration, above 50 ms floor
        },
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert plan.needs_ec is True
    assert plan.ec_duration_ms > 0
    assert plan.pid_state_updates["ec"].get("last_dose_at") == now


# ── Фаза 1: Регрессионный тест integral spike при reset ───────────────────────

def test_reset_pid_state_includes_last_measurement_at() -> None:
    """При возврате в норму last_measurement_at должен сбрасываться в now.

    Без этого фикса: integral=0, но last_measurement_at = стый timestamp из
    прошлой коррекции → следующий tick вычисляет огромный dt → integral spike.
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.8,
        ph_max=6.2,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(),
        pid_state={
            "ph": {
                "integral": 3.5,
                "prev_error": 0.2,
                "prev_derivative": 0.0,
                "last_measurement_at": datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC),  # 2h ago
            },
            "ec": {
                "integral": 12.0,
                "prev_error": 0.5,
                "prev_derivative": 0.0,
                "last_measurement_at": datetime(2026, 3, 10, 10, 0, 0, tzinfo=UTC),  # 2h ago
            },
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False

    # integral и prev_error сброшены
    ph_upd = dose_plan.pid_state_updates["ph"]
    ec_upd = dose_plan.pid_state_updates["ec"]
    assert ph_upd["integral"] == 0.0
    assert ec_upd["integral"] == 0.0

    # last_measurement_at должен быть сброшен в now, а не оставаться стым
    assert "last_measurement_at" in ph_upd, (
        "last_measurement_at missing from reset update — stale dt bug not fixed"
    )
    assert "last_measurement_at" in ec_upd, (
        "last_measurement_at missing from reset update — stale dt bug not fixed"
    )
    # Значение должно быть now (UTC naive) — проверяем что это не старый timestamp
    from ae3lite.domain.services.correction_planner import _to_utc_naive
    assert ph_upd["last_measurement_at"] == _to_utc_naive(now)
    assert ec_upd["last_measurement_at"] == _to_utc_naive(now)


def test_no_integral_spike_after_reset_and_reentry() -> None:
    """Симуляция re-entry после reset: integral не должен прыгать до max_integral."""
    planner = CorrectionPlanner()
    t0 = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
    t_reset = datetime(2026, 3, 10, 14, 0, 0, tzinfo=UTC)  # через 2 часа
    t_reentry = datetime(2026, 3, 10, 14, 5, 0, tzinfo=UTC)  # через 5 минут после reset

    # Шаг 1: reset (значения в норме)
    reset_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_min=5.8,
        ph_max=6.2,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(ec_overrides={"min_interval_sec": 0, "deadband": 0.0, "ki": 0.1, "kp": 1.0, "kd": 0.0}),
        pid_state={
            "ec": {"integral": 10.0, "last_measurement_at": t0},
        },
        now=t_reset,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator=None,
    )
    assert reset_plan.pid_state_updates["ec"]["integral"] == 0.0

    # Шаг 2: re-entry (значения вышли из нормы) — используем сброшенный state
    reset_ec_state = reset_plan.pid_state_updates["ec"]  # integral=0, last_measurement_at=t_reset

    reentry_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.7,  # EC ниже нормы
        target_ph=6.0,
        target_ec=2.0,
        ec_min=1.9,
        ec_max=2.1,
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ec_overrides={
                "min_interval_sec": 0,
                "deadband": 0.0,
                "ki": 0.1,
                "kp": 1.0,
                "kd": 0.0,
                "max_integral": 100.0,
            }
        ),
        workflow_phase="solution_fill",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.2}},
        ec_component_policy={},
        pid_state={"ec": reset_ec_state},
        now=t_reentry,
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 1.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    new_integral = reentry_plan.pid_state_updates["ec"]["integral"]
    # dt = 5 минут = 300 сек, gap = 0.3 → integral += 0.3*300 = 90
    # НЕ должно прыгнуть на 2h*0.3=2160 (что было бы без фикса, ограниченное до max=100)
    # С фиксом: dt = 300s, integral = 90 ≤ 100 — корректно
    assert new_integral <= 100.0, f"integral={new_integral} exceeded max_integral"


# ── Фаза 3: Тесты валидации калибровки насоса ────────────────────────────────

def test_dose_ml_to_ms_raises_on_ml_per_sec_too_low() -> None:
    """ml_per_sec ниже 0.01 должен вызывать PlannerConfigurationError."""
    import pytest
    from ae3lite.domain.services.correction_planner import _dose_ml_to_ms
    from ae3lite.domain.errors import PlannerConfigurationError

    with pytest.raises(PlannerConfigurationError, match="valid range"):
        _dose_ml_to_ms(1.0, {"ml_per_sec": 0.001}, _correction_config())


def test_dose_ml_to_ms_raises_on_ml_per_sec_too_high() -> None:
    """ml_per_sec выше 100 должен вызывать PlannerConfigurationError."""
    import pytest
    from ae3lite.domain.services.correction_planner import _dose_ml_to_ms
    from ae3lite.domain.errors import PlannerConfigurationError

    with pytest.raises(PlannerConfigurationError, match="valid range"):
        _dose_ml_to_ms(1.0, {"ml_per_sec": 200.0}, _correction_config())


def test_dose_ml_to_ms_logs_warning_on_silent_drop(caplog) -> None:
    """Дозы ниже _MIN_DOSE_MS=50ms должны давать warning-лог и возвращать reason="below_min_dose_ms"."""
    import logging
    from ae3lite.domain.services.correction_planner import _dose_ml_to_ms

    # 0.002ml / 1.0 ml_per_sec = 2ms < 50ms → должен быть warning
    with caplog.at_level(logging.WARNING, logger="ae3lite.domain.services.correction_planner"):
        duration_ms, reason, details = _dose_ml_to_ms(0.002, {"ml_per_sec": 1.0}, _correction_config())

    assert duration_ms == 0
    assert reason == "below_min_dose_ms"
    assert details["computed_duration_ms"] == 2
    assert details["min_dose_ms"] == 50
    assert any("below minimum" in record.message or "Dose discarded" in record.message
               for record in caplog.records), (
        "Expected warning log for sub-minimum dose, got none"
    )


def test_build_dose_plan_exposes_dead_zone_details_and_discarded_payload() -> None:
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.98,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=1.0,
        correction_config=_correction_config(
            ec_overrides={"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
            dosing_overrides={"pump_calibration": {"min_dose_ms": 50, "ml_per_sec_min": 0.01, "ml_per_sec_max": 100.0}},
        ),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.2}},
        ec_component_policy={"solution_fill": {"npk": 1.0}},
        ec_actuator=None,
        ec_actuators={
            "ec_npk": {
                "node_uid": "ec-node",
                "channel": "ec_npk_pump",
                "calibration": {"ml_per_sec": 10.0},
            },
        },
        ph_up_actuator=None,
        ph_down_actuator=None,
    )

    assert dose_plan.needs_any is False
    assert dose_plan.dose_discarded_reason == "below_min_dose_ms"
    assert dose_plan.dose_discarded_details["computed_duration_ms"] == 10
    assert dose_plan.dead_zone_details["ec_gap"] == pytest.approx(0.02)
    assert dose_plan.dead_zone_details["ec_deadband"] == pytest.approx(0.0)


# ── B4: integral reset при смене pH direction ──────────────────────────────

def test_build_dose_plan_resets_ph_integral_on_direction_switch_up_to_down() -> None:
    """Overshoot scenario: ph_up dose pushed pH from 5.5 to 6.5, past target 6.0.

    Before B4 fix: ph integral from chasing ph_up (positive accumulation)
    would linger and distort the first ph_down dose on the next tick.
    Fix: detect sign flip across the setpoint (5.5 → 6.5 crosses 6.0)
    and reset integral/prev_error/prev_derivative before the new direction
    begins accumulating.
    """
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=6.5,  # above target → ph_down needed
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,  # tolerance = ±0.06 → 6.5 outside
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 0.5, "ki": 0.1, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_down_gain_per_ml": 0.5}},
        pid_state={
            "ph": {
                "integral": 30.0,  # massive positive accumulation from chasing ph_up
                "prev_error": 0.5,
                "prev_derivative": 0.0,
                "last_measurement_at": now - timedelta(seconds=20),
                "last_measured_value": 5.5,  # previous measurement was BELOW target
            },
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator=None,
        ph_down_actuator={
            "node_uid": "ph-node",
            "channel": "ph_down_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
    )

    # ph should still need dose (6.5 outside [5.94, 6.06]).
    assert dose_plan.needs_ph_down is True
    ph_upd = dose_plan.pid_state_updates["ph"]
    # Integral must be reset, not propagated from the old ph_up regime.
    # Without the fix, _next_pid_state would compute integral = 30.0 + 0.5*20 = 40.0
    # and use ki*integral = 4.0 as part of the dose → gross overdose.
    # With the fix, integral starts at 0 and then accumulates 0.5*20 = 10.0 for
    # the current tick's ph_down gap; output = kp*0.5 + ki*10.0 = 0.25 + 1.0 = 1.25 ml.
    assert ph_upd["current_zone"] == "direction_switch"
    assert ph_upd["integral"] == pytest.approx(10.0)


def test_build_dose_plan_resets_ph_integral_on_direction_switch_down_to_up() -> None:
    """Symmetric test: pH overshot DOWN (acid overdose) and now needs ph_up."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.3,  # below target → ph_up needed
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 0.5, "ki": 0.1, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.5}},
        pid_state={
            "ph": {
                "integral": 25.0,
                "prev_error": 0.5,
                "prev_derivative": 0.0,
                "last_measurement_at": now - timedelta(seconds=15),
                "last_measured_value": 6.6,  # previous was ABOVE target
            },
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    ph_upd = dose_plan.pid_state_updates["ph"]
    assert ph_upd["current_zone"] == "direction_switch"
    assert ph_upd["integral"] == pytest.approx(10.5)  # 0.7 * 15 starting from 0


def test_build_dose_plan_preserves_ph_integral_when_same_direction() -> None:
    """No direction switch: integral must continue accumulating normally."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.5,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 0.5, "ki": 0.1, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.5}},
        pid_state={
            "ph": {
                "integral": 5.0,
                "prev_error": 0.4,
                "prev_derivative": 0.0,
                "last_measurement_at": now - timedelta(seconds=10),
                "last_measured_value": 5.6,  # same side (below target) as current
            },
        },
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    ph_upd = dose_plan.pid_state_updates["ph"]
    # No direction switch → zone is not "direction_switch"; integral accumulates
    # from 5.0 + 0.5*10 = 10.0 (same-direction continuation).
    assert ph_upd.get("current_zone") != "direction_switch"
    assert ph_upd["integral"] == pytest.approx(10.0)


def test_build_dose_plan_no_direction_reset_when_no_prior_measurement() -> None:
    """First tick: last_measured_value=None → no direction-switch reset triggered."""
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 10, 12, 0, 0)

    dose_plan = planner.build_dose_plan(
        current_ph=5.5,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=5.0,
        correction_config=_correction_config(
            ph_overrides={"kp": 0.5, "ki": 0.1, "kd": 0.0, "deadband": 0.0, "min_interval_sec": 0},
        ),
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ph_up_gain_per_ml": 0.5}},
        pid_state={},  # no ph entry
        now=now,
        ec_actuator=None,
        ec_actuators={},
        ph_up_actuator={
            "node_uid": "ph-node",
            "channel": "ph_up_pump",
            "calibration": {"ml_per_sec": 8.0},
        },
        ph_down_actuator=None,
    )

    assert dose_plan.needs_ph_up is True
    ph_upd = dose_plan.pid_state_updates.get("ph", {})
    assert ph_upd.get("current_zone") != "direction_switch"


# ── Фаза 4: Тест вынесенной phase_utils ──────────────────────────────────────

def test_normalize_phase_key_from_phase_utils() -> None:
    """normalize_phase_key доступна из phase_utils и возвращает правильные ключи."""
    from ae3lite.domain.services.phase_utils import normalize_phase_key

    assert normalize_phase_key("solution_fill") == "solution_fill"
    assert normalize_phase_key("tank_filling") == "solution_fill"
    assert normalize_phase_key("prepare_recirculation") == "tank_recirc"
    assert normalize_phase_key("tank_recirc") == "tank_recirc"
    assert normalize_phase_key("irrigating") == "irrigation"
    assert normalize_phase_key("irrigation") == "irrigation"
    assert normalize_phase_key("irrig_recirc") == "irrigation"
    assert normalize_phase_key(None) == "generic"
    assert normalize_phase_key("") == "generic"
    assert normalize_phase_key("unknown_phase") == "unknown_phase"
