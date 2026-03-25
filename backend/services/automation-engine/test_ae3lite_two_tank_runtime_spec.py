from __future__ import annotations

from types import SimpleNamespace

import pytest

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.two_tank_runtime_spec import resolve_two_tank_runtime


def _minimal_zone_correction_config() -> dict[str, object]:
    return {
        "base": {
            "runtime": {
                "required_node_type": "irrig",
                "clean_fill_timeout_sec": 1200,
                "solution_fill_timeout_sec": 1800,
                "clean_fill_retry_cycles": 1,
                "level_switch_on_threshold": 0.5,
                "clean_max_sensor_label": "level_clean_max",
                "clean_min_sensor_label": "level_clean_min",
                "solution_max_sensor_label": "level_solution_max",
                "solution_min_sensor_label": "level_solution_min",
            },
            "timing": {
                "sensor_mode_stabilization_time_sec": 60,
                "stabilization_sec": 60,
                "telemetry_max_age_sec": 60,
                "irr_state_max_age_sec": 30,
                "level_poll_interval_sec": 10,
            },
            "retry": {
                "max_ec_correction_attempts": 5,
                "max_ph_correction_attempts": 5,
                "prepare_recirculation_timeout_sec": 1200,
                "prepare_recirculation_max_attempts": 3,
                "prepare_recirculation_max_correction_attempts": 20,
                "telemetry_stale_retry_sec": 30,
                "decision_window_retry_sec": 30,
                "low_water_retry_sec": 60,
            },
            "dosing": {
                "solution_volume_l": 100.0,
                "dose_ec_channel": "ec_npk_pump",
                "dose_ph_up_channel": "ph_base_pump",
                "dose_ph_down_channel": "ph_acid_pump",
                "max_ec_dose_ml": 50.0,
                "max_ph_dose_ml": 20.0,
            },
            "tolerance": {
                "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
            },
            "controllers": {
                "ph": {
                    "mode": "cross_coupled_pi_d",
                    "kp": 5.0,
                    "ki": 0.05,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.05,
                    "max_dose_ml": 20.0,
                    "min_interval_sec": 90,
                    "max_integral": 20.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.02,
                        "no_effect_consecutive_limit": 3,
                    },
                },
                "ec": {
                    "mode": "supervisory_allocator",
                    "kp": 30.0,
                    "ki": 0.3,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.1,
                    "max_dose_ml": 50.0,
                    "min_interval_sec": 120,
                    "max_integral": 100.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.05,
                        "no_effect_consecutive_limit": 3,
                    },
                },
            },
            "safety": {
                "safe_mode_on_no_effect": True,
                "block_on_active_no_effect_alert": True,
            },
        },
        "phases": {
            "solution_fill": {},
            "tank_recirc": {},
            "irrigation": {},
        },
        "meta": {},
    }


def _minimal_pid_configs() -> dict[str, object]:
    return {
        "ph": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
        "ec": {"config": {"kp": 1.0, "ki": 0.1, "kd": 0.0}},
    }


def _merge_recursive(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_recursive(current, value)
            continue
        merged[key] = value
    return merged


def _with_legacy_runtime_overrides(
    *,
    correction_config: dict[str, object],
    correction: dict[str, object],
    startup: dict[str, object] | None,
    prepare_tolerance: dict[str, object] | None,
) -> dict[str, object]:
    merged = _merge_recursive(_minimal_zone_correction_config(), correction_config)
    if correction_config:
        return merged

    dosing = merged["base"]["dosing"]
    retry = merged["base"]["retry"]
    timing = merged["base"]["timing"]
    tolerance_cfg = merged["base"]["tolerance"]["prepare_tolerance"]
    runtime_cfg = merged["base"]["runtime"]

    for key, value in correction.items():
        if key in {"max_ec_correction_attempts", "max_ph_correction_attempts", "prepare_recirculation_max_attempts", "prepare_recirculation_max_correction_attempts"}:
            retry[key] = value
        elif key in {"max_ec_dose_ml", "max_ph_dose_ml", "solution_volume_l", "dose_ec_channel", "dose_ph_up_channel", "dose_ph_down_channel"}:
            dosing[key] = value
        elif key == "stabilization_sec":
            timing[key] = value

    for key, value in (startup or {}).items():
        if key in {"clean_fill_timeout_sec", "solution_fill_timeout_sec", "clean_fill_retry_cycles", "level_switch_on_threshold", "clean_max_sensor_label", "clean_min_sensor_label", "solution_max_sensor_label", "solution_min_sensor_label"}:
            runtime_cfg[key] = value
        elif key in {"telemetry_max_age_sec", "irr_state_max_age_sec", "level_poll_interval_sec", "sensor_mode_stabilization_time_sec"}:
            timing[key] = value
        elif key in {"prepare_recirculation_timeout_sec"}:
            retry[key] = value

    for key, value in (prepare_tolerance or {}).items():
        tolerance_cfg[key] = value

    return merged


def _snapshot(
    *,
    correction: dict[str, object],
    startup: dict[str, object] | None = None,
    correction_config: dict[str, object] | None = None,
    prepare_tolerance: dict[str, object] | None = None,
    process_calibrations: dict[str, object] | None = None,
) -> SimpleNamespace:
    default_process_calibrations = {
        "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
        "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
        "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
    }
    effective_correction_config = _with_legacy_runtime_overrides(
        correction_config=correction_config if correction_config is not None else {},
        correction=correction,
        startup=startup,
        prepare_tolerance=prepare_tolerance,
    )
    return SimpleNamespace(
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "irr_state_wait_timeout_sec": 4.5,
                **(startup or {}),
            },
            "prepare_tolerance": dict(prepare_tolerance or {}),
            "correction": correction,
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs=_minimal_pid_configs(),
        process_calibrations=process_calibrations if process_calibrations is not None else default_process_calibrations,
        correction_config=effective_correction_config,
    )


