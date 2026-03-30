from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError
from ae3lite.infrastructure.read_models.zone_snapshot_read_model import PgZoneSnapshotReadModel


def test_resolve_profile_execution_merges_non_conflicting_sources() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._resolve_profile_execution(
        {
            "subsystems": {
                "diagnostics": {
                    "execution": {
                        "workflow": "cycle_start",
                        "startup": {"level_poll_interval_sec": 10},
                    }
                }
            },
            "command_plans": {
                "plans": {
                    "diagnostics": {
                        "execution": {
                            "topology": "two_tank",
                            "startup": {"clean_fill_timeout_sec": 30},
                        }
                    }
                }
            },
        }
    )

    assert result["workflow"] == "cycle_start"
    assert result["topology"] == "two_tank"
    assert result["startup"]["level_poll_interval_sec"] == 10
    assert result["startup"]["clean_fill_timeout_sec"] == 30


def test_normalize_two_tank_execution_contract_removes_legacy_startup_and_required_node_types() -> None:
    read_model = PgZoneSnapshotReadModel()
    execution = {
        "workflow": "cycle_start",
        "topology": "two_tank_drip_substrate_trays",
        "required_node_types": ["irrig"],
        "startup": {"clean_fill_timeout_sec": 30},
        "refill_timeout_sec": 60,
    }

    read_model._normalize_two_tank_execution_contract(execution)

    assert execution["workflow"] == "cycle_start"
    assert execution["topology"] == "two_tank_drip_substrate_trays"
    assert execution["refill_timeout_sec"] == 60
    assert "startup" not in execution
    assert "required_node_types" not in execution


def test_resolve_profile_execution_fails_on_conflict() -> None:
    read_model = PgZoneSnapshotReadModel()

    with pytest.raises(SnapshotBuildError) as exc_info:
        read_model._resolve_profile_execution(
            {
                "subsystems": {
                    "diagnostics": {
                        "execution": {
                            "workflow": "cycle_start",
                            "topology": "two_tank",
                        }
                    }
                },
                "command_plans": {
                    "plans": {
                        "diagnostics": {
                            "execution": {
                                "topology": "generic_cycle_start",
                            }
                        }
                    }
                },
            }
    )

    assert "diagnostics.execution.topology" in str(exc_info.value)
    assert exc_info.value.code == ErrorCodes.AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES


def test_resolve_ec_component_policy_extracts_correction_policy() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._resolve_ec_component_policy(
        {
            "workflow": "cycle_start",
            "correction": {
                "ec_component_policy": {
                    "solution_fill": {"npk": 1.0},
                    "irrigating": {"calcium": 0.45, "magnesium": 0.25, "micro": 0.30},
                }
            },
        }
    )

    assert result["solution_fill"]["npk"] == 1.0
    assert result["irrigating"]["calcium"] == 0.45


def test_build_process_calibrations_prefers_first_active_profile_per_mode() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._build_process_calibrations(
        [
            {
                "mode": "tank_recirc",
                "ec_gain_per_ml": 0.11,
                "ph_up_gain_per_ml": 0.08,
                "ph_down_gain_per_ml": 0.07,
                "ph_per_ec_ml": -0.015,
                "ec_per_ph_ml": 0.02,
                "transport_delay_sec": 20,
                "settle_sec": 45,
                "confidence": 0.91,
                "source": "hil_manual",
                "valid_from": None,
                "valid_to": None,
                "is_active": True,
                "meta": {"batch": "a"},
                "updated_at": None,
            },
            {
                "mode": "tank_recirc",
                "ec_gain_per_ml": 0.99,
                "ph_up_gain_per_ml": 0.99,
                "ph_down_gain_per_ml": 0.99,
                "ph_per_ec_ml": 0.99,
                "ec_per_ph_ml": 0.99,
                "transport_delay_sec": 99,
                "settle_sec": 99,
                "confidence": 0.10,
                "source": "should_not_win",
                "valid_from": None,
                "valid_to": None,
                "is_active": True,
                "meta": {},
                "updated_at": None,
            },
            {
                "mode": "generic",
                "ec_gain_per_ml": 0.05,
                "ph_up_gain_per_ml": 0.03,
                "ph_down_gain_per_ml": 0.02,
                "ph_per_ec_ml": -0.01,
                "ec_per_ph_ml": 0.01,
                "transport_delay_sec": 15,
                "settle_sec": 30,
                "confidence": 0.70,
                "source": "generic",
                "valid_from": None,
                "valid_to": None,
                "is_active": True,
                "meta": {},
                "updated_at": None,
            },
        ]
    )

    assert result["tank_recirc"]["source"] == "hil_manual"
    assert result["tank_recirc"]["transport_delay_sec"] == 20
    assert result["generic"]["settle_sec"] == 30


