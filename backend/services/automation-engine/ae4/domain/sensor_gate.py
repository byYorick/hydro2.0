"""Границы датчика и свежесть. Не обновлять как норму вне диапазона."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from ae4.domain.planting import TelemetrySample

PH_MIN = 0.0
PH_MAX = 14.0
EC_MIN = 0.0
EC_MAX = 20.0


def sensor_value_in_bounds(*, sensor_type: str, value: Any) -> bool:
    """pH ∈ [0, 14], EC ∈ [0, 20]. Вне — не норма."""
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


def sample_in_bounds(*, sample: TelemetrySample) -> bool:
    return sensor_value_in_bounds(sensor_type=sample.metric_type, value=sample.value)


def is_fresh(
    *,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> bool:
    """Нет telemetry_max_age_sec — датчик протух. Своё число секунд не вводится."""
    if sample is None or telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return False
    ts = sample.ts
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    now_naive = now
    if now_naive.tzinfo is not None:
        now_naive = now_naive.astimezone(timezone.utc).replace(tzinfo=None)
    return (now_naive - ts) <= timedelta(seconds=int(telemetry_max_age_sec))


__all__ = [
    "PH_MIN",
    "PH_MAX",
    "EC_MIN",
    "EC_MAX",
    "sensor_value_in_bounds",
    "sample_in_bounds",
    "is_fresh",
]
