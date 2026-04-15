"""Tests for `ae3lite.config.loader` (Phase 2).

Scope: happy path + common failure modes. Does NOT hit DB — pure data
validation against canonical JSON Schema mirror.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.loader import load_zone_correction
from ae3lite.config.schema import ZoneCorrection


def _valid_payload() -> dict:
    """Canonical minimal zone.correction base config matching schema v1.

    Mirrors ZoneCorrectionConfigCatalog::defaults() from PHP side (after
    Phase 1 patch: includes ec_dosing_mode + prepare_recirculation_correction_slack_sec).
    """
    return {
        "controllers": {
            "ph": {
                "mode": "cross_coupled_pi_d",
                "kp": 0.28,
                "ki": 0.015,
                "kd": 0.0,
                "derivative_filter_alpha": 0.35,
                "deadband": 0.04,
                "max_dose_ml": 35.0,
                "min_interval_sec": 20,
                "max_integral": 12.0,
                "anti_windup": {"enabled": True},
                "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
                "no_effect": {"enabled": True, "max_count": 4},
                "observe": {
                    "telemetry_period_sec": 2,
                    "window_min_samples": 3,
                    "decision_window_sec": 8,
                    "observe_poll_sec": 2,
                    "min_effect_fraction": 0.15,
                    "stability_max_slope": 0.04,
                    "no_effect_consecutive_limit": 4,
                },
            },
            "ec": {
                "mode": "supervisory_allocator",
                "kp": 0.55,
                "ki": 0.03,
                "kd": 0.0,
                "derivative_filter_alpha": 0.35,
                "deadband": 0.06,
                "max_dose_ml": 80.0,
                "min_interval_sec": 25,
                "max_integral": 20.0,
                "anti_windup": {"enabled": True},
                "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                "no_effect": {"enabled": True, "max_count": 4},
                "observe": {
                    "telemetry_period_sec": 2,
                    "window_min_samples": 3,
                    "decision_window_sec": 8,
                    "observe_poll_sec": 2,
                    "min_effect_fraction": 0.15,
                    "stability_max_slope": 0.08,
                    "no_effect_consecutive_limit": 4,
                },
            },
        },
        "runtime": {
            "required_node_type": "irrig",
            "clean_fill_timeout_sec": 1200,
            "solution_fill_timeout_sec": 900,
            "clean_fill_retry_cycles": 1,
            "level_switch_on_threshold": 0.5,
            "clean_max_sensor_label": "level_clean_max",
            "clean_min_sensor_label": "level_clean_min",
            "solution_max_sensor_label": "level_solution_max",
            "solution_min_sensor_label": "level_solution_min",
        },
        "timing": {
            "sensor_mode_stabilization_time_sec": 8,
            "stabilization_sec": 8,
            "telemetry_max_age_sec": 10,
            "irr_state_max_age_sec": 30,
            "level_poll_interval_sec": 10,
        },
        "dosing": {
            "solution_volume_l": 100.0,
            "dose_ec_channel": "pump_a",
            "dose_ph_up_channel": "pump_base",
            "dose_ph_down_channel": "pump_acid",
            "max_ec_dose_ml": 80.0,
            "max_ph_dose_ml": 35.0,
            "ec_dosing_mode": "single",
        },
        "retry": {
            "max_ec_correction_attempts": 8,
            "max_ph_correction_attempts": 8,
            "prepare_recirculation_timeout_sec": 900,
            "prepare_recirculation_correction_slack_sec": 0,
            "prepare_recirculation_max_attempts": 4,
            "prepare_recirculation_max_correction_attempts": 40,
            "telemetry_stale_retry_sec": 30,
            "decision_window_retry_sec": 10,
            "low_water_retry_sec": 60,
        },
        "tolerance": {
            "prepare_tolerance": {"ph_pct": 5.0, "ec_pct": 10.0},
        },
        "safety": {
            "safe_mode_on_no_effect": True,
            "block_on_active_no_effect_alert": True,
        },
    }


# ─── Happy path ────────────────────────────────────────────────────────────

def test_canonical_payload_is_accepted() -> None:
    model = load_zone_correction(_valid_payload(), zone_id=42)
    assert isinstance(model, ZoneCorrection)
    assert model.controllers.ph.kp == pytest.approx(0.28)
    assert model.dosing.ec_dosing_mode == "single"
    assert model.retry.prepare_recirculation_correction_slack_sec == 0


def test_ec_dosing_mode_multi_parallel_accepted() -> None:
    payload = _valid_payload()
    payload["dosing"]["ec_dosing_mode"] = "multi_parallel"
    model = load_zone_correction(payload, zone_id=42)
    assert model.dosing.ec_dosing_mode == "multi_parallel"


def test_model_is_frozen() -> None:
    model = load_zone_correction(_valid_payload())
    # Pydantic v2 frozen ConfigDict raises on assignment.
    with pytest.raises(Exception):
        model.runtime.clean_fill_timeout_sec = 9999  # type: ignore[misc]


# ─── Type / shape errors ───────────────────────────────────────────────────

def test_rejects_non_mapping_payload() -> None:
    with pytest.raises(ConfigValidationError):
        load_zone_correction([1, 2, 3], zone_id=5)  # type: ignore[arg-type]


def test_rejects_missing_top_level_section() -> None:
    payload = _valid_payload()
    del payload["retry"]
    with pytest.raises(ConfigValidationError) as exc:
        load_zone_correction(payload)
    # Loc path should include 'retry'
    locs = [tuple(e["loc"]) for e in exc.value.errors]
    assert any("retry" in loc for loc in locs)


def test_rejects_unknown_top_level_field() -> None:
    payload = _valid_payload()
    payload["extra_section"] = {"x": 1}
    with pytest.raises(ConfigValidationError) as exc:
        load_zone_correction(payload)
    types = [e["type"] for e in exc.value.errors]
    assert any("extra" in t for t in types)


def test_rejects_unknown_nested_field() -> None:
    payload = _valid_payload()
    payload["runtime"]["undocumented_knob"] = True
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


# ─── Value / constraint errors ────────────────────────────────────────────

def test_rejects_ec_dosing_mode_unknown_enum() -> None:
    payload = _valid_payload()
    payload["dosing"]["ec_dosing_mode"] = "experimental"
    with pytest.raises(ConfigValidationError) as exc:
        load_zone_correction(payload)
    assert any("dosing" in e["loc"] for e in exc.value.errors)


def test_rejects_negative_timeout() -> None:
    payload = _valid_payload()
    payload["runtime"]["clean_fill_timeout_sec"] = -1
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


def test_rejects_ph_out_of_physical_bounds() -> None:
    payload = _valid_payload()
    payload["controllers"]["ph"]["overshoot_guard"]["hard_max"] = 15.5  # > 14
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


def test_rejects_ec_hard_max_out_of_bounds() -> None:
    payload = _valid_payload()
    payload["controllers"]["ec"]["overshoot_guard"]["hard_max"] = 25.0  # > 20
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


def test_rejects_wrong_ph_controller_mode() -> None:
    payload = _valid_payload()
    payload["controllers"]["ph"]["mode"] = "supervisory_allocator"  # EC mode on pH
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


def test_rejects_zero_max_integral() -> None:
    payload = _valid_payload()
    payload["controllers"]["ph"]["max_integral"] = 0.0  # must be > 0
    with pytest.raises(ConfigValidationError):
        load_zone_correction(payload)


def test_error_carries_zone_id_and_namespace() -> None:
    payload = _valid_payload()
    del payload["safety"]
    with pytest.raises(ConfigValidationError) as exc:
        load_zone_correction(payload, zone_id=777, namespace="zone.correction:phase.irrigation")
    assert exc.value.zone_id == 777
    assert exc.value.namespace == "zone.correction:phase.irrigation"
    assert len(exc.value.errors) >= 1


def test_independent_copies_dont_cross_contaminate() -> None:
    """Loader must accept two independent payloads in sequence."""
    p1 = _valid_payload()
    p2 = deepcopy(p1)
    p2["dosing"]["ec_dosing_mode"] = "multi_parallel"
    m1 = load_zone_correction(p1)
    m2 = load_zone_correction(p2)
    assert m1.dosing.ec_dosing_mode == "single"
    assert m2.dosing.ec_dosing_mode == "multi_parallel"
