"""Метрики tick форточек теплицы (один tick на greenhouse)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

GREENHOUSE_CLIMATE_TICK_TOTAL = Counter(
    "greenhouse_climate_tick_total",
    "Тики климата теплицы по терминальному статусу",
    ["status"],
)

GREENHOUSE_CLIMATE_COMMAND_TOTAL = Counter(
    "greenhouse_climate_command_total",
    "Команды форточек по стороне и статусу",
    ["side", "status"],
)

GREENHOUSE_CLIMATE_DECISION_DURATION_SECONDS = Histogram(
    "greenhouse_climate_decision_duration_seconds",
    "Длительность одного tick климата теплицы",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

GREENHOUSE_CLIMATE_SENSOR_STALE_TOTAL = Counter(
    "greenhouse_climate_sensor_stale_total",
    "Протухшие датчики климата теплицы",
    ["kind"],
)

GREENHOUSE_CLIMATE_WIND_CLAMP_TOTAL = Counter(
    "greenhouse_climate_wind_clamp_total",
    "Решения с ограничением по ветру",
)

GREENHOUSE_CLIMATE_RAIN_CLAMP_TOTAL = Counter(
    "greenhouse_climate_rain_clamp_total",
    "Решения с ограничением по дождю",
)

GREENHOUSE_CLIMATE_COMMAND_FAILED_TOTAL = Counter(
    "greenhouse_climate_command_failed_total",
    "Сбои команд форточек",
    ["side", "failure"],
)

__all__ = [
    "GREENHOUSE_CLIMATE_TICK_TOTAL",
    "GREENHOUSE_CLIMATE_COMMAND_TOTAL",
    "GREENHOUSE_CLIMATE_DECISION_DURATION_SECONDS",
    "GREENHOUSE_CLIMATE_SENSOR_STALE_TOTAL",
    "GREENHOUSE_CLIMATE_WIND_CLAMP_TOTAL",
    "GREENHOUSE_CLIMATE_RAIN_CLAMP_TOTAL",
    "GREENHOUSE_CLIMATE_COMMAND_FAILED_TOTAL",
]
