"""Тесты safety-guards в correction pipeline.

Покрывает:
- max_dose_ms clamp в `_dose_ml_to_ms` (runaway pump protection)
- sanity bounds на telemetry в `BaseStageHandler._sensor_value_in_bounds`
- fail-closed на duplicate channels в multi_parallel dosing
"""
from __future__ import annotations

import pytest

from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_planner import (
    _assert_distinct_parallel_actuators,
    _dose_ml_to_ms,
)


# ── max_dose_ms clamp ─────────────────────────────────────────────────────────


class TestDoseMlToMsMaxDoseClamp:
    CORRECTION_CFG_BASE = {
        "pump_calibration": {
            "min_dose_ms": 100,
            "max_dose_ms": 60_000,  # explicit lower cap для тестов
            "ml_per_sec_min": 0.1,
            "ml_per_sec_max": 10.0,
        },
    }

    def test_normal_dose_returns_duration(self) -> None:
        dose_ms, reason, _ = _dose_ml_to_ms(
            1.0,  # dose_ml
            {"ml_per_sec": 1.0},
            self.CORRECTION_CFG_BASE,
        )
        assert dose_ms == 1000
        assert reason == ""

    def test_dose_clamped_to_max_dose_ms(self) -> None:
        # dose=10ml @ 0.1 ml/s = 100_000 ms > max=60_000 → clamped
        dose_ms, reason, details = _dose_ml_to_ms(
            10.0,
            {"ml_per_sec": 0.1},
            self.CORRECTION_CFG_BASE,
        )
        assert dose_ms == 60_000
        assert reason == "clamped_to_max_dose_ms"
        assert details["computed_duration_ms"] == 100_000
        assert details["max_dose_ms"] == 60_000

    def test_below_min_dose_still_discarded(self) -> None:
        # dose=0.05ml @ 1ml/s = 50ms < min=100 → discard
        dose_ms, reason, _ = _dose_ml_to_ms(
            0.05,
            {"ml_per_sec": 1.0},
            self.CORRECTION_CFG_BASE,
        )
        assert dose_ms == 0
        assert reason == "below_min_dose_ms"

    def test_invalid_max_dose_ms_fails_fast(self) -> None:
        cfg = {
            "pump_calibration": {
                "min_dose_ms": 1000,
                "max_dose_ms": 500,  # max < min → invalid
                "ml_per_sec_min": 0.1,
                "ml_per_sec_max": 10.0,
            },
        }
        with pytest.raises(PlannerConfigurationError, match="max_dose_ms"):
            _dose_ml_to_ms(1.0, {"ml_per_sec": 1.0}, cfg)

    def test_default_max_dose_ms_5min_when_not_configured(self) -> None:
        cfg = {
            "pump_calibration": {
                "min_dose_ms": 100,
                "ml_per_sec_min": 0.1,
                "ml_per_sec_max": 10.0,
                # max_dose_ms не указан → дефолт 300_000 (5 мин)
            },
        }
        # 10 min duration → clamp до 5 min
        dose_ms, reason, _ = _dose_ml_to_ms(
            60.0,  # 60ml @ 0.1ml/s = 600_000 ms
            {"ml_per_sec": 0.1},
            cfg,
        )
        assert dose_ms == 300_000
        assert reason == "clamped_to_max_dose_ms"


# ── sensor sanity bounds ──────────────────────────────────────────────────────


class TestSensorValueInBounds:

    def test_ph_within_bounds(self) -> None:
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=5.8) is True
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=0.0) is True
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=14.0) is True

    def test_ph_out_of_bounds(self) -> None:
        # Типичный error code -1 (disconnect)
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=-1.0) is False
        # Absurdly high
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=99.0) is False
        # Slightly above upper bound
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=14.5) is False

    def test_ec_within_bounds(self) -> None:
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=1.5) is True
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=0.0) is True
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=20.0) is True

    def test_ec_out_of_bounds(self) -> None:
        # Short-circuit error code 999
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=999.0) is False
        # Negative
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=-0.1) is False

    def test_non_numeric_returns_false(self) -> None:
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value="bad") is False
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="PH", value=None) is False

    def test_nan_and_inf_return_false(self) -> None:
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=float("nan")) is False
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=float("inf")) is False
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="EC", value=float("-inf")) is False

    def test_unknown_sensor_type_passes_through(self) -> None:
        # Для других типов bounds не определены → проходит (только finite check)
        assert BaseStageHandler._sensor_value_in_bounds(sensor_type="TEMPERATURE", value=25.0) is True


# ── multi_parallel distinct channels ─────────────────────────────────────────


class TestAssertDistinctParallelActuators:

    def test_distinct_actuators_pass(self) -> None:
        actuators = {
            "calcium": {"node_uid": "ec-node-1", "channel": "pump_ca"},
            "magnesium": {"node_uid": "ec-node-1", "channel": "pump_mg"},
            "micro": {"node_uid": "ec-node-2", "channel": "pump_micro"},
        }
        # Не должно выбросить
        _assert_distinct_parallel_actuators(actuators)

    def test_duplicate_channel_fails_closed(self) -> None:
        actuators = {
            "calcium": {"node_uid": "ec-node-1", "channel": "pump_shared"},
            "magnesium": {"node_uid": "ec-node-1", "channel": "pump_shared"},
        }
        with pytest.raises(PlannerConfigurationError, match="distinct"):
            _assert_distinct_parallel_actuators(actuators)

    def test_different_nodes_same_channel_name_ok(self) -> None:
        # Разные ноды — different (node_uid, channel) tuples
        actuators = {
            "calcium": {"node_uid": "ec-node-1", "channel": "pump_main"},
            "magnesium": {"node_uid": "ec-node-2", "channel": "pump_main"},
        }
        _assert_distinct_parallel_actuators(actuators)

    def test_case_insensitive_comparison(self) -> None:
        actuators = {
            "calcium": {"node_uid": "EC-NODE-1", "channel": "PUMP_CA"},
            "magnesium": {"node_uid": "ec-node-1", "channel": "pump_ca"},
        }
        with pytest.raises(PlannerConfigurationError, match="distinct"):
            _assert_distinct_parallel_actuators(actuators)

    def test_aliases_for_same_component_are_deduped(self) -> None:
        actuators = {
            "pump_a": {"node_uid": "ec-node-1", "channel": "pump_a"},
            "ec_npk_pump": {"node_uid": "ec-node-1", "channel": "pump_a"},
            "dose_ec_a": {"node_uid": "ec-node-1", "channel": "pump_a"},
        }
        _assert_distinct_parallel_actuators(actuators)

    def test_empty_actuator_entries_skipped(self) -> None:
        # Нестроковые/пустые значения просто пропускаются, не вызывают ложный conflict
        actuators = {
            "calcium": {"node_uid": "", "channel": "pump_ca"},
            "magnesium": {"node_uid": None, "channel": "pump_mg"},
            "micro": "not_a_mapping",
        }
        _assert_distinct_parallel_actuators(actuators)
