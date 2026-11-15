"""climate tick sensors: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Callable, Mapping


# Температура раствора тоже TEMPERATURE (solution_temp_c) и в воздух не входит.
_INSIDE_AIR_TEMP_LABELS = frozenset({"temperature", "temp_air", "air_temp", "air_temp_c"})


def _is_inside_air_temperature(sensor_type: str, label: str) -> bool:
    return label in _INSIDE_AIR_TEMP_LABELS and sensor_type in {"TEMPERATURE", "TEMP"}


@dataclass(frozen=True)
class ClimateTickSensorsPorts:
    core_outside_weather_keys: Callable[..., Any]
    outside_channel_hints: Callable[..., Any]
    outside_sensor_types: Callable[..., Any]
    accumulate_sensor_row: Callable[..., Any]
    as_float: Callable[..., Any]
    is_truthy_sensor_value: Callable[..., Any]
    load_shared_weather_station_node_id: Callable[..., Any]
    weather_station_fresh: Callable[..., Any]
    fetch: Callable[..., Any]


class ClimateTickSensors:
    def __init__(self, ports: ClimateTickSensorsPorts) -> None:
        self._ports = ports

    def weather_station_fresh(self, outside_fresh: Mapping[str, bool]) -> bool:
        """Core outside weather sensors; rain/light are optional and must not stale the station."""
        return any(bool(outside_fresh.get(key)) for key in self._ports.core_outside_weather_keys())

    async def load_shared_weather_station_node_id(self, greenhouse_id: int) -> int | None:
        rows = await self._ports.fetch(
            """
            SELECT shared_weather_station_node_id
            FROM greenhouses
            WHERE id = $1
            """,
            greenhouse_id,
        )
        if not rows:
            return None
        raw = rows[0].get("shared_weather_station_node_id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def accumulate_sensor_row(
        self,
        row: Mapping[str, Any],
        *,
        freshness_sec: int,
        now: datetime,
        inside_temps: list[float],
        inside_rhs: list[float],
        inside_pressures: list[float],
        outside_fresh: dict[str, bool],
        outdoor_state: dict[str, Any],
        allow_inside: bool,
        allow_outside: bool,
    ) -> bool:
        """Apply one sensor row into aggregators. Returns whether inside climate was marked fresh."""
        scope = str(row.get("scope") or "").lower()
        st = str(row.get("type") or "")
        label = str(row.get("label") or "").strip().lower()
        val = row.get("last_value")
        ts = row.get("last_ts") or row.get("telemetry_updated_at")
        q = str(row.get("last_quality") or "").upper()

        def _fresh(ts_value: Any) -> bool:
            if ts_value is None or not isinstance(ts_value, datetime):
                return False
            if ts_value.tzinfo is None:
                ts_value = ts_value.replace(tzinfo=timezone.utc)
            return (now - ts_value).total_seconds() <= float(freshness_sec)

        fresh = _fresh(ts) and q != "BAD"
        if not fresh:
            return False
        fv = self._ports.as_float(val)
        if fv is None:
            return False

        inside_marked = False
        if allow_inside and scope == "inside" and _is_inside_air_temperature(st, label):
            inside_temps.append(fv)
            inside_marked = True
        elif allow_inside and scope == "inside" and (st == "HUMIDITY" or label in {"humidity", "humidity_air"}):
            inside_rhs.append(fv)
            inside_marked = True
        elif allow_inside and scope == "inside" and (st == "PRESSURE" or label == "pressure"):
            inside_pressures.append(fv)
        elif allow_outside and (
            scope == "outside"
            or st in self._ports.outside_sensor_types()
            or label in self._ports.outside_channel_hints()
            or st in {"WIND_SPEED", "WIND_DIRECTION"}
            or label in {"wind_speed", "wind_direction"}
        ):
            if st in {"TEMPERATURE", "OUTSIDE_TEMP"} or label in {"outside_temp", "outdoor_temp"}:
                outdoor_state["outside_temp"] = fv
                outside_fresh["outside_temp"] = True
            elif st in {"HUMIDITY", "OUTSIDE_HUMIDITY"} or label in {"outside_humidity", "outdoor_humidity"}:
                outdoor_state["outside_humidity"] = fv
                outside_fresh["outside_humidity"] = True
            elif st in {"PRESSURE", "OUTSIDE_PRESSURE"} or label in {"outside_pressure"}:
                outdoor_state["outside_pressure"] = fv
            elif st == "WIND_SPEED" or label == "wind_speed":
                outdoor_state["wind_speed"] = fv
                outside_fresh["wind_speed"] = True
            elif st == "WIND_DIRECTION" or label == "wind_direction":
                outdoor_state["wind_direction_deg"] = fv
            elif st in {"LIGHT_INTENSITY", "OUTSIDE_LIGHT"} or label in {"outside_light", "light"}:
                outdoor_state["outside_light_lux"] = fv
                outside_fresh["outside_light"] = True
            elif st in {"RAIN_DETECTED", "RAIN"} or label in {"rain_detected", "rain"}:
                outdoor_state["rain_detected"] = self._ports.is_truthy_sensor_value(fv)
                outside_fresh["rain_detected"] = True

        return inside_marked

    async def sensor_snapshot(self, greenhouse_id: int, freshness_sec: int) -> dict[str, Any]:
        shared_weather_node_id = await self._ports.load_shared_weather_station_node_id(greenhouse_id)

        # Indoor always from the ticking greenhouse. Outdoor prefers shared site station.
        inside_rows = await self._ports.fetch(
            """
            SELECT s.scope::text AS scope,
                   s.type::text AS type,
                   s.label,
                   tl.last_value,
                   tl.last_ts,
                   tl.updated_at AS telemetry_updated_at,
                   tl.last_quality::text AS last_quality
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.greenhouse_id = $1 AND s.is_active IS TRUE
            """,
            greenhouse_id,
        )

        outside_rows: list[Any] = []
        if shared_weather_node_id is not None:
            outside_rows = await self._ports.fetch(
                """
                SELECT s.scope::text AS scope,
                       s.type::text AS type,
                       s.label,
                       tl.last_value,
                       tl.last_ts,
                       tl.updated_at AS telemetry_updated_at,
                       tl.last_quality::text AS last_quality
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.node_id = $1 AND s.is_active IS TRUE
                """,
                shared_weather_node_id,
            )
        else:
            outside_rows = [
                row
                for row in (inside_rows or [])
                if str(row.get("scope") or "").lower() == "outside"
                or str(row.get("type") or "") in self._ports.outside_sensor_types()
                or str(row.get("label") or "").strip().lower() in self._ports.outside_channel_hints()
            ]

        now = datetime.now(timezone.utc)
        inside_temps: list[float] = []
        inside_rhs: list[float] = []
        inside_pressures: list[float] = []
        outside_fresh: dict[str, bool] = {
            "outside_temp": False,
            "outside_humidity": False,
            "wind_speed": False,
            "rain_detected": False,
            "outside_light": False,
        }
        outdoor_state: dict[str, Any] = {
            "outside_temp": None,
            "outside_humidity": None,
            "outside_pressure": None,
            "wind_speed": None,
            "wind_direction_deg": None,
            "rain_detected": False,
            "outside_light_lux": None,
        }
        inside_fresh = False

        for row in inside_rows or []:
            if self._ports.accumulate_sensor_row(
                row,
                freshness_sec=freshness_sec,
                now=now,
                inside_temps=inside_temps,
                inside_rhs=inside_rhs,
                inside_pressures=inside_pressures,
                outside_fresh=outside_fresh,
                outdoor_state=outdoor_state,
                allow_inside=True,
                allow_outside=shared_weather_node_id is None,
            ):
                inside_fresh = True

        if shared_weather_node_id is not None:
            for row in outside_rows or []:
                self._ports.accumulate_sensor_row(
                    row,
                    freshness_sec=freshness_sec,
                    now=now,
                    inside_temps=inside_temps,
                    inside_rhs=inside_rhs,
                    inside_pressures=inside_pressures,
                    outside_fresh=outside_fresh,
                    outdoor_state=outdoor_state,
                    allow_inside=False,
                    allow_outside=True,
                )

        it_med = float(median(inside_temps)) if inside_temps else None
        it_max = max(inside_temps) if inside_temps else None
        it_min = min(inside_temps) if inside_temps else None
        it_spread = (it_max - it_min) if it_max is not None and it_min is not None else None
        irh_med = float(median(inside_rhs)) if inside_rhs else None
        irh_max = max(inside_rhs) if inside_rhs else None
        irh_min = min(inside_rhs) if inside_rhs else None
        irh_spread = (irh_max - irh_min) if irh_max is not None and irh_min is not None else None
        ip_med = float(median(inside_pressures)) if inside_pressures else None

        return {
            "inside_temp_median": it_med,
            "inside_temp_max": it_max,
            "inside_temp_min": it_min,
            "inside_temp_spread": it_spread,
            "inside_rh_median": irh_med,
            "inside_rh_max": irh_max,
            "inside_rh_min": irh_min,
            "inside_rh_spread": irh_spread,
            "inside_pressure_median": ip_med,
            "outside_temp": outdoor_state["outside_temp"],
            "outside_humidity": outdoor_state["outside_humidity"],
            "outside_pressure": outdoor_state["outside_pressure"],
            "wind_speed": outdoor_state["wind_speed"],
            "wind_direction_deg": outdoor_state["wind_direction_deg"],
            "rain_detected": outdoor_state["rain_detected"],
            "outside_light_lux": outdoor_state["outside_light_lux"],
            "weather_fresh": self._ports.weather_station_fresh(outside_fresh),
            "outside_fresh": outside_fresh,
            "inside_fresh": inside_fresh,
            "shared_weather_station_node_id": shared_weather_node_id,
        }
