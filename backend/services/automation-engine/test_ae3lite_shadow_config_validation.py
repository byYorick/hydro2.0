"""Unit tests для shadow validation hook в CycleStartPlanner (Phase 2 / B2 audit fix).

Покрывает `CycleStartPlanner._shadow_validate_correction` — 4 кодовых пути:
  1. snapshot.correction_config is None / not Mapping → result=invalid
  2. correction_config exists but no base/phases → result=invalid
  3. all targets (base + 3 phases) valid → result=ok
  4. one phase invalid → result=invalid + WARNING log

Использует `SHADOW_CONFIG_VALIDATION` Prometheus counter напрямую.
Snapshot — `SimpleNamespace` (стандартный паттерн в AE3 unit-тестах).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ae3lite.domain.services import CycleStartPlanner
from ae3lite.infrastructure.metrics import SHADOW_CONFIG_VALIDATION


# ─── Helpers ───────────────────────────────────────────────────────────────

def _counter_value(result: str, namespace: str = "zone.correction") -> float:
    """Read current Prometheus counter value for given labels."""
    return SHADOW_CONFIG_VALIDATION.labels(
        result=result, namespace=namespace,
    )._value.get()


def _valid_base_payload() -> dict:
    """Minimum valid `base` per zone_correction.v1.json schema."""
    return {
        "controllers": {
            "ph": {
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
            },
            "ec": {
                "mode": "supervisory_allocator",
                "kp": 0.55, "ki": 0.03, "kd": 0.0,
                "derivative_filter_alpha": 0.35, "deadband": 0.06,
                "max_dose_ml": 80.0, "min_interval_sec": 25, "max_integral": 20.0,
                "anti_windup": {"enabled": True},
                "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                "no_effect": {"enabled": True, "max_count": 4},
                "observe": {
                    "telemetry_period_sec": 2, "window_min_samples": 3,
                    "decision_window_sec": 8, "observe_poll_sec": 2,
                    "min_effect_fraction": 0.15, "stability_max_slope": 0.08,
                    "no_effect_consecutive_limit": 4,
                },
            },
        },
        "runtime": {
            "required_node_type": "irrig",
            "clean_fill_timeout_sec": 1200, "solution_fill_timeout_sec": 900,
            "clean_fill_retry_cycles": 1, "level_switch_on_threshold": 0.5,
            "clean_max_sensor_label": "level_clean_max",
            "clean_min_sensor_label": "level_clean_min",
            "solution_max_sensor_label": "level_solution_max",
            "solution_min_sensor_label": "level_solution_min",
        },
        "timing": {
            "sensor_mode_stabilization_time_sec": 8, "stabilization_sec": 8,
            "telemetry_max_age_sec": 10, "irr_state_max_age_sec": 30,
            "level_poll_interval_sec": 10,
        },
        "dosing": {
            "solution_volume_l": 100.0, "dose_ec_channel": "pump_a",
            "dose_ph_up_channel": "pump_base", "dose_ph_down_channel": "pump_acid",
            "max_ec_dose_ml": 80.0, "max_ph_dose_ml": 35.0,
            "ec_dosing_mode": "single",
        },
        "retry": {
            "max_ec_correction_attempts": 8, "max_ph_correction_attempts": 8,
            "prepare_recirculation_timeout_sec": 900,
            "prepare_recirculation_correction_slack_sec": 0,
            "prepare_recirculation_max_attempts": 4,
            "prepare_recirculation_max_correction_attempts": 40,
            "telemetry_stale_retry_sec": 30, "decision_window_retry_sec": 10,
            "low_water_retry_sec": 60,
        },
        "tolerance": {"prepare_tolerance": {"ph_pct": 5.0, "ec_pct": 10.0}},
        "safety": {"safe_mode_on_no_effect": True, "block_on_active_no_effect_alert": True},
    }


def _make_snapshot(correction_config) -> SimpleNamespace:
    return SimpleNamespace(correction_config=correction_config)


def _make_task(zone_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(zone_id=zone_id)


# ─── Tests ─────────────────────────────────────────────────────────────────

def test_shadow_invalid_when_correction_config_is_none() -> None:
    planner = CycleStartPlanner()
    before = _counter_value("invalid")
    planner._shadow_validate_correction(
        snapshot=_make_snapshot(None), task=_make_task(),
    )
    assert _counter_value("invalid") == before + 1


def test_shadow_invalid_when_correction_config_is_not_mapping() -> None:
    planner = CycleStartPlanner()
    before = _counter_value("invalid")
    planner._shadow_validate_correction(
        snapshot=_make_snapshot([1, 2, 3]), task=_make_task(),
    )
    assert _counter_value("invalid") == before + 1


def test_shadow_invalid_when_no_base_or_phases() -> None:
    planner = CycleStartPlanner()
    before = _counter_value("invalid")
    planner._shadow_validate_correction(
        snapshot=_make_snapshot({"meta": {"version": 1}}),
        task=_make_task(),
    )
    assert _counter_value("invalid") == before + 1


def test_shadow_ok_when_all_targets_valid(caplog) -> None:
    base = _valid_base_payload()
    correction_config = {
        "base": base,
        "phases": {
            "solution_fill": deepcopy(base),
            "tank_recirc": deepcopy(base),
            "irrigation": deepcopy(base),
        },
        "meta": {"version": 1},
    }
    planner = CycleStartPlanner()
    before_ok = _counter_value("ok")
    before_invalid = _counter_value("invalid")

    with caplog.at_level(logging.WARNING, logger="ae3lite.domain.services.cycle_start_planner"):
        planner._shadow_validate_correction(
            snapshot=_make_snapshot(correction_config), task=_make_task(),
        )

    assert _counter_value("ok") == before_ok + 1
    assert _counter_value("invalid") == before_invalid  # unchanged
    # No WARNING expected when all valid
    assert not any(
        rec.levelno == logging.WARNING and "ae3_shadow_config_validation_failed" in rec.message
        for rec in caplog.records
    )


def test_shadow_invalid_when_one_phase_breaks(caplog) -> None:
    base = _valid_base_payload()
    broken_phase = deepcopy(base)
    del broken_phase["retry"]  # required section removed
    correction_config = {
        "base": base,
        "phases": {
            "solution_fill": deepcopy(base),
            "tank_recirc": broken_phase,
            "irrigation": deepcopy(base),
        },
    }
    planner = CycleStartPlanner()
    before = _counter_value("invalid")

    with caplog.at_level(logging.WARNING, logger="ae3lite.domain.services.cycle_start_planner"):
        planner._shadow_validate_correction(
            snapshot=_make_snapshot(correction_config), task=_make_task(zone_id=42),
        )

    assert _counter_value("invalid") == before + 1
    # WARNING expected for the broken phase, with zone_id and namespace populated
    failed_logs = [
        rec for rec in caplog.records
        if rec.levelno == logging.WARNING and "ae3_shadow_config_validation_failed" in rec.message
    ]
    assert len(failed_logs) == 1
    assert failed_logs[0].zone_id == 42
    assert failed_logs[0].namespace == "zone.correction:phases.tank_recirc"
