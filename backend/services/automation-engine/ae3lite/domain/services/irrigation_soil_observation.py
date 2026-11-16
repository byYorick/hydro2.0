"""Validate and aggregate percentage soil readings before irrigation admission."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean
from typing import Any, Mapping


def soil_percentage(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def soil_percentage_unit(unit: Any) -> bool:
    return str(unit or "pct").strip().lower() in {"pct", "%", "percent"}


@dataclass(frozen=True)
class SoilObservation:
    means: tuple[float, ...]
    samples: int
    sensors: int
    missing_sensors: int
    rejected_samples: int
    stale: bool

    @property
    def available(self) -> bool:
        return bool(self.means) and not self.stale and self.missing_sensors == 0

    def details(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "sensor_count": len(self.means),
            "active_sensor_count": self.sensors,
            "missing_sensor_count": self.missing_sensors,
            "rejected_samples": self.rejected_samples,
        }


def observe_soil_windows(data: Mapping[str, Any]) -> SoilObservation:
    windows = data.get("sensor_windows")
    windows = windows if isinstance(windows, (list, tuple)) else ()
    means: list[float] = []
    count = missing = rejected = 0
    stale = bool(data.get("is_stale"))
    for window in windows:
        if not isinstance(window, Mapping):
            missing += 1
            continue
        stale = stale or bool(window.get("is_stale"))
        samples = window.get("samples")
        samples = samples if isinstance(samples, (list, tuple)) else ()
        values = [soil_percentage(sample.get("value")) if isinstance(sample, Mapping) else None for sample in samples]
        rejected += sum(value is None for value in values) + int(window.get("rejected_samples") or 0)
        valid = [value for value in values if value is not None]
        count += len(valid)
        if valid:
            means.append(float(mean(valid)))
        else:
            missing += 1
    return SoilObservation(tuple(means), count, len(windows), missing, rejected, stale)
