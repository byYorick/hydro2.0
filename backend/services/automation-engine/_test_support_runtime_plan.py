"""Shared factory for `RuntimePlan` test fixtures.

Handlers now consume `plan.runtime` as a typed `RuntimePlan` model (no more
`_DictShim` compat bridge). Tests therefore must construct a fully populated
`RuntimePlan` rather than a partial dict. This module provides a factory
`make_runtime_plan_dict(**overrides)` that returns a canonical valid payload
covering all required fields; tests override only what they care about.

Usage:
    from _test_support_runtime_plan import make_runtime_plan, make_runtime_plan_dict

    plan = SimpleNamespace(runtime=make_runtime_plan(target_ph=6.2))
    # or override nested:
    runtime_dict = make_runtime_plan_dict(
        fail_safe_guards={"clean_fill_min_check_delay_ms": 2000, ...},
    )
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ae3lite.config.loader import load_runtime_plan
from ae3lite.config.schema import RuntimePlan


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


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursive dict merge. `patch` values override `base`. Nested dicts merged."""
    for k, v in patch.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def make_runtime_plan_dict(**overrides: Any) -> dict:
    """Return a dict with every required RuntimePlan field populated.

    Overrides are deep-merged into the canonical base — pass nested dicts
    with only the keys you want changed (e.g.
    `correction={"max_ec_correction_attempts": 4}` only overrides that one
    field, the rest of the default correction stays intact).
    """
    correction = _correction_phase()
    base: dict = {
        "required_node_types": ["irrig"],
        "clean_fill_timeout_sec": 1200,
        "solution_fill_timeout_sec": 900,
        "prepare_recirculation_timeout_sec": 900,
        "prepare_recirculation_correction_slack_sec": 0,
        "level_poll_interval_sec": 10,
        "clean_fill_retry_cycles": 1,
        "level_switch_on_threshold": 0.5,
        "telemetry_max_age_sec": 300,
        "irr_state_max_age_sec": 60,
        "irr_state_wait_timeout_sec": 5.0,
        "irr_state_wait_poll_interval_sec": None,
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
        "command_specs": {},
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
            "stage_timeout_sec": None,
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
    _deep_merge(base, overrides)
    return base


def make_runtime_plan(**overrides: Any) -> RuntimePlan:
    """Return a fully validated `RuntimePlan` with overrides applied."""
    return load_runtime_plan(make_runtime_plan_dict(**overrides))
