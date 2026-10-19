"""Семантика дискретных датчиков уровня (WATER_LEVEL_SWITCH)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def level_switch_is_triggered(value: Any, *, threshold: float) -> bool | None:
    try:
        normalized = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if normalized is None:
        return None
    # Вне [0, 1] это не дискретный датчик. None = неизвестно, не подтверждённый OFF:
    # иначе процент/ADC читается как «бак пуст» и набор продолжается.
    if normalized > 1.0 or normalized < 0.0:
        return None
    return normalized >= float(threshold)


def confirmed_level_switch(*, value: Any, threshold: float) -> tuple[bool, bool]:
    """(есть подтверждённое чтение, датчик сработал).

    Значение вне [0, 1] не является чтением: вызывающий код должен идти в
    unavailable, а не считать бак пустым.
    """
    triggered = level_switch_is_triggered(value, threshold=threshold)
    if triggered is None:
        return False, False
    return True, bool(triggered)


def newer_level_sample(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Более поздний sample_ts. При равных или отсутствующих метках остаётся left."""
    if not isinstance(left, Mapping):
        return right if isinstance(right, Mapping) else None
    if not isinstance(right, Mapping):
        return left
    left_ts = left.get("sample_ts")
    right_ts = right.get("sample_ts")
    if isinstance(right_ts, datetime) and (
        not isinstance(left_ts, datetime) or right_ts > left_ts
    ):
        return right
    return left
