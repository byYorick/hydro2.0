"""Unit tests for level_monitor helpers."""

from __future__ import annotations

from ae3lite.domain.level_switch_semantics import level_switch_is_triggered


def test_level_switch_is_triggered_binary_values() -> None:
    assert level_switch_is_triggered(0.0, threshold=0.5) is False
    assert level_switch_is_triggered(1.0, threshold=0.5) is True
    assert level_switch_is_triggered(0.5, threshold=0.5) is True


def test_level_switch_is_triggered_rejects_analog_outliers() -> None:
    """Analog/raw values must not read as latched full tank."""
    assert level_switch_is_triggered(100.0, threshold=0.5) is False
    assert level_switch_is_triggered(14500.0, threshold=0.5) is False
    assert level_switch_is_triggered(-1.0, threshold=0.5) is False