def test_build_phase_targets_uses_recipe_phase_without_runtime_overrides() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._build_phase_targets(
        zone_row={
            "ph_target": 5.7,
            "ph_min": 5.5,
            "ph_max": 5.9,
            "ec_target": 1.4,
            "ec_min": 1.2,
            "ec_max": 1.6,
            "phase_extensions": {
                "targets": {
                    "diagnostics": {
                        "execution": {
                            "target_ph": 9.9,
                            "target_ec": 9.9,
                        }
                    }
                }
            },
        }
    )

    assert result["ph"]["target"] == 5.7
    assert result["ec"]["target"] == 1.4
    assert result["diagnostics"]["execution"]["target_ph"] == 9.9


def test_build_phase_targets_preserves_phase_extensions_for_runtime_consumers() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._build_phase_targets(
        zone_row={
            "phase_extensions": {
                "subsystems": {
                    "irrigation": {
                        "targets": {
                            "soil_moisture": {
                                "min": 38.0,
                                "max": 48.0,
                                "target": 43.0,
                                "unit": "pct",
                            }
                        }
                    }
                }
            }
        }
    )

    assert result["extensions"]["subsystems"]["irrigation"]["targets"]["soil_moisture"]["min"] == 38.0
    assert result["extensions"]["subsystems"]["irrigation"]["targets"]["soil_moisture"]["max"] == 48.0
    assert result["extensions"]["subsystems"]["irrigation"]["targets"]["soil_moisture"]["target"] == 43.0
    assert result["extensions"]["subsystems"]["irrigation"]["targets"]["soil_moisture"]["unit"] == "pct"


def test_build_process_calibrations_normalizes_legacy_mode_aliases() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._build_process_calibrations(
        [
            {
                "mode": "irrigating",
                "ec_gain_per_ml": 0.21,
                "ph_up_gain_per_ml": None,
                "ph_down_gain_per_ml": None,
                "ph_per_ec_ml": None,
                "ec_per_ph_ml": None,
                "transport_delay_sec": 12,
                "settle_sec": 30,
                "confidence": 0.8,
                "source": "legacy_irrigating",
                "valid_from": None,
                "valid_to": None,
                "is_active": True,
                "meta": {},
                "updated_at": None,
            },
            {
                "mode": "irrig_recirc",
                "ec_gain_per_ml": 0.99,
                "ph_up_gain_per_ml": None,
                "ph_down_gain_per_ml": None,
                "ph_per_ec_ml": None,
                "ec_per_ph_ml": None,
                "transport_delay_sec": 99,
                "settle_sec": 99,
                "confidence": 0.1,
                "source": "should_not_override_alias_group",
                "valid_from": None,
                "valid_to": None,
                "is_active": True,
                "meta": {},
                "updated_at": None,
            },
        ]
    )

    assert "irrigation" in result
    assert result["irrigation"]["source"] == "legacy_irrigating"
    assert result["irrigation"]["transport_delay_sec"] == 12


def test_build_pid_state_preserves_wallclock_runtime_fields() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._build_pid_state(
        [
            {
                "pid_type": "ph",
                "integral": 1.25,
                "prev_error": -0.4,
                "prev_derivative": 0.02,
                "last_output_ms": 250,
                "last_dose_at": "2026-03-10T10:00:00Z",
                "hold_until": "2026-03-10T10:05:00Z",
                "last_measurement_at": "2026-03-10T10:04:30Z",
                "last_measured_value": 5.88,
                "feedforward_bias": 0.07,
                "no_effect_count": 2,
                "last_correction_kind": "ec",
                "stats": {"samples": 4},
                "current_zone": "tank_recirc",
                "updated_at": "2026-03-10T10:04:31Z",
            }
        ]
    )

    assert result["ph"]["hold_until"] == "2026-03-10T10:05:00Z"
    assert result["ph"]["last_measurement_at"] == "2026-03-10T10:04:30Z"
    assert result["ph"]["last_measured_value"] == 5.88
    assert result["ph"]["feedforward_bias"] == 0.07
    assert result["ph"]["no_effect_count"] == 2
    assert result["ph"]["last_correction_kind"] == "ec"


def test_build_pid_state_normalizes_aware_datetimes_to_naive_utc() -> None:
    read_model = PgZoneSnapshotReadModel()
    ts = datetime(2026, 3, 17, 12, 37, 31, tzinfo=timezone.utc)

    result = read_model._build_pid_state(
        [
            {
                "pid_type": "ec",
                "last_dose_at": ts,
                "hold_until": ts,
                "last_measurement_at": ts,
                "updated_at": ts,
            }
        ]
    )

    assert result["ec"]["last_dose_at"] == ts.replace(tzinfo=None)
    assert result["ec"]["hold_until"] == ts.replace(tzinfo=None)
    assert result["ec"]["last_measurement_at"] == ts.replace(tzinfo=None)
    assert result["ec"]["updated_at"] == ts.replace(tzinfo=None)


