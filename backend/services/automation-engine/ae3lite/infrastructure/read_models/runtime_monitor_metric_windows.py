"""PgZoneRuntimeMonitor metric windows: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.domain.services.metric_window_validator import is_stub_telemetry


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
    ) -> Mapping[str, Any]:
        normalized_since_ts = self._ports.normalize_timestamp(since_ts)
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            sensor_rows = await conn.fetch(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    COALESCE(tl.last_ts, tl.updated_at) AS sample_ts,
                    tl.last_quality AS last_quality
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type = $2
                ORDER BY s.id ASC
                """,
                zone_id,
                sensor_type,
            )

            sensor_windows: list[dict[str, Any]] = []
            latest_sample_ts: Optional[datetime] = None
            for sensor_row in sensor_rows:
                if is_stub_telemetry(quality=sensor_row.get("last_quality")):
                    sensor_windows.append(
                        {
                            "sensor_id": sensor_row.get("sensor_id"),
                            "sensor_label": sensor_row.get("sensor_label"),
                            "samples": (),
                            "latest_sample_ts": sensor_row.get("sample_ts"),
                            "sample_age_sec": self._ports.age_sec(sensor_row.get("sample_ts")),
                            "is_stale": True,
                        }
                    )
                    continue
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
                    max(1, int(limit_per_sensor)),
                )
                samples: list[dict[str, Any]] = []
                sensor_latest_ts = sensor_row.get("sample_ts")
                for row in rows:
                    if is_stub_telemetry(quality=row.get("quality"), metadata=row.get("metadata")):
                        continue
                    raw_value = row.get("value")
                    try:
                        value = float(raw_value) if raw_value is not None else None
                    except (TypeError, ValueError):
                        value = None
                    ts = row.get("ts")
                    if ts is not None:
                        sensor_latest_ts = ts
                    if value is None:
                        continue
                    samples.append({"ts": ts, "value": value})

                if sensor_latest_ts is not None and (latest_sample_ts is None or sensor_latest_ts > latest_sample_ts):
                    latest_sample_ts = sensor_latest_ts

                sensor_age_sec = self._ports.age_sec(sensor_latest_ts)
                sensor_windows.append(
                    {
                        "sensor_id": sensor_row.get("sensor_id"),
                        "sensor_label": sensor_row.get("sensor_label"),
                        "samples": tuple(samples),
                        "latest_sample_ts": sensor_latest_ts,
                        "sample_age_sec": sensor_age_sec,
                        "is_stale": bool(
                            sensor_latest_ts is not None
                            and ((sensor_age_sec or 0.0) > max(0, int(telemetry_max_age_sec)))
                        ),
                    }
                )

        age_sec = self._ports.age_sec(latest_sample_ts)
        return {
            "has_sensors": bool(sensor_windows),
            "sensor_windows": tuple(sensor_windows),
            "latest_sample_ts": latest_sample_ts,
            "sample_age_sec": age_sec,
            "is_stale": bool(latest_sample_ts is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec)))),
        }
