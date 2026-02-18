"""Unit tests for correction bounds safety policy."""

from types import SimpleNamespace

from services.correction_bounds_policy import (
    apply_target_rate_limit,
    extract_bounds_overrides,
    resolve_bounds,
    validate_target_with_bounds,
)


def _settings_stub():
    return SimpleNamespace(
        AE_SAFETY_PH_HARD_PCT=20.0,
        AE_SAFETY_PH_ABS_MIN=5.2,
        AE_SAFETY_PH_ABS_MAX=6.8,
        AE_SAFETY_PH_MAX_DELTA_PER_MIN=0.15,
        AE_SAFETY_EC_HARD_PCT=20.0,
        AE_SAFETY_EC_ABS_MIN=0.6,
        AE_SAFETY_EC_ABS_MAX=2.8,
        AE_SAFETY_EC_MAX_DELTA_PER_MIN=0.2,
    )


def test_resolve_bounds_prefers_overrides_over_targets_and_defaults():
    settings = _settings_stub()
    targets = {
        "ph": {
            "hard_pct": 12,
            "min": 5.4,
            "max": 6.6,
            "max_delta_per_min": 0.11,
        }
    }
    overrides = {"ph": {"hard_pct": 15, "abs_min": 5.3}}

    resolved = resolve_bounds("ph", targets, overrides, settings)

    assert resolved["hard_pct"] == 15.0
    assert resolved["abs_min"] == 5.3
    assert resolved["abs_max"] == 6.6
    assert resolved["max_delta_per_min"] == 0.11
    assert resolved["config_errors"] == []


def test_resolve_bounds_collects_configuration_errors():
    settings = _settings_stub()
    targets = {"ph": {"bounds": {"abs_min": "bad", "abs_max": 6.0, "hard_pct": 0}}}

    resolved = resolve_bounds("ph", targets, None, settings)

    assert "targets_abs_min_not_numeric" in resolved["config_errors"]
    assert "hard_pct_must_be_positive" in resolved["config_errors"]


def test_validate_target_with_bounds_rejects_abs_range_violation():
    bounds = {
        "hard_pct": 20.0,
        "abs_min": 5.2,
        "abs_max": 6.8,
        "max_delta_per_min": 0.15,
        "config_errors": [],
    }

    validation = validate_target_with_bounds(metric="ph", target=7.0, bounds=bounds)

    assert validation["valid"] is False
    assert validation["reason_code"] == "target_above_abs_max"


def test_validate_target_with_bounds_rejects_hard_pct_violation():
    bounds = {
        "hard_pct": 10.0,
        "abs_min": 5.0,
        "abs_max": 7.0,
        "max_delta_per_min": 0.15,
        "config_errors": [],
    }

    validation = validate_target_with_bounds(
        metric="ph",
        target=6.9,
        bounds=bounds,
        previous_target=6.0,
    )

    assert validation["valid"] is False
    assert validation["reason_code"] == "target_hard_pct_violation"
    assert validation["details"]["safe_max"] == 6.6


def test_apply_target_rate_limit_clamps_target_delta():
    result = apply_target_rate_limit(
        target=6.8,
        bounds={"max_delta_per_min": 0.15},
        previous_target=6.0,
        elapsed_seconds=60.0,
    )

    assert result["clamped"] is True
    assert result["target"] == 6.15
    assert result["reason_code"] == "max_delta_per_min_clamped"


def test_extract_bounds_overrides_merges_known_runtime_paths():
    targets = {
        "bounds": {"ph": {"hard_pct": 10}},
        "execution": {"bounds": {"ph": {"abs_min": 5.1}}},
        "diagnostics": {"execution": {"bounds": {"ph": {"abs_max": 6.7}}}},
        "extensions": {"safety": {"bounds": {"ph": {"max_delta_per_min": 0.12}}}},
    }

    overrides = extract_bounds_overrides(targets)

    assert overrides["ph"]["hard_pct"] == 10
    assert overrides["ph"]["abs_min"] == 5.1
    assert overrides["ph"]["abs_max"] == 6.7
    assert overrides["ph"]["max_delta_per_min"] == 0.12