def test_build_correction_config_preserves_runtime_contract_fields() -> None:
    read_model = PgZoneSnapshotReadModel()
    row = {
        "version": 9,
        "resolved_config": {
            "base": {
                "runtime": {"clean_fill_timeout_sec": 777, "solution_max_sensor_label": "level_solution_max"},
                "timing": {"telemetry_max_age_sec": 123},
                "retry": {"max_ec_correction_attempts": 6},
                "dosing": {"solution_volume_l": 88.0},
            },
            "phases": {
                "solution_fill": {"timing": {"stabilization_sec": 31}},
                "tank_recirc": {"retry": {"prepare_recirculation_timeout_sec": 620}},
                "irrigation": {"tolerance": {"prepare_tolerance": {"ph_pct": 10.5}}},
            },
            "meta": {"preset_slug": "balanced"},
        },
        "phase_overrides": {
            "solution_fill": {"timing": {"stabilization_sec": 31}},
            "tank_recirc": {"retry": {"prepare_recirculation_timeout_sec": 620}},
        },
    }

    result = read_model._build_correction_config(row)

    assert result is not None
    assert result["base"]["runtime"]["clean_fill_timeout_sec"] == 777
    assert result["base"]["timing"]["telemetry_max_age_sec"] == 123
    assert result["base"]["retry"]["max_ec_correction_attempts"] == 6
    assert result["base"]["dosing"]["solution_volume_l"] == 88.0
    assert result["phases"]["solution_fill"]["timing"]["stabilization_sec"] == 31
    assert result["phases"]["tank_recirc"]["retry"]["prepare_recirculation_timeout_sec"] == 620
    assert result["phases"]["irrigation"]["tolerance"]["prepare_tolerance"]["ph_pct"] == 10.5
    assert result["meta"]["preset_slug"] == "balanced"
    assert result["meta"]["version"] == 9
    assert result["meta"]["phase_overrides"]["solution_fill"]["timing"]["stabilization_sec"] == 31


def test_extract_pump_calibration_merges_policy_with_db_calibration() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._extract_pump_calibration(
        {
            "channel_config": {},
            "calibration_ml_per_sec": 1.75,
            "calibration_k_ms_per_ml_l": 12.5,
            "calibration_component": "ec_a",
            "calibration_source": "e2e_realhw_setup_ready",
            "calibration_quality_score": 0.97,
            "calibration_sample_count": 4,
            "calibration_valid_from": "2026-03-25T00:00:00Z",
        },
        pump_calibration_policy={
            "min_dose_ms": 50,
            "ml_per_sec_min": 0.01,
            "ml_per_sec_max": 20.0,
        },
    )

    assert result is not None
    assert result["min_dose_ms"] == 50
    assert result["ml_per_sec_min"] == 0.01
    assert result["ml_per_sec_max"] == 20.0
    assert result["ml_per_sec"] == 1.75
    assert result["k_ms_per_ml_l"] == 12.5
    assert result["component"] == "ec_a"
    assert result["source"] == "e2e_realhw_setup_ready"
    assert result["sample_count"] == 4


def test_extract_pump_calibration_ignores_legacy_node_channel_config() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._extract_pump_calibration(
        {
            "channel_config": {
                "pump_calibration": {
                    "ml_per_sec": 7.5,
                    "k_ms_per_ml_l": 11.0,
                    "source": "legacy_config",
                    "min_dose_ms": 999,
                    "ml_per_sec_min": 9.9,
                    "ml_per_sec_max": 99.9,
                }
            },
            "calibration_ml_per_sec": None,
            "calibration_k_ms_per_ml_l": None,
            "calibration_component": None,
            "calibration_source": None,
            "calibration_quality_score": None,
            "calibration_sample_count": None,
            "calibration_valid_from": None,
        },
        pump_calibration_policy={
            "min_dose_ms": 50,
            "ml_per_sec_min": 0.01,
            "ml_per_sec_max": 20.0,
        },
    )

    assert result is not None
    assert result["min_dose_ms"] == 50
    assert result["ml_per_sec_min"] == 0.01
    assert result["ml_per_sec_max"] == 20.0
    assert "ml_per_sec" not in result
    assert "k_ms_per_ml_l" not in result
    assert result.get("source") is None


def test_bundle_correction_config_row_uses_bundle_meta_version() -> None:
    read_model = PgZoneSnapshotReadModel()

    result = read_model._bundle_correction_config_row(
        {
            "correction": {
                "resolved_config": {
                    "base": {"runtime": {"required_node_type": "irrig"}},
                    "phases": {},
                    "meta": {"version": 4},
                },
                "phase_overrides": {"solution_fill": {"timing": {"stabilization_sec": 12}}},
            }
        }
    )

    assert result is not None
    assert result["version"] == 4
    assert result["phase_overrides"]["solution_fill"]["timing"]["stabilization_sec"] == 12
