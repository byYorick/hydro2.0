"""PgZoneRuntimeMonitor metric windows: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.domain.services.irrigation_soil_observation import soil_percentage_unit
from ae3lite.domain.services.metric_window_validator import (
    is_stub_telemetry,
    sensor_value_in_bounds,
    usable_decision_quality,
)


@dataclass(frozen=True)
class RuntimeMonitorMetricWindowsPorts:
    age_sec: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    read_metric_sensor: Callable[..., Awaitable[Any]]
    global_get_pool: Callable[..., Any]


class RuntimeMonitorMetricWindows:
    def __init__(self, ports: RuntimeMonitorMetricWindowsPorts) -> None:
        self._ports = ports

    async def read_metric(self, *, zone_id: int, sensor_type: str, telemetry_max_age_sec: int) -> Mapping[str, Any]:
        row = await self._ports.read_metric_sensor(zone_id=zone_id, sensor_type=sensor_type)
        if row is None:
            return {"has_value": False, "is_stale": False, "value": None}

        raw_value = row.get("value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        sample_ts = row.get("sample_ts")
        age_sec = self._ports.age_sec(sample_ts)
        if is_stub_telemetry(quality=row.get("last_quality")):
            return {"has_value": False, "is_stale": True, "value": None}
        is_stale = bool(value is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "value": value,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_value": value is not None,
            "is_stale": is_stale,
        }

    async def read_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit: int = 64,
    ) -> Mapping[str, Any]:
        normalized_since_ts = self._ports.normalize_timestamp(since_ts)
        sensor_row = await self._ports.read_metric_sensor(zone_id=zone_id, sensor_type=sensor_type)
        if sensor_row is None:
            return {
                "has_sensor": False,
                "has_samples": False,
                "is_stale": False,
                "sensor_id": None,
                "sensor_label": None,
                "samples": (),
                "latest_sample_ts": None,
            }
        if is_stub_telemetry(quality=sensor_row.get("last_quality")):
            return {
                "has_sensor": True,
                "has_samples": False,
                "is_stale": True,
                "sensor_id": sensor_row.get("sensor_id"),
                "sensor_label": sensor_row.get("sensor_label"),
                "samples": (),
                "latest_sample_ts": sensor_row.get("sample_ts"),
                "sample_age_sec": self._ports.age_sec(sensor_row.get("sample_ts")),
            }

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ts, value, quality, metadata
                FROM (
                    SELECT ts, value, quality, metadata, id
                    FROM telemetry_samples
                    WHERE sensor_id = $1
                      AND ts >= $2
                      AND COALESCE(quality, 'GOOD') <> 'STUB'
                      AND COALESCE(metadata->>'stub', 'false') NOT IN ('true', '1')
                    ORDER BY ts DESC, id DESC
                    LIMIT $3
                ) recent
                ORDER BY ts ASC, id ASC
                """,
                int(sensor_row["sensor_id"]),
                normalized_since_ts,
                max(1, int(limit)),
            )

        samples: list[dict[str, Any]] = []
        latest_sample_ts: Optional[datetime] = None
        for row in rows:
            raw_value = row.get("value")
            try:
                value = float(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                value = None
            ts = row.get("ts")
            latest_sample_ts = ts if ts is not None else latest_sample_ts
            if is_stub_telemetry(quality=row.get("quality"), metadata=row.get("metadata")):
                continue
            if value is None:
                continue
            samples.append({"ts": ts, "value": value})

        if latest_sample_ts is None:
            latest_sample_ts = sensor_row.get("sample_ts")
        age_sec = self._ports.age_sec(latest_sample_ts)
        is_stale = bool(latest_sample_ts is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        return {
            "has_sensor": True,
            "has_samples": bool(samples),
            "is_stale": is_stale,
            "sensor_id": sensor_row.get("sensor_id"),
            "sensor_label": sensor_row.get("sensor_label"),
            "samples": tuple(samples),
            "latest_sample_ts": latest_sample_ts,
            "sample_age_sec": age_sec,
        }

    async def read_metric_windows(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit_per_sensor: int = 64,
        until_ts: datetime | None = None,
    ) -> Mapping[str, Any]:
        """Bounded, quality-filtered windows in two queries for any sensor count.

        Freshness belongs to the accepted history, not a newer telemetry_last
        timestamp. Two seconds allow timestamp(0) rounding, not arbitrary future data.
        """
        since = self._ports.normalize_timestamp(since_ts)
        moment = _naive_utc(until_ts or datetime.now(timezone.utc))
        upper = moment + timedelta(seconds=2)
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            sensors = await conn.fetch(
                """
                SELECT s.id AS sensor_id, s.label AS sensor_label, s.unit,
                       tl.last_value AS value,
                       COALESCE(tl.last_ts, tl.updated_at) AS sample_ts,
                       tl.last_quality AS last_quality
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1 AND s.is_active = TRUE AND s.type = $2
                ORDER BY s.id ASC
                """,
                zone_id,
                sensor_type,
            )
            usable = {}
            for sensor in sensors:
                stamp = sensor.get("sample_ts")
                usable[int(sensor["sensor_id"])] = (
                    usable_decision_quality(quality=sensor.get("last_quality"))
                    and (sensor_type.upper() != "SOIL_MOISTURE" or soil_percentage_unit(sensor.get("unit")))
                    and (
                        stamp is None
                        or (
                            isinstance(stamp, datetime)
                            and _naive_utc(stamp) <= upper
                            and sensor_value_in_bounds(sensor_type=sensor_type, value=sensor.get("value"))
                        )
                    )
                )
            ids = [sensor_id for sensor_id, valid in usable.items() if valid]
            rows = (
                await conn.fetch(
                    """
                SELECT binding.sensor_id, recent.ts, recent.value, recent.quality, recent.metadata
                FROM unnest($1::bigint[]) AS binding(sensor_id)
                CROSS JOIN LATERAL (
                    SELECT ts, value, quality, metadata, id
                    FROM telemetry_samples
                    WHERE sensor_id = binding.sensor_id
                      AND ts >= $2 AND ts <= $4
                      AND COALESCE(quality, 'GOOD') = 'GOOD'
                      AND COALESCE(metadata->>'stub', 'false') NOT IN ('true', '1')
                    ORDER BY ts DESC, id DESC LIMIT $3
                ) recent
                ORDER BY binding.sensor_id ASC, recent.ts ASC, recent.id ASC
                """,
                    ids,
                    since,
                    max(1, int(limit_per_sensor)),
                    upper,
                )
                if ids
                else []
            )

        grouped = {int(sensor["sensor_id"]): [] for sensor in sensors}
        rejected = {sensor_id: 0 for sensor_id in grouped}
        latest_rejected = {}
        for row in rows:
            sensor_id = int(row["sensor_id"])
            ts = row.get("ts")
            valid = (
                isinstance(ts, datetime)
                and since <= _naive_utc(ts) <= upper
                and usable_decision_quality(quality=row.get("quality"), metadata=row.get("metadata"))
                and sensor_value_in_bounds(sensor_type=sensor_type, value=row.get("value"))
            )
            if not valid:
                rejected[sensor_id] += 1
                if isinstance(ts, datetime):
                    latest_rejected[sensor_id] = _naive_utc(ts)
                continue
            grouped[sensor_id].append({"ts": ts, "value": float(row["value"])})
            if latest_rejected.get(sensor_id) == _naive_utc(ts):
                latest_rejected.pop(sensor_id)

        windows = []
        for sensor in sensors:
            sensor_id = int(sensor["sensor_id"])
            samples = grouped[sensor_id]
            latest = samples[-1]["ts"] if samples else None
            age = (moment - _naive_utc(latest)).total_seconds() if latest else None
            invalid_tail = latest_rejected.get(sensor_id)
            stale = (
                not usable[sensor_id]
                or age is None
                or age < -2
                or age > max(0, int(telemetry_max_age_sec))
                or (invalid_tail is not None and (latest is None or invalid_tail >= _naive_utc(latest)))
            )
            windows.append(
                {
                    "sensor_id": sensor_id,
                    "sensor_label": sensor.get("sensor_label"),
                    "samples": tuple(samples),
                    "latest_sample_ts": latest,
                    "sample_age_sec": age,
                    "is_stale": bool(stale),
                    "rejected_samples": rejected[sensor_id],
                }
            )
        latest = max(
            (_naive_utc(window["latest_sample_ts"]) for window in windows if window["latest_sample_ts"] is not None),
            default=None,
        )
        return {
            "has_sensors": bool(windows),
            "sensor_windows": tuple(windows),
            "latest_sample_ts": latest,
            "sample_age_sec": (moment - latest).total_seconds() if latest else None,
            "is_stale": bool(windows) and any(window["is_stale"] for window in windows),
        }


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
