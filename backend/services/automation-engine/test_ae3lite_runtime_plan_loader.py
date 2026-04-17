"""Tests for `ae3lite.config.loader.load_runtime_plan` and the `RuntimePlan`
Pydantic model (Phase 3.1 / B-3).

`RuntimePlan` mirrors the dict produced by `resolve_two_tank_runtime`. These
tests use a hand-crafted canonical payload (no DB / no real resolver) — they
verify the Pydantic shape, not the resolver. The end-to-end check
(resolve → load_runtime_plan) lives in `test_ae3lite_two_tank_cycle_start_integration.py`
and will be added in B-4.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.loader import load_runtime_plan
from ae3lite.config.schema import RuntimePlan


# ─── Fixture ───────────────────────────────────────────────────────────────

def _ph_controller() -> dict:
    return {
        "mode": "cross_coupled_pi_d",
        "kp": 0.28, "ki": 0.015, "kd": 0.0,
        "derivative_filter_alpha": 0.35, "deadband": 0.04,
        "max_dose_ml": 35.0, "min_interval_sec": 20, "max_integral": 12.0,
        "anti_windup": {"enabled": True},
        "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
        "no_effect": {"enabled": True, "max_count": 4},
        "observe": {
            "telemetry_period_sec": 2, "window_min_samples": 3,
            "decision_window_sec": 8, "observe_poll_sec": 2,
            "min_effect_fraction": 0.15, "stability_max_slope": 0.04,
            "no_effect_consecutive_limit": 4,
        },
    }


def _ec_controller() -> dict:
    cfg = _ph_controller()
    cfg.update({
        "mode": "supervisory_allocator",
        "kp": 0.55, "ki": 0.03,
        "deadband": 0.06, "max_dose_ml": 80.0,
        "min_interval_sec": 25, "max_integral": 20.0,
        "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
    })
    cfg["observe"]["stability_max_slope"] = 0.08
    return cfg


def _correction_phase() -> dict:
    return {
        "dose_ec_channel": "pump_a",
        "dose_ph_up_channel": "pump_base",
        "dose_ph_down_channel": "pump_acid",
        "max_ec_dose_ml": 80.0,
        "max_ph_dose_ml": 35.0,
        "stabilization_sec": 8,
        "max_ec_correction_attempts": 8,
        "max_ph_correction_attempts": 8,
        "prepare_recirculation_max_attempts": 4,
        "prepare_recirculation_max_correction_attempts": 40,
        "telemetry_stale_retry_sec": 30,
        "decision_window_retry_sec": 10,
        "low_water_retry_sec": 60,
        "solution_volume_l": 100.0,
        "controllers": {"ph": _ph_controller(), "ec": _ec_controller()},
        "pump_calibration": {},
        "ec_component_policy": {},
        "ec_dosing_mode": "single",
        "ec_component_ratios": {},
        "ec_excluded_components": (),
        "actuators": {},
    }


def _valid_runtime_plan() -> dict:
    correction = _correction_phase()
    return {
        "required_node_types": ["irrig"],
        "clean_fill_timeout_sec": 1200,
        "solution_fill_timeout_sec": 900,
        "prepare_recirculation_timeout_sec": 900,
        "prepare_recirculation_correction_slack_sec": 0,
        "level_poll_interval_sec": 10,
        "clean_fill_retry_cycles": 1,
        "level_switch_on_threshold": 0.5,
        "telemetry_max_age_sec": 10,
        "irr_state_max_age_sec": 30,
        "irr_state_wait_timeout_sec": 5.0,
        "sensor_mode_stabilization_time_sec": 8,
        "clean_max_sensor_labels": ["level_clean_max"],
        "clean_min_sensor_labels": ["level_clean_min"],
        "solution_max_sensor_labels": ["level_solution_max"],
        "solution_min_sensor_labels": ["level_solution_min"],
        "target_ph": 6.0,
        "target_ec": 1.8,
        "target_ph_min": 5.5,
        "target_ph_max": 6.5,
        "target_ec_min": 1.5,
        "target_ec_max": 2.1,
        "target_ec_prepare": 1.5,
        "target_ec_prepare_min": 1.3,
        "target_ec_prepare_max": 1.7,
        "npk_ec_share": 0.85,
        "day_night_enabled": False,
        "day_night_config": {
            "enabled": False,
            "lighting": {"day_start_time": None, "day_hours": None, "timezone": None},
            "ph": {"day": None, "night": None, "day_min": None, "day_max": None,
                   "night_min": None, "night_max": None},
            "ec": {"day": None, "night": None, "day_min": None, "day_max": None,
                   "night_min": None, "night_max": None},
        },
        "prepare_tolerance": {"ph_pct": 5.0, "ec_pct": 10.0},
        "prepare_tolerance_by_phase": {
            "solution_fill": {"ph_pct": 5.0, "ec_pct": 10.0},
            "tank_recirc":   {"ph_pct": 5.0, "ec_pct": 10.0},
            "irrigation":    {"ph_pct": 5.0, "ec_pct": 10.0},
            "generic":       {"ph_pct": 5.0, "ec_pct": 10.0},
        },
        "pid_state": {"ph": {}, "ec": {}},
        "pid_configs": {"ph": {"config": {}}, "ec": {"config": {}}},
        "process_calibrations": {
            "tank_recirc": {
                "ec_gain_per_ml": 0.01,
                "ph_up_gain_per_ml": 0.022,
                "ph_down_gain_per_ml": 0.022,
                "ph_per_ec_ml": -0.002,
                "ec_per_ph_ml": 0.001,
                "transport_delay_sec": 4,
                "settle_sec": 12,
                "confidence": 0.85,
                "source": "system_default",
                "meta": {},
            }
        },
        "correction": deepcopy(correction),
        "correction_by_phase": {
            "solution_fill": deepcopy(correction),
            "tank_recirc":   deepcopy(correction),
            "irrigation":    deepcopy(correction),
            "generic":       deepcopy(correction),
        },
        "command_specs": {
            "irrigation_start": [
                {"channel": "valve_solution_supply", "cmd": "set_relay",
                 "params": {"state": True}, "node_types": ["irrig"], "complete_on_ack": False},
            ],
        },
        "fail_safe_guards": {
            "clean_fill_min_check_delay_ms": 5000,
            "solution_fill_clean_min_check_delay_ms": 5000,
            "solution_fill_solution_min_check_delay_ms": 15000,
            "recirculation_stop_on_solution_min": True,
            "irrigation_stop_on_solution_min": True,
            "estop_debounce_ms": 80,
        },
        "irrigation_execution": {
            "duration_sec": None,
            "interval_sec": None,
            "correction_during_irrigation": True,
            "correction_slack_sec": 900,
            "stage_timeout_sec": 3600,
        },
        "irrigation_decision": {
            "strategy": "task",
            "config": {
                "lookback_sec": 1800, "min_samples": 3,
                "stale_after_sec": 600, "hysteresis_pct": 2.0,
                "spread_alert_threshold_pct": 12.0,
            },
        },
        "irrigation_recovery": {
            "max_continue_attempts": 5, "timeout_sec": 600,
            "auto_replay_after_setup": True, "max_setup_replays": 1,
        },
        "irrigation_safety": {"stop_on_solution_min": True},
        "soil_moisture_target": None,
    }


# ─── Happy path ────────────────────────────────────────────────────────────

def test_canonical_runtime_plan_accepted() -> None:
    plan = load_runtime_plan(_valid_runtime_plan(), zone_id=1)
    assert isinstance(plan, RuntimePlan)
    assert plan.target_ph == pytest.approx(6.0)
    assert plan.correction.dose_ec_channel == "pump_a"
    assert plan.correction_by_phase["solution_fill"].ec_dosing_mode == "single"
    assert len(plan.command_specs["irrigation_start"]) == 1


def test_runtime_plan_is_frozen() -> None:
    plan = load_runtime_plan(_valid_runtime_plan(), zone_id=1)
    with pytest.raises(Exception):
        plan.target_ph = 7.0  # type: ignore[misc]


def test_optional_soil_moisture_target_none() -> None:
    plan = load_runtime_plan(_valid_runtime_plan())
    assert plan.soil_moisture_target is None


# ─── Errors ────────────────────────────────────────────────────────────────

def test_rejects_non_mapping_payload() -> None:
    with pytest.raises(ConfigValidationError):
        load_runtime_plan([1, 2], zone_id=5)  # type: ignore[arg-type]


def test_rejects_missing_required_top_level() -> None:
    p = _valid_runtime_plan()
    del p["target_ph"]
    with pytest.raises(ConfigValidationError) as exc:
        load_runtime_plan(p)
    assert any("target_ph" in tuple(e["loc"]) for e in exc.value.errors)


def test_rejects_unknown_top_level_field() -> None:
    p = _valid_runtime_plan()
    p["experimental_knob"] = 42
    with pytest.raises(ConfigValidationError):
        load_runtime_plan(p)


def test_rejects_target_ph_out_of_physical_bounds() -> None:
    p = _valid_runtime_plan()
    p["target_ph"] = 15.5
    with pytest.raises(ConfigValidationError):
        load_runtime_plan(p)


def test_rejects_invalid_command_step_cmd() -> None:
    p = _valid_runtime_plan()
    p["command_specs"]["irrigation_start"][0]["cmd"] = ""
    with pytest.raises(ConfigValidationError):
        load_runtime_plan(p)


def test_rejects_correction_by_phase_missing_controller() -> None:
    p = _valid_runtime_plan()
    del p["correction_by_phase"]["solution_fill"]["controllers"]
    with pytest.raises(ConfigValidationError):
        load_runtime_plan(p)


def test_rejects_invalid_ec_dosing_mode() -> None:
    p = _valid_runtime_plan()
    p["correction"]["ec_dosing_mode"] = "experimental_mode"
    with pytest.raises(ConfigValidationError):
        load_runtime_plan(p)


def test_error_carries_zone_id_and_namespace() -> None:
    p = _valid_runtime_plan()
    del p["fail_safe_guards"]
    with pytest.raises(ConfigValidationError) as exc:
        load_runtime_plan(p, zone_id=99, namespace="runtime.plan:test")
    assert exc.value.zone_id == 99
    assert exc.value.namespace == "runtime.plan:test"


def test_independent_copies_dont_cross_contaminate() -> None:
    p1 = _valid_runtime_plan()
    p2 = deepcopy(p1)
    p2["target_ph"] = 7.5
    plan1 = load_runtime_plan(p1)
    plan2 = load_runtime_plan(p2)
    assert plan1.target_ph == pytest.approx(6.0)
    assert plan2.target_ph == pytest.approx(7.5)


# ─── Integration: real resolve_two_tank_runtime → load_runtime_plan ───────

def test_resolve_two_tank_runtime_output_validates_as_runtime_plan() -> None:
    """Builder output must validate as `RuntimePlan` without field drift."""
    from test_ae3lite_runtime_plan_builder import _snapshot
    from ae3lite.config.runtime_plan_builder import resolve_two_tank_runtime

    snapshot = _snapshot(correction={})
    runtime_dict = resolve_two_tank_runtime(snapshot)
    plan = load_runtime_plan(runtime_dict, zone_id=1)

    assert plan.target_ph == pytest.approx(5.8)
    assert plan.target_ec == pytest.approx(2.2)
    assert "irrig" in plan.required_node_types
    assert plan.correction.dose_ec_channel  # non-empty
    # Phases dict must contain all 4 keys after merge
    assert set(plan.correction_by_phase.keys()) >= {
        "solution_fill", "tank_recirc", "irrigation", "generic",
    }