def test_resolve_target_bound_handles_zero_value() -> None:
    """ec_min=0.0 must NOT be ignored (falsy value != absent value)."""
    runtime = resolve_two_tank_runtime(
        _snapshot(correction={})
    )
    # Override snapshot to include explicit zero bounds
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "ec_min": 0.0,
            "ph_min": 0.0,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8, "min": 0.0},
            "ec": {"target": 2.2, "min": 0.0},
        },
        pid_configs=_minimal_pid_configs(),
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 10,
                "settle_sec": 10,
            }
        },
        correction_config=_minimal_zone_correction_config(),
    )
    runtime = resolve_two_tank_runtime(snap)
    # 0.0 is a valid bound and must be preserved (not replaced by fallback=target)
    assert runtime["target_ec_min"] == 0.0
    assert runtime["target_ph_min"] == 0.0


def test_resolve_two_tank_runtime_uses_recipe_phase_targets_instead_of_execution_targets() -> None:
    snap = _snapshot(correction={})
    snap.phase_targets = {
        "ph": {"target": 6.4},
        "ec": {"target": 1.1},
    }

    runtime = resolve_two_tank_runtime(snap)

    assert runtime["target_ph"] == 6.4
    assert runtime["target_ec"] == 1.1


def test_resolve_two_tank_runtime_raises_when_recipe_phase_target_missing() -> None:
    snap = _snapshot(correction={})
    snap.phase_targets = {
        "ph": {"target": 5.8},
    }

    with pytest.raises(PlannerConfigurationError) as exc_info:
        resolve_two_tank_runtime(snap)

    assert getattr(exc_info.value, "code", "") == "zone_recipe_phase_targets_missing_critical"


def test_resolve_two_tank_runtime_uses_split_retry_contract() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "max_ec_correction_attempts": 3,
                "max_ph_correction_attempts": 4,
                "prepare_recirculation_max_attempts": 2,
                "prepare_recirculation_max_correction_attempts": 11,
            }
        )
    )

    assert runtime["correction"]["max_ec_correction_attempts"] == 3
    assert runtime["correction"]["max_ph_correction_attempts"] == 4
    assert runtime["correction"]["prepare_recirculation_max_attempts"] == 2
    assert runtime["correction"]["prepare_recirculation_max_correction_attempts"] == 11
    assert runtime["irr_state_wait_timeout_sec"] == 4.5


def test_resolve_two_tank_runtime_preserves_explicit_prepare_recirculation_attempt_cap() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "prepare_recirculation_max_correction_attempts": 200,
            }
        )
    )

    assert runtime["correction"]["prepare_recirculation_max_correction_attempts"] == 200


def test_resolve_two_tank_runtime_includes_configurable_retry_delays() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={},
            correction_config={
                "phases": {
                    "solution_fill": {
                        "retry": {
                            "telemetry_stale_retry_sec": 17,
                            "decision_window_retry_sec": 19,
                            "low_water_retry_sec": 61,
                        },
                    },
                },
            },
        )
    )

    assert runtime["correction"]["telemetry_stale_retry_sec"] == 17
    assert runtime["correction"]["decision_window_retry_sec"] == 19
    assert runtime["correction"]["low_water_retry_sec"] == 61


