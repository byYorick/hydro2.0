"""Ряд PPFD зоны для потолка DLI. Читает PostgreSQL, в Laravel по HTTP не ходит."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import asyncpg

from ae3lite.domain.services.dli_integral import (
    configured_channel_unit,
    explicit_light_channel,
    positive_dli_target,
    select_light_channel_row,
    zone_timezone,
)


async def load_dli_light_series(
    conn: asyncpg.Connection,
    *,
    zone_id: int,
    targets: Mapping[str, Any],
    greenhouse_timezone: str | None,
) -> dict[str, Any] | None:
    lighting = targets.get("lighting") if isinstance(targets.get("lighting"), Mapping) else {}
    if positive_dli_target(lighting.get("dli_target") if isinstance(lighting, Mapping) else None) is None:
        return None

    tz_name = greenhouse_timezone if isinstance(greenhouse_timezone, str) and greenhouse_timezone.strip() else None
    if tz_name is None and isinstance(targets.get("greenhouse_timezone"), str):
        tz_name = str(targets.get("greenhouse_timezone")).strip() or None
    tz = zone_timezone(tz_name)
    now = datetime.now(timezone.utc)
    local = now.astimezone(tz)
    window_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    rows = await conn.fetch(
        """
        SELECT
            nc.id,
            LOWER(COALESCE(nc.channel, '')) AS channel,
            nc.unit,
            nc.config,
            UPPER(COALESCE(nc.metric, '')) AS metric,
            LOWER(COALESCE(s.scope, '')) AS scope,
            s.id AS sensor_id
        FROM nodes n
        JOIN node_channels nc
            ON nc.node_id = n.id
        LEFT JOIN sensors s
            ON s.node_id = n.id
           AND s.zone_id = n.zone_id
           AND s.is_active IS TRUE
           AND s.label = nc.channel
        WHERE n.zone_id = $1
          AND COALESCE(nc.is_active, TRUE) = TRUE
          AND UPPER(TRIM(COALESCE(nc.type, ''))) = 'SENSOR'
        ORDER BY nc.id ASC
        """,
        zone_id,
    )
    chosen = select_light_channel_row(
        rows,
        explicit_channel=explicit_light_channel(lighting if isinstance(lighting, Mapping) else None),
    )
    unit = ""
    sensor_id = None
    if chosen is not None:
        unit = configured_channel_unit(chosen.get("unit"), chosen.get("config"))
        raw_sensor = chosen.get("sensor_id")
        try:
            sensor_id = int(raw_sensor) if raw_sensor is not None else None
        except (TypeError, ValueError):
            sensor_id = None

    samples: list[dict[str, Any]] = []
    if sensor_id is not None and unit in {"ppfd", "umol_m2_s"}:
        sample_rows = await conn.fetch(
            """
            SELECT ts, value
            FROM telemetry_samples
            WHERE sensor_id = $1
              AND zone_id = $2
              AND ts >= $3
              AND ts <= $4
            ORDER BY ts ASC
            """,
            sensor_id,
            zone_id,
            window_start.replace(tzinfo=None),
            now.replace(tzinfo=None),
        )
        samples = [_sample_point(row) for row in sample_rows]

    return {
        "unit": unit,
        "samples": samples,
        "timezone": tz_name or "UTC",
        "window_start": window_start.isoformat(),
        "as_of": now.isoformat(),
    }


def _sample_point(row: Mapping[str, Any] | asyncpg.Record) -> dict[str, Any]:
    moment = row["ts"] if isinstance(row, Mapping) else row["ts"]
    if isinstance(moment, datetime):
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        else:
            moment = moment.astimezone(timezone.utc)
        ts_text = moment.isoformat()
    else:
        ts_text = str(moment)
    return {"ts": ts_text, "value": float(row["value"])}


__all__ = ["load_dli_light_series"]
