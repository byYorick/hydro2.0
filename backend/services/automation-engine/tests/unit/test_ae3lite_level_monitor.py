"""Unit tests for level_monitor helpers."""

from __future__ import annotations

from ae3lite.domain.level_switch_semantics import level_switch_is_triggered


def test_level_switch_is_triggered_binary_values() -> None:
    assert level_switch_is_triggered(0.0, threshold=0.5) is False
    assert level_switch_is_triggered(1.0, threshold=0.5) is True
    assert level_switch_is_triggered(0.5, threshold=0.5) is True


def test_level_switch_is_triggered_rejects_analog_outliers() -> None:
    """Значение вне [0, 1] неизвестно: не «полон» и не подтверждённый OFF."""
    from datetime import datetime, timedelta

    from ae3lite.domain.level_switch_semantics import confirmed_level_switch, newer_level_sample

    assert level_switch_is_triggered(100.0, threshold=0.5) is None
    assert level_switch_is_triggered(14500.0, threshold=0.5) is None
    assert level_switch_is_triggered(-1.0, threshold=0.5) is None
    assert confirmed_level_switch(value=100.0, threshold=0.5) == (False, False)
    assert confirmed_level_switch(value=0.0, threshold=0.5) == (True, False)
    assert confirmed_level_switch(value=1.0, threshold=0.5) == (True, True)

    older = {"sample_ts": datetime(2026, 10, 18, 12, 0, 0), "is_triggered": False}
    newer = {"sample_ts": older["sample_ts"] + timedelta(seconds=20), "is_triggered": True}
    assert newer_level_sample(older, newer) is newer
    assert newer_level_sample(newer, older) is newer
