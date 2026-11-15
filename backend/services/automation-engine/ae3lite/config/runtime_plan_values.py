"""Shared immutable values/records for config/runtime_plan_builder.py."""

from __future__ import annotations

from typing import Any

_MAX_CORRECTION_ATTEMPTS: int = 500

HL_RUN_PUMP_MAX_DURATION_MS: int = 300_000

_REQUIRED_TWO_TANK_PLAN_CHANNELS: dict[str, tuple[str, ...]] = {
    "irrigation_start": ("valve_solution_supply", "valve_irrigation", "pump_main"),
    "irrigation_pump_stop": ("pump_main",),
    "irrigation_stop": ("pump_main", "valve_irrigation", "valve_solution_supply"),
    "clean_fill_start": ("valve_clean_fill",),
    "clean_fill_stop": ("valve_clean_fill",),
    "solution_fill_start": ("valve_clean_supply", "valve_solution_fill", "pump_main"),
    "solution_fill_stop": ("pump_main", "valve_solution_fill", "valve_clean_supply"),
    "prepare_recirculation_start": ("valve_solution_supply", "valve_solution_fill", "pump_main"),
    "prepare_recirculation_stop": ("pump_main", "valve_solution_fill", "valve_solution_supply"),
    "recirc_dilute_start": ("valve_clean_supply",),
    "recirc_dilute_stop": ("valve_clean_supply",),
    "solution_drain_start": ("valve_drain",),
    "solution_drain_stop": ("valve_drain",),
}

_STAGE_TIMEOUT_GUARDS: dict[str, tuple[str, str]] = {
    "solution_fill_start": ("solution_fill", "solution_fill_timeout_sec"),
    "prepare_recirculation_start": ("prepare_recirculation", "prepare_recirculation_timeout_sec"),
}


_REQUIRED_ZONE_CORRECTION_TEMPLATE: dict[str, Any] = {
    "runtime": {
        "required_node_type": "",
        "clean_fill_timeout_sec": 0,
        "solution_fill_timeout_sec": 0,
        "clean_fill_retry_cycles": 0,
        "level_switch_on_threshold": 0.0,
        "clean_max_sensor_label": "",
        "clean_min_sensor_label": "",
        "solution_max_sensor_label": "",
        "solution_min_sensor_label": "",
    },
    "timing": {
        "sensor_mode_stabilization_time_sec": 0,
        "stabilization_sec": 0,
        "telemetry_max_age_sec": 0,
        "irr_state_max_age_sec": 0,
        "level_poll_interval_sec": 0,
    },
    "dosing": {
        "solution_volume_l": 0.0,
        "dose_ec_channel": "",
        "dose_ph_up_channel": "",
        "dose_ph_down_channel": "",
        "max_ec_dose_ml": 0.0,
        "max_ph_dose_ml": 0.0,
    },
    "retry": {
        "max_ec_correction_attempts": 0,
        "max_ph_correction_attempts": 0,
        "prepare_recirculation_timeout_sec": 0,
        "prepare_recirculation_max_attempts": 0,
        "prepare_recirculation_max_correction_attempts": 0,
        "telemetry_stale_retry_sec": 0,
        "decision_window_retry_sec": 0,
        "low_water_retry_sec": 0,
    },
    "tolerance": {
        "prepare_tolerance": {
            "ph_pct": 0.0,
            "ec_pct": 0.0,
        },
    },
    "controllers": {
        "ph": {
            "mode": "",
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "derivative_filter_alpha": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 0.0,
            "min_interval_sec": 0,
            "max_integral": 0.0,
            "anti_windup": {"enabled": False},
            "overshoot_guard": {"enabled": False, "hard_min": 0.0, "hard_max": 0.0},
            "no_effect": {"enabled": False, "max_count": 0},
            "observe": {
                "telemetry_period_sec": 0,
                "window_min_samples": 0,
                "decision_window_sec": 0,
                "observe_poll_sec": 0,
                "min_effect_fraction": 0.0,
                "stability_max_slope": 0.0,
                "no_effect_consecutive_limit": 0,
            },
        },
        "ec": {
            "mode": "",
            "kp": 0.0,
            "ki": 0.0,
            "kd": 0.0,
            "derivative_filter_alpha": 0.0,
            "deadband": 0.0,
            "max_dose_ml": 0.0,
            "min_interval_sec": 0,
            "max_integral": 0.0,
            "anti_windup": {"enabled": False},
            "overshoot_guard": {"enabled": False, "hard_min": 0.0, "hard_max": 0.0},
            "no_effect": {"enabled": False, "max_count": 0},
            "observe": {
                "telemetry_period_sec": 0,
                "window_min_samples": 0,
                "decision_window_sec": 0,
                "observe_poll_sec": 0,
                "min_effect_fraction": 0.0,
                "stability_max_slope": 0.0,
                "no_effect_consecutive_limit": 0,
            },
        },
    },
    "safety": {
        "safe_mode_on_no_effect": False,
        "block_on_active_no_effect_alert": False,
    },
}