def test_resolve_two_tank_runtime_rejects_correction_attempt_caps_above_contract_maximum() -> None:
    with pytest.raises(PlannerConfigurationError, match="retry.max_ec_correction_attempts must be <= 500"):
        resolve_two_tank_runtime(
            _snapshot(
                correction={
                    "max_ec_correction_attempts": 999,
                    "max_ph_correction_attempts": 999,
                    "prepare_recirculation_max_correction_attempts": 999,
                }
            )
        )


def test_resolve_two_tank_runtime_accepts_timeout_equal_to_observe_window_plus_stabilization() -> None:
    """timeout == observe_window + stabilization is the exact minimum — should pass."""
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs=_minimal_pid_configs(),
        correction_config=_with_legacy_runtime_overrides(
            correction_config={},
            correction={"stabilization_sec": 10},
            startup={"prepare_recirculation_timeout_sec": 35},
            prepare_tolerance=None,
        ),
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 15,
                "settle_sec": 10,
            }
        },
    )
    runtime = resolve_two_tank_runtime(snap)
    assert runtime["prepare_recirculation_timeout_sec"] == 35


def test_resolve_two_tank_runtime_raises_when_timeout_less_than_observe_window_plus_stabilization() -> None:
    """timeout < observe_window + stabilization is provably impossible — must raise PlannerConfigurationError."""
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs=_minimal_pid_configs(),
        correction_config=_with_legacy_runtime_overrides(
            correction_config={},
            correction={"stabilization_sec": 10},
            startup={"prepare_recirculation_timeout_sec": 30},
            prepare_tolerance=None,
        ),
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 15,
                "settle_sec": 10,
            }
        },
    )
    with pytest.raises(PlannerConfigurationError, match="prepare_recirculation_timeout_sec"):
        resolve_two_tank_runtime(snap)


def test_resolve_two_tank_runtime_prefers_process_hold_window_for_prepare_recirculation_validation() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "stabilization_sec": 10,
            },
            startup={
                "prepare_recirculation_timeout_sec": 55,
            },
            process_calibrations={
                "tank_recirc": {
                    "transport_delay_sec": 25,
                    "settle_sec": 20,
                }
            },
        )
    )

    assert runtime["prepare_recirculation_timeout_sec"] == 55


def test_resolve_two_tank_runtime_raises_when_timeout_less_than_process_hold_window() -> None:
    with pytest.raises(PlannerConfigurationError, match="observe_window_sec"):
        resolve_two_tank_runtime(
            _snapshot(
                correction={
                    "stabilization_sec": 10,
                },
                startup={
                    "prepare_recirculation_timeout_sec": 50,
                },
                process_calibrations={
                    "tank_recirc": {
                        "transport_delay_sec": 25,
                        "settle_sec": 20,
                    }
                },
            )
        )


def test_resolve_two_tank_runtime_raises_when_zone_correction_config_missing() -> None:
    snap = SimpleNamespace(
        zone_id=188,
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs=_minimal_pid_configs(),
        correction_config=None,
    )
    with pytest.raises(PlannerConfigurationError) as exc_info:
        resolve_two_tank_runtime(snap)
    assert getattr(exc_info.value, "code", "") == "zone_correction_config_missing_critical"


def test_resolve_two_tank_runtime_uses_phase_aware_correction_config() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "stabilization_sec": 60,
            },
            correction_config={
                "base": {
                    "timing": {
                        "stabilization_sec": 20,
                    },
                    "retry": {
                        "prepare_recirculation_timeout_sec": 600,
                    },
                },
                "phases": {
                    "solution_fill": {
                        "timing": {
                            "stabilization_sec": 10,
                        }
                    },
                    "tank_recirc": {
                        "timing": {
                            "stabilization_sec": 10,
                        },
                        "retry": {
                            "prepare_recirculation_timeout_sec": 360,
                        },
                    },
                },
                "meta": {
                    "phase_overrides": {
                        "solution_fill": {
                            "timing": {
                                "stabilization_sec": 10,
                            },
                        },
                        "tank_recirc": {
                            "timing": {
                                "stabilization_sec": 10,
                            },
                            "retry": {
                                "prepare_recirculation_timeout_sec": 360,
                            },
                        },
                    }
                },
            },
            process_calibrations={
                "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
                "tank_recirc": {"transport_delay_sec": 15, "settle_sec": 15},
                "irrigation": {"transport_delay_sec": 20, "settle_sec": 20},
            },
        )
    )

    assert runtime["correction"]["stabilization_sec"] == 10
    assert runtime["correction_by_phase"]["tank_recirc"]["stabilization_sec"] == 10
    assert "ec_mix_wait_sec" not in runtime["correction"]
    assert "ph_mix_wait_sec" not in runtime["correction_by_phase"]["tank_recirc"]
    assert runtime["prepare_recirculation_timeout_sec"] == 360


