"""Tests for BUG-6: _WARNED_SCHEMA_KEYS memory leak prevention."""
from __future__ import annotations

from services.targets_accessor import (
    _WARNED_SCHEMA_KEYS,
    _WARNED_SCHEMA_KEYS_MAX_SIZE,
    _warn_schema_mismatch,
    get_ventilation_pwm_params,
    get_recirculation_params,
)


def test_warned_schema_keys_max_size_defined():
    assert _WARNED_SCHEMA_KEYS_MAX_SIZE > 0
    assert _WARNED_SCHEMA_KEYS_MAX_SIZE <= 10000


def test_warned_schema_keys_clears_at_max_size():
    original = list(_WARNED_SCHEMA_KEYS.items())
    try:
        _WARNED_SCHEMA_KEYS.clear()

        for i in range(_WARNED_SCHEMA_KEYS_MAX_SIZE):
            _WARNED_SCHEMA_KEYS[(i, "test", f"detail_{i}")] = None

        assert len(_WARNED_SCHEMA_KEYS) == _WARNED_SCHEMA_KEYS_MAX_SIZE
        oldest = next(iter(_WARNED_SCHEMA_KEYS))

        _warn_schema_mismatch("test", _WARNED_SCHEMA_KEYS_MAX_SIZE + 1, "overflow")

        assert len(_WARNED_SCHEMA_KEYS) == _WARNED_SCHEMA_KEYS_MAX_SIZE
        assert oldest not in _WARNED_SCHEMA_KEYS
    finally:
        _WARNED_SCHEMA_KEYS.clear()
        for key, value in original:
            _WARNED_SCHEMA_KEYS[key] = value


def test_get_recirculation_params_returns_tuple():
    result = get_recirculation_params({})
    assert isinstance(result, tuple)
    assert len(result) == 3
    enabled, interval, duration = result
    assert enabled is False
    assert interval is None
    assert duration is None


def test_get_ventilation_pwm_params_from_execution_params():
    targets = {
        "ventilation": {
            "execution": {
                "params": {
                    "humidity_high_pwm": 73,
                    "humidity_normal_pwm": 41,
                }
            }
        }
    }
    high, normal = get_ventilation_pwm_params(targets)
    assert high == 73
    assert normal == 41
