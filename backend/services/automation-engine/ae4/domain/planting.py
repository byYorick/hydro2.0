"""Состояние посадки. Имён стадий бака здесь нет."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

Outcome = str

# Первое имя в списке важнее при одной и той же тяжести.
NEED_ORDER = (
    "water",
    "nutrition",
    "acidity",
    "leaf_climate",
    "moisture_unseen",
    "root_oxygen",
)
_SEVERITY = ("below", "unseen", "above")


@dataclass(frozen=True)
class TelemetrySample:
    metric_type: str
    channel: str
    value: float
    ts: datetime
    unit: str | None = None


@dataclass(frozen=True)
class ShotMark:
    at: datetime
    kind: str
    phase_id: int
    duration_sec: int


@dataclass(frozen=True)
class PhaseTargets:
    phase_id: int
    started_at: datetime
    interval_sec: int | None = None
    duration_sec: int | None = None
    soil_moisture_min: float | None = None
    soil_moisture_max: float | None = None
    soil_moisture_unit: str | None = None
    vpd_min: float | None = None
    vpd_max: float | None = None
    light_integral_per_shot: float | None = None
    light_integral_unit: str | None = None
    ec_target: float | None = None
    ec_min: float | None = None
    ec_max: float | None = None
    ec_unit: str | None = None
    ph_target: float | None = None
    ph_min: float | None = None
    ph_max: float | None = None
    temp_air_target: float | None = None
    humidity_target: float | None = None
    solution_temp_min: float | None = None
    solution_temp_max: float | None = None
    on_time: str | None = None
    off_time: str | None = None
    lighting_start_time: str | None = None
    lighting_photoperiod_hours: float | None = None


@dataclass(frozen=True)
class PlantingState:
    zone_id: int
    grow_cycle_id: int
    phase: PhaseTargets


def planting_public_keys(state: PlantingState) -> set[str]:
    """Имена полей посадки. Стадий бака среди них нет."""
    keys = {"zone_id", "grow_cycle_id"}
    keys.update(state.phase.__dataclass_fields__.keys())
    return keys


def worst_need(outcomes: Mapping[str, str | None]) -> str | None:
    """Одна функция ограничителя: худшая потребность текущего решения."""
    present = {
        name: outcome
        for name, outcome in outcomes.items()
        if name in NEED_ORDER and outcome is not None
    }
    for severity in _SEVERITY:
        for name in NEED_ORDER:
            if present.get(name) == severity:
                return name
    return None


__all__ = [
    "NEED_ORDER",
    "Outcome",
    "PhaseTargets",
    "PlantingState",
    "ShotMark",
    "TelemetrySample",
    "planting_public_keys",
    "worst_need",
]
