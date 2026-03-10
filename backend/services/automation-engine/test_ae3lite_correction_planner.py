from __future__ import annotations

from datetime import datetime, timedelta

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
        "ec_dose_ml_per_mS_L": 1.0,
        "ph_dose_ml_per_unit_L": 0.5,
        "max_ec_dose_ml": 50.0,
        "max_ph_dose_ml": 20.0,
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
    planner = CorrectionPlanner()

    dose_plan = planner.build_dose_plan(
        current_ph=6.4,
        current_ec=2.0,
        target_ph=6.0,
        target_ec=2.0,
        ph_tolerance_pct=1.0,
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

    assert dose_plan.needs_ph_down is True
    assert dose_plan.ph_channel == "ph_down_pump"
    assert dose_plan.ph_amount_ml == 1.5
    assert dose_plan.ph_duration_ms == 187


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
            "calibration": {"ml_per_sec": 8.0},
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


def test_is_within_tolerance_prefers_explicit_target_windows() -> None:
    planner = CorrectionPlanner()

    assert planner.is_within_tolerance(
        current_ph=5.0,
        current_ec=2.4,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.8,
        ph_max=5.2,
        ec_min=2.2,
        ec_max=2.6,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
    ) is True

    assert planner.is_within_tolerance(
        current_ph=5.31,
        current_ec=2.4,
        target_ph=5.0,
        target_ec=2.4,
        ph_min=4.8,
        ph_max=5.2,
        ec_min=2.2,
        ec_max=2.6,
        ph_tolerance_pct=15.0,
        ec_tolerance_pct=25.0,
    ) is False


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
            "calibration": {"ml_per_sec": 8.0, "min_effective_ml": 1.0},
        },
    )

    assert dose_plan.needs_ph_down is True
    assert dose_plan.ph_channel == "ph_down_pump"


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
    assert dose_plan.ec_amount_ml == 9.4
    assert dose_plan.pid_state_updates["ec"]["integral"] == 0.9
    assert dose_plan.pid_state_updates["ec"]["prev_error"] == 0.95


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
    assert dose_plan.ec_amount_ml == pytest.approx(4.5)


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
                "calibration": {"ml_per_sec": 10.0},
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
