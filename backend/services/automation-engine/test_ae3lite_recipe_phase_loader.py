"""Tests for `ae3lite.config.loader.load_recipe_phase` (Phase 2 / B4 audit fix).

Mirrors `schemas/recipe_phase.v1.json`. Required for Phase 5 live-mode
hot-reload of recipe phase (Q4 in plan).
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.loader import load_recipe_phase
from ae3lite.config.schema import RecipePhase


def _valid_recipe_phase() -> dict:
    return {
        "phase_targets": {
            "ph": {"target": 6.0, "min": 5.5, "max": 6.5},
            "ec": {"target": 1.8, "min": 1.5, "max": 2.1},
            "day_night_enabled": False,
            "ec_component_ratios": {"npk_ec_share": 0.85},
        },
        "targets": {
            "irrigation": {
                "correction_during_irrigation": True,
                "correction_slack_sec": 900,
                "stage_timeout_sec": 3600,
            },
            "extensions": {
                "subsystems": {
                    "irrigation": {
                        "decision": {
                            "strategy": "smart_soil_v1",
                            "lookback_sec": 1800,
                            "min_samples": 3,
                            "stale_threshold_sec": 600,
                            "hysteresis_percent": 2.0,
                        },
                        "recovery": {
                            "max_continue_attempts": 5,
                            "timeout_sec": 600,
                            "max_replays": 1,
                        },
                    },
                },
            },
        },
        "diagnostics_execution": {
            "two_tank_commands": {
                "irrigation_start": [
                    {"channel": "valve_solution_supply", "cmd": "set_relay",
                     "params": {"state": True}},
                ],
            },
            "fail_safe_guards": {
                "clean_fill_min_check_delay_ms": 5000,
                "solution_fill_min_check_delay_ms": 5000,
                "solution_fill_max_check_delay_ms": 15000,
                "estop_debounce_ms": 80,
            },
            "startup": {"irr_state_wait_timeout_sec": 5.0},
        },
    }


# ─── Happy path ────────────────────────────────────────────────────────────

def test_canonical_payload_accepted() -> None:
    model = load_recipe_phase(_valid_recipe_phase(), zone_id=42, cycle_id=99)
    assert isinstance(model, RecipePhase)
    assert model.phase_targets.ph.target == pytest.approx(6.0)
    assert model.targets.irrigation.correction_during_irrigation is True
    assert model.diagnostics_execution.startup.irr_state_wait_timeout_sec == pytest.approx(5.0)


def test_minimum_required_only() -> None:
    """All optional fields stripped — must still validate."""
    payload = {
        "phase_targets": {"ph": {"target": 6.0}, "ec": {"target": 1.8}},
        "targets": {},
        "diagnostics_execution": {
            "two_tank_commands": {},
            "fail_safe_guards": {
                "clean_fill_min_check_delay_ms": 5000,
                "solution_fill_min_check_delay_ms": 5000,
                "solution_fill_max_check_delay_ms": 15000,
                "estop_debounce_ms": 80,
            },
            "startup": {"irr_state_wait_timeout_sec": 5.0},
        },
    }
    model = load_recipe_phase(payload)
    assert model.targets.irrigation is None
    assert model.targets.extensions is None


def test_model_is_frozen() -> None:
    model = load_recipe_phase(_valid_recipe_phase())
    with pytest.raises(Exception):
        model.phase_targets.ph.target = 7.0  # type: ignore[misc]


# ─── Errors ────────────────────────────────────────────────────────────────

def test_rejects_ph_above_physical_bound() -> None:
    p = _valid_recipe_phase()
    p["phase_targets"]["ph"]["target"] = 14.5
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_rejects_ec_above_physical_bound() -> None:
    p = _valid_recipe_phase()
    p["phase_targets"]["ec"]["target"] = 25.0
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_rejects_unknown_irrigation_strategy() -> None:
    p = _valid_recipe_phase()
    p["targets"]["extensions"]["subsystems"]["irrigation"]["decision"]["strategy"] = "experimental"
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_rejects_missing_diagnostics_execution() -> None:
    p = _valid_recipe_phase()
    del p["diagnostics_execution"]
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_rejects_unknown_top_level_field() -> None:
    p = _valid_recipe_phase()
    p["unknown_section"] = {"x": 1}
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_rejects_command_with_unknown_cmd() -> None:
    p = _valid_recipe_phase()
    p["diagnostics_execution"]["two_tank_commands"]["irrigation_start"] = [
        {"channel": "valve_x", "cmd": "fly_to_moon"},
    ]
    with pytest.raises(ConfigValidationError):
        load_recipe_phase(p)


def test_error_carries_zone_id_and_namespace() -> None:
    p = _valid_recipe_phase()
    del p["phase_targets"]["ph"]
    with pytest.raises(ConfigValidationError) as exc:
        load_recipe_phase(p, zone_id=11, namespace="recipe.phase:cycle.42")
    assert exc.value.zone_id == 11
    assert exc.value.namespace == "recipe.phase:cycle.42"


def test_independent_copies_dont_cross_contaminate() -> None:
    p1 = _valid_recipe_phase()
    p2 = deepcopy(p1)
    p2["phase_targets"]["ph"]["target"] = 7.2
    m1 = load_recipe_phase(p1)
    m2 = load_recipe_phase(p2)
    assert m1.phase_targets.ph.target == pytest.approx(6.0)
    assert m2.phase_targets.ph.target == pytest.approx(7.2)
