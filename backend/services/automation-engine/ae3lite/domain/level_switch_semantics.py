"""Семантика дискретных датчиков уровня (WATER_LEVEL_SWITCH)."""

from __future__ import annotations

from typing import Any


def level_switch_is_triggered(value: Any, *, threshold: float) -> bool | None:
    try:
        normalized = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if normalized is None:
        return None
    # WATER_LEVEL_SWITCH telemetry must be binary 0/1. Analog/raw values (e.g. ADC
    # or misrouted WATER_LEVEL ratio) must not read as "tank full" at threshold 0.5.
    if normalized > 1.0:
        return False
    if normalized < 0.0:
        return False
    return normalized >= float(threshold)
