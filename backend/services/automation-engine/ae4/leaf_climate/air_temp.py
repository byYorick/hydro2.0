"""Свежесть температуры воздуха для форточек (§1.1.7).

solution_temp_c сюда не подставляется. Своё число секунд не вводится.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Sequence

from ae4.domain.planting import TelemetrySample
from ae4.domain.sensor_gate import is_fresh

_AIR_TEMP_CHANNELS = frozenset({"temperature", "air_temp_c"})


def is_air_temp_sample(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "TEMPERATURE":
        return False
    return bool(sample.channel) and sample.channel in _AIR_TEMP_CHANNELS


def has_fresh_air_temperature(
    *,
    samples: Sequence[TelemetrySample],
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> bool:
    """Нет telemetry_max_age_sec или нет свежей пробы воздуха — False (E211)."""
    if telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return False
    for sample in samples:
        if not is_air_temp_sample(sample):
            continue
        if is_fresh(
            sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec
        ):
            return True
    return False


def fresh_air_temp_stats(
    *,
    samples: Sequence[TelemetrySample],
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> tuple[float | None, float | None]:
    """(median, max) свежих проб воздуха. solution_temp_c не входит."""
    values: list[float] = []
    if telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return None, None
    for sample in samples:
        if not is_air_temp_sample(sample):
            continue
        if not is_fresh(
            sample=sample, now=now, telemetry_max_age_sec=telemetry_max_age_sec
        ):
            continue
        values.append(float(sample.value))
    if not values:
        return None, None
    return float(median(values)), float(max(values))


__all__ = [
    "fresh_air_temp_stats",
    "has_fresh_air_temperature",
    "is_air_temp_sample",
]
