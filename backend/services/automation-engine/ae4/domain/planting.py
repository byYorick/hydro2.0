"""Состояние посадки. Имён стадий бака здесь нет."""

from __future__ import annotations

from dataclasses import dataclass, replace
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

# Имена стадий бака запрещены в публичных ключах состояния посадки.
_FORBIDDEN_PUBLIC_SUBSTRINGS = (
    "two_tank",
    "tank_filling",
    "tank_recirc",
    "irrigating",
)

# Каналы §1.1.7. TEMPERATURE без одного из этих каналов не читается.
_AIR_TEMP_CHANNELS = frozenset({"temperature", "air_temp_c"})
_AIR_HUM_CHANNELS = frozenset({"humidity", "air_rh"})
_SOLUTION_TEMP_CHANNELS = frozenset({"solution_temp_c"})


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
    volume_ml: float | None = None
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
    co2_target: float | None = None
    mist_interval_sec: int | None = None
    mist_duration_sec: int | None = None
    mist_mode: str | None = None
    on_time: str | None = None
    off_time: str | None = None
    lighting_start_time: str | None = None
    lighting_photoperiod_hours: float | None = None


@dataclass(frozen=True)
class PlantingState:
    zone_id: int
    grow_cycle_id: int
    phase: PhaseTargets


@dataclass(frozen=True)
class LightIntegralCursor:
    """Курсор интеграла: сумма только от проб новее last_accounted_ts."""

    accumulated: float
    last_accounted_ts: datetime | None
    unit: str | None
    status: str  # ok | unseen
    last_value: float | None = None


def planting_public_keys(state: PlantingState) -> set[str]:
    """Имена полей посадки. Стадий бака среди них нет."""
    keys = {"zone_id", "grow_cycle_id"}
    keys.update(state.phase.__dataclass_fields__.keys())
    for key in keys:
        lowered = key.lower()
        for forbidden in _FORBIDDEN_PUBLIC_SUBSTRINGS:
            if forbidden in lowered:
                raise ValueError(f"публичный ключ посадки содержит имя стадии бака: {key}")
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


def apply_phase_change(
    *,
    state: PlantingState,
    new_phase: PhaseTargets,
    integral: LightIntegralCursor,
) -> tuple[PlantingState, LightIntegralCursor]:
    """Смена фазы: цели новой фазы, интеграл прошлой не переносится."""
    reset = LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=new_phase.started_at,
        unit=new_phase.light_integral_unit,
        status="ok",
        last_value=None,
    )
    return replace(state, phase=new_phase), reset


def observe_leaf_climate(
    *,
    phase: PhaseTargets,
    temp_air: TelemetrySample | None,
    humidity_air: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> str | None:
    """Климат листа как наблюдение: воздух против целей фазы, без команд."""
    has_temp_norm = phase.temp_air_target is not None
    has_hum_norm = phase.humidity_target is not None
    if not has_temp_norm and not has_hum_norm:
        return None

    # Чужой канал (в т.ч. solution_temp_c) или TEMPERATURE без канала воздуха — unseen.
    if has_temp_norm and not (
        _is_air_temp(temp_air)
        and _sample_fresh(sample=temp_air, now=now, telemetry_max_age_sec=telemetry_max_age_sec)
    ):
        return "unseen"
    if has_hum_norm and not (
        _is_air_humidity(humidity_air)
        and _sample_fresh(
            sample=humidity_air, now=now, telemetry_max_age_sec=telemetry_max_age_sec
        )
    ):
        return "unseen"

    if has_temp_norm and temp_air is not None and phase.temp_air_target is not None:
        if temp_air.value < phase.temp_air_target:
            return "below"
        if temp_air.value > phase.temp_air_target:
            return "above"
    if has_hum_norm and humidity_air is not None and phase.humidity_target is not None:
        if humidity_air.value < phase.humidity_target:
            return "below"
        if humidity_air.value > phase.humidity_target:
            return "above"
    return None


def observe_root_oxygen(
    *,
    phase: PhaseTargets,
    solution_temp: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> str | None:
    """Кислород корня: solution_temp_c против solution_temp_min/max."""
    has_min = phase.solution_temp_min is not None
    has_max = phase.solution_temp_max is not None
    if not has_min and not has_max:
        return None
    if not (
        _is_solution_temp(solution_temp)
        and _sample_fresh(
            sample=solution_temp, now=now, telemetry_max_age_sec=telemetry_max_age_sec
        )
    ):
        return "unseen"
    assert solution_temp is not None
    if (
        has_min
        and phase.solution_temp_min is not None
        and solution_temp.value < phase.solution_temp_min
    ):
        return "below"
    if (
        has_max
        and phase.solution_temp_max is not None
        and solution_temp.value > phase.solution_temp_max
    ):
        return "above"
    return None


def _is_air_temp(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "TEMPERATURE":
        return False
    return bool(sample.channel) and sample.channel in _AIR_TEMP_CHANNELS


def _is_air_humidity(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "HUMIDITY":
        return False
    return bool(sample.channel) and sample.channel in _AIR_HUM_CHANNELS


def _is_solution_temp(sample: TelemetrySample | None) -> bool:
    if sample is None or sample.metric_type != "TEMPERATURE":
        return False
    return bool(sample.channel) and sample.channel in _SOLUTION_TEMP_CHANNELS


def _sample_fresh(
    *,
    sample: TelemetrySample | None,
    now: datetime,
    telemetry_max_age_sec: int | None,
) -> bool:
    # Нет telemetry_max_age_sec в плане — датчик протух (§1.1.3).
    if sample is None or telemetry_max_age_sec is None or telemetry_max_age_sec <= 0:
        return False
    age = (now - sample.ts).total_seconds()
    return age <= telemetry_max_age_sec


__all__ = [
    "NEED_ORDER",
    "Outcome",
    "PhaseTargets",
    "PlantingState",
    "ShotMark",
    "TelemetrySample",
    "LightIntegralCursor",
    "planting_public_keys",
    "worst_need",
    "apply_phase_change",
    "observe_leaf_climate",
    "observe_root_oxygen",
]
