"""PgZoneRuntimeMonitor temperature: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from ae3lite.domain.services.metric_window_validator import usable_decision_quality, sensor_value_in_bounds
from ae3lite.domain.services.solution_temp_irrigation_guard import (
    SOLUTION_TEMP_CHANNEL_LABELS,
    DEFAULT_SOLUTION_TEMP_STALE_SEC,
)


@dataclass(frozen=True)
class RuntimeMonitorTemperaturePorts:
    normalize_labels: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class RuntimeMonitorTemperature:
    def __init__(self, ports: RuntimeMonitorTemperaturePorts) -> None:
        self._ports = ports

    async def read_solution_temp_window(
        self,
        *,
        zone_id: int,
        since_ts: datetime,
        until_ts: datetime,
        limit: int = 5000,
    ) -> Mapping[str, Any]:
        """Ряд ``telemetry_samples`` канала solution_temp_c за окно hold.

        ``telemetry_last`` возвращается отдельно и в ряд не подмешивается:
        одна последняя точка hold не доказывает.
        """
        labels = self._ports.normalize_labels(SOLUTION_TEMP_CHANNEL_LABELS)
        since = self._ports.normalize_timestamp(since_ts)
        until = self._ports.normalize_timestamp(until_ts)
        empty: dict[str, Any] = {
            "has_sensor": False,
            "sensor_id": None,
            "sensor_label": None,
            "telemetry_last": None,
            "samples": (),
        }
        if since is None or until is None or until < since:
            return empty

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            sensor_row = await conn.fetchrow(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    tl.last_value AS value,
                    COALESCE(tl.last_ts, tl.updated_at) AS sample_ts,
                    tl.last_quality AS last_quality
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND UPPER(COALESCE(s.type, '')) = 'TEMPERATURE'
                  AND LOWER(TRIM(COALESCE(s.label, ''))) = ANY($2::text[])
                ORDER BY COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST, s.id DESC
                LIMIT 1
                """,
                zone_id,
                labels,
            )
            if sensor_row is None:
                return empty

            telemetry_last = None
            if usable_decision_quality(quality=sensor_row.get("last_quality")):
                try:
                    last_value = float(sensor_row.get("value")) if sensor_row.get("value") is not None else None
                except (TypeError, ValueError):
                    last_value = None
                last_ts = sensor_row.get("sample_ts")
                if (
                    last_value is not None
                    and sensor_value_in_bounds(sensor_type="TEMPERATURE", value=last_value)
                    and isinstance(last_ts, datetime)
                ):
                    telemetry_last = {"ts": last_ts, "value": last_value}

            rows = await conn.fetch(
                """
                SELECT ts, value, quality, metadata FROM (
                    (SELECT ts, value, quality, metadata, id
                     FROM telemetry_samples
                     WHERE sensor_id=$1 AND ts < $2
                       AND ts >= $2 - $5::interval
                       AND COALESCE(quality, 'GOOD') = 'GOOD'
                       AND COALESCE(metadata->>'stub', 'false') NOT IN ('true', '1')
                     ORDER BY ts DESC, id DESC LIMIT 1)
                    UNION ALL
                    (SELECT ts, value, quality, metadata, id
                     FROM telemetry_samples
                     WHERE sensor_id=$1 AND ts >= $2 AND ts <= $3
                     ORDER BY ts DESC, id DESC LIMIT ($4 + 1))
                ) observed ORDER BY ts ASC, id ASC
                """,
                int(sensor_row["sensor_id"]),
                since,
                until,
                max(1, int(limit)),
                timedelta(seconds=DEFAULT_SOLUTION_TEMP_STALE_SEC),
            )

        samples: list[dict[str, Any]] = []
        invalid_samples = 0
        window_count = sum(1 for row in rows if isinstance(row.get("ts"), datetime) and row["ts"] >= since)
        for row in rows:
            if not usable_decision_quality(quality=row.get("quality"), metadata=row.get("metadata")):
                invalid_samples += 1
                continue
            try:
                value = float(row.get("value")) if row.get("value") is not None else None
            except (TypeError, ValueError):
                value = None
            ts = row.get("ts")
            if (
                value is None
                or not sensor_value_in_bounds(sensor_type="TEMPERATURE", value=value)
                or not isinstance(ts, datetime)
            ):
                invalid_samples += 1
                continue
            samples.append({"ts": ts, "value": value})

        return {
            "has_sensor": True,
            "sensor_id": sensor_row.get("sensor_id"),
            "sensor_label": sensor_row.get("sensor_label"),
            "telemetry_last": telemetry_last,
            "samples": tuple(samples),
            "invalid_samples": invalid_samples,
            "history_truncated": window_count > max(1, int(limit)),
        }
