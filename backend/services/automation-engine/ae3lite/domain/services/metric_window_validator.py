"""Shared sanity bounds and decision-window value validation for PH/EC telemetry."""

from __future__ import annotations

import math
from typing import Any

PH_MIN = 0.0
PH_MAX = 14.0
EC_MIN = 0.0
EC_MAX = 20.0

SENSOR_OUT_OF_BOUNDS_REASON = "sensor_out_of_bounds"


def sensor_value_in_bounds(*, sensor_type: str, value: Any) -> bool:
    """Return True when ``value`` is physically valid for ``sensor_type``.

    Bounds are absolute sanity limits (not recipe targets). They filter explicit
    sensor error codes such as pH=-1 on disconnect or EC=999 on short-circuit.
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(numeric):
        return False
    key = (sensor_type or "").strip().upper()
    if key == "PH":
        return PH_MIN <= numeric <= PH_MAX
    if key == "EC":
        return EC_MIN <= numeric <= EC_MAX
    return True


def decision_window_bounds_reason(*, sensor_type: str, value: Any) -> str | None:
    """Return ``sensor_out_of_bounds`` when value fails sanity bounds, else None."""
    if sensor_value_in_bounds(sensor_type=sensor_type, value=value):
        return None
    return SENSOR_OUT_OF_BOUNDS_REASON