def test_resolve_two_tank_runtime_raises_when_pid_authority_documents_missing() -> None:
    snap = SimpleNamespace(
        zone_id=188,
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs={},
        process_calibrations={
            "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
            "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
            "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
        },
        correction_config=_minimal_zone_correction_config(),
    )

    with pytest.raises(PlannerConfigurationError) as exc_info:
        resolve_two_tank_runtime(snap)

    assert getattr(exc_info.value, "code", "") == "zone_pid_config_missing_critical"


def test_resolve_two_tank_runtime_raises_when_zone_correction_field_missing() -> None:
    correction_config = _minimal_zone_correction_config()
    del correction_config["base"]["dosing"]["max_ec_dose_ml"]

    snap = SimpleNamespace(
        zone_id=188,
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        phase_targets={
            "ph": {"target": 5.8},
            "ec": {"target": 2.2},
        },
        pid_configs=_minimal_pid_configs(),
        process_calibrations={
            "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
            "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
            "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
        },
        correction_config=correction_config,
    )

    with pytest.raises(PlannerConfigurationError, match="max_ec_dose_ml") as exc_info:
        resolve_two_tank_runtime(snap)

    assert getattr(exc_info.value, "code", "") == "zone_correction_config_missing_critical"


def test_resolve_two_tank_runtime_prefers_correction_config_over_execution_defaults() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "max_ec_correction_attempts": 8,
                "max_ph_correction_attempts": 8,
            },
            startup={
                "solution_fill_timeout_sec": 240,
                "prepare_recirculation_timeout_sec": 30,
                "level_poll_interval_sec": 5,
            },
            correction_config={
                "base": {
                    "timing": {
                        "level_poll_interval_sec": 20,
                    },
                    "retry": {
                        "max_ec_correction_attempts": 5,
                        "max_ph_correction_attempts": 5,
                        "prepare_recirculation_timeout_sec": 600,
                    },
                    "runtime": {
                        "solution_fill_timeout_sec": 900,
                    },
                },
                "phases": {
                    "solution_fill": {"timing": {}},
                    "tank_recirc": {},
                    "irrigation": {},
                },
                "meta": {},
            },
            process_calibrations={
                "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
                "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
                "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
            },
        )
    )

    assert "ec_mix_wait_sec" not in runtime["correction"]
    assert "ph_mix_wait_sec" not in runtime["correction"]
    assert runtime["correction"]["max_ec_correction_attempts"] == 5
    assert runtime["correction"]["max_ph_correction_attempts"] == 5
    assert runtime["solution_fill_timeout_sec"] == 900
    assert runtime["prepare_recirculation_timeout_sec"] == 600
    assert runtime["level_poll_interval_sec"] == 20


def test_resolve_two_tank_runtime_prefers_correction_config_prepare_timeout_over_startup_default() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={"stabilization_sec": 0},
            startup={"prepare_recirculation_timeout_sec": 30},
            correction_config={
                "base": {
                    "retry": {
                        "prepare_recirculation_timeout_sec": 600,
                    }
                },
                "phases": {
                    "tank_recirc": {
                        "retry": {
                            "prepare_recirculation_timeout_sec": 600,
                        }
                    }
                },
            },
            process_calibrations={
                "tank_recirc": {
                    "transport_delay_sec": 10,
                    "settle_sec": 10,
                }
            },
        )
    )

    assert runtime["prepare_recirculation_timeout_sec"] == 600


def test_resolve_two_tank_runtime_exposes_process_calibrations_to_runtime() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={"stabilization_sec": 0},
            process_calibrations={
                "solution_fill": {
                    "ec_gain_per_ml": 0.25,
                    "transport_delay_sec": 15,
                },
                "tank_recirc": {
                    "ph_down_gain_per_ml": 0.12,
                    "transport_delay_sec": 15,
                    "settle_sec": 45,
                },
            },
        )
    )

    assert runtime["process_calibrations"]["solution_fill"]["ec_gain_per_ml"] == 0.25
    assert runtime["process_calibrations"]["tank_recirc"]["settle_sec"] == 45


def test_resolve_two_tank_runtime_requires_process_hold_window_for_prepare_recirculation() -> None:
    with pytest.raises(PlannerConfigurationError, match="transport_delay_sec and settle_sec"):
        resolve_two_tank_runtime(
            _snapshot(
                correction={"stabilization_sec": 5},
                startup={"prepare_recirculation_timeout_sec": 60},
                process_calibrations={
                    "tank_recirc": {
                        "transport_delay_sec": 15,
                    }
                },
            )
        )
