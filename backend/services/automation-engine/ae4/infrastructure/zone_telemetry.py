"""Свежие пробы зоны для тика AE4. Синонимы каналов не читаются (§1.1.7 / §2.10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ae4.domain.drain_policy import (
    CONTRACT_DRAIN_TANK_EC_CHANNEL,
    CONTRACT_DRAIN_TANK_LEVEL_CHANNELS,
)
from ae4.domain.planting import TelemetrySample
from common.db import fetch

# Каналы §1.1.7 + бак стока §2.10 — без синонимов.
_LEVEL_CHANNELS = frozenset(
    {
        "level_solution_min",
        "level_solution_max",
        "level_clean_min",
        "level_clean_max",
    }
) | frozenset(CONTRACT_DRAIN_TANK_LEVEL_CHANNELS)
_EC_FEED_CHANNELS = frozenset({"ec_sensor"})
_EC_DRAIN_CHANNELS = frozenset(
    {CONTRACT_DRAIN_TANK_EC_CHANNEL} if CONTRACT_DRAIN_TANK_EC_CHANNEL else set()
)
_PH_CHANNELS = frozenset({"ph_sensor"})
_SOIL_CHANNELS = frozenset({"soil_moisture"})
_AIR_TEMP_CHANNELS = frozenset({"temperature", "air_temp_c"})
_AIR_HUM_CHANNELS = frozenset({"humidity", "air_rh"})
_SOLUTION_TEMP_CHANNELS = frozenset({"solution_temp_c"})
_ZONE_LIGHT_CHANNELS = frozenset({"light", "light_level"})
_OUTSIDE_LIGHT_CHANNELS = frozenset({"outside_light"})


@dataclass(frozen=True)
class LevelReading:
    """Сырая проба уровня: value 0/1, свежесть отдельно."""

    channel: str
    value: int | None
    ts: datetime | None
    bound: bool
    fresh: bool


@dataclass(frozen=True)
class ZoneTelemetrySnapshot:
    level_solution_min: LevelReading
    level_solution_max: LevelReading
    level_clean_min: LevelReading
    level_clean_max: LevelReading
    level_drain_min: LevelReading
    level_drain_max: LevelReading
    ec_feed: TelemetrySample | None
    ec_drain: TelemetrySample | None
    ph_feed: TelemetrySample | None
    soil_moisture: TelemetrySample | None
    temp_air: TelemetrySample | None
    humidity_air: TelemetrySample | None
    solution_temp: TelemetrySample | None
    light_samples: tuple[TelemetrySample, ...]


def _as_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0) if value.microsecond else value


def _is_fresh(
    *,
    ts: datetime | None,
    now: datetime,
    telemetry_max_age_sec: int,
) -> bool:
    if ts is None:
        return False
    age = _as_utc_naive(now) - _as_utc_naive(ts)
    if age is None:
        return False
    return age <= timedelta(seconds=int(telemetry_max_age_sec))


def _channel_from_sensor(*, label: str, specs: object) -> str:
    label_s = str(label or "").strip()
    if isinstance(specs, dict):
        channel = str(specs.get("channel") or "").strip()
        if channel:
            return channel
    return label_s


def _unbound_level(channel: str) -> LevelReading:
    return LevelReading(channel=channel, value=None, ts=None, bound=False, fresh=False)


async def load_zone_telemetry(
    *,
    zone_id: int,
    now: datetime,
    telemetry_max_age_sec: int,
) -> ZoneTelemetrySnapshot:
    """Читает telemetry_last по точным каналам §1.1.7 / §2.10."""
    rows = await fetch(
        """
        SELECT
            s.type AS sensor_type,
            s.label AS label,
            s.unit AS unit,
            s.specs AS specs,
            tl.last_value AS last_value,
            tl.last_ts AS last_ts
        FROM sensors AS s
        LEFT JOIN telemetry_last AS tl ON tl.sensor_id = s.id
        WHERE s.zone_id = $1
          AND s.is_active = TRUE
        """,
        zone_id,
    )
    levels: dict[str, LevelReading] = {
        name: _unbound_level(name) for name in _LEVEL_CHANNELS
    }
    ec_feed: TelemetrySample | None = None
    ec_drain: TelemetrySample | None = None
    ph_feed: TelemetrySample | None = None
    soil: TelemetrySample | None = None
    temp_air: TelemetrySample | None = None
    humidity_air: TelemetrySample | None = None
    solution_temp: TelemetrySample | None = None
    lights: list[TelemetrySample] = []

    for row in rows:
        channel = _channel_from_sensor(label=str(row.get("label") or ""), specs=row.get("specs"))
        sensor_type = str(row.get("sensor_type") or "").strip().upper()
        ts = _as_utc_naive(row.get("last_ts"))
        raw_value = row.get("last_value")
        unit = str(row.get("unit") or "").strip() or None

        if channel in _LEVEL_CHANNELS and sensor_type in {
            "WATER_LEVEL_SWITCH",
            "WATER_LEVEL",
        }:
            bound = True
            value: int | None = None
            if raw_value is not None:
                try:
                    number = float(raw_value)
                except (TypeError, ValueError):
                    number = None
                if number is not None and 0.0 <= number <= 1.0:
                    value = 1 if number >= 1.0 else 0
            fresh = _is_fresh(
                ts=ts, now=now, telemetry_max_age_sec=telemetry_max_age_sec
            )
            levels[channel] = LevelReading(
                channel=channel,
                value=value,
                ts=ts,
                bound=bound,
                fresh=fresh and value is not None,
            )
            continue

        if channel in _EC_FEED_CHANNELS and sensor_type == "EC" and raw_value is not None and ts:
            try:
                ec_feed = TelemetrySample(
                    metric_type="EC",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if channel in _EC_DRAIN_CHANNELS and sensor_type == "EC" and raw_value is not None and ts:
            try:
                ec_drain = TelemetrySample(
                    metric_type="EC",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if channel in _PH_CHANNELS and sensor_type == "PH" and raw_value is not None and ts:
            try:
                ph_feed = TelemetrySample(
                    metric_type="PH",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if channel in _SOIL_CHANNELS and sensor_type == "SOIL_MOISTURE" and raw_value is not None and ts:
            try:
                soil = TelemetrySample(
                    metric_type="SOIL_MOISTURE",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if channel in _AIR_TEMP_CHANNELS and sensor_type == "TEMPERATURE" and raw_value is not None and ts:
            try:
                temp_air = TelemetrySample(
                    metric_type="TEMPERATURE",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if (
            channel in _SOLUTION_TEMP_CHANNELS
            and sensor_type == "TEMPERATURE"
            and raw_value is not None
            and ts
        ):
            try:
                solution_temp = TelemetrySample(
                    metric_type="TEMPERATURE",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if channel in _AIR_HUM_CHANNELS and sensor_type == "HUMIDITY" and raw_value is not None and ts:
            try:
                humidity_air = TelemetrySample(
                    metric_type="HUMIDITY",
                    channel=channel,
                    value=float(raw_value),
                    ts=ts,
                    unit=unit,
                )
            except (TypeError, ValueError):
                pass
            continue

        if (
            channel in _ZONE_LIGHT_CHANNELS or channel in _OUTSIDE_LIGHT_CHANNELS
        ) and raw_value is not None and ts:
            metric = (
                "OUTSIDE_LIGHT"
                if channel in _OUTSIDE_LIGHT_CHANNELS
                else "LIGHT_INTENSITY"
            )
            try:
                lights.append(
                    TelemetrySample(
                        metric_type=metric,
                        channel=channel,
                        value=float(raw_value),
                        ts=ts,
                        unit=unit,
                    )
                )
            except (TypeError, ValueError):
                pass

    return ZoneTelemetrySnapshot(
        level_solution_min=levels["level_solution_min"],
        level_solution_max=levels["level_solution_max"],
        level_clean_min=levels["level_clean_min"],
        level_clean_max=levels["level_clean_max"],
        level_drain_min=levels.get(
            "level_drain_min", _unbound_level("level_drain_min")
        ),
        level_drain_max=levels.get(
            "level_drain_max", _unbound_level("level_drain_max")
        ),
        ec_feed=ec_feed,
        ec_drain=ec_drain,
        ph_feed=ph_feed,
        soil_moisture=soil,
        temp_air=temp_air,
        humidity_air=humidity_air,
        solution_temp=solution_temp,
        light_samples=tuple(lights),
    )


def tank_empty(*, reading: LevelReading) -> bool:
    """Пустой бак — свежий level_*_min = 0. Протухший/непривязанный не считается пустым."""
    return bool(reading.bound and reading.fresh and reading.value == 0)


def tank_not_empty(*, reading: LevelReading) -> bool:
    """Не пуст — свежий min = 1."""
    return bool(reading.bound and reading.fresh and reading.value == 1)


def tank_full(*, reading: LevelReading) -> bool:
    """Полон — свежий level_*_max = 1."""
    return bool(reading.bound and reading.fresh and reading.value == 1)


def level_stale_or_unbound(*, reading: LevelReading) -> bool:
    return (not reading.bound) or (not reading.fresh)


__all__ = [
    "LevelReading",
    "ZoneTelemetrySnapshot",
    "load_zone_telemetry",
    "tank_empty",
    "tank_not_empty",
    "tank_full",
    "level_stale_or_unbound",
]
