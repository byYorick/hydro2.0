"""Ряд телеметрии канала по label, без фильтра по sensors.type.

PAR ещё может лежать как OTHER, пока нет отдельного типа. Драйвер датчика
в этот контур не входит.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.db import get_pool


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return _as_utc(moment).replace(tzinfo=None)


async def fetch_channel_samples(
    *,
    zone_id: int,
    label: str,
    since_ts: datetime,
    until_ts: datetime,
) -> dict[str, Any]:
    channel = str(label or "").strip().lower()
    if not channel:
        return {"samples": [], "sensor_id": None}
    pool = await get_pool()
    async with pool.acquire() as conn:
        sensor = await conn.fetchrow(
            """
            SELECT s.id
            FROM sensors s
            WHERE s.zone_id = $1
              AND s.is_active IS TRUE
              AND lower(s.label) = $2
            ORDER BY s.id ASC
            LIMIT 1
            """,
            int(zone_id),
            channel,
        )
        if sensor is None:
            return {"samples": [], "sensor_id": None}
        rows = await conn.fetch(
            """
            SELECT ts, value
            FROM telemetry_samples
            WHERE sensor_id = $1
              AND zone_id = $2
              AND ts >= $3
              AND ts <= $4
              AND COALESCE(quality, 'GOOD') <> 'STUB'
            ORDER BY ts ASC
            LIMIT 20000
            """,
            int(sensor["id"]),
            int(zone_id),
            _naive_utc(since_ts),
            _naive_utc(until_ts),
        )
    samples: list[dict[str, Any]] = []
    for row in rows:
        moment = row["ts"]
        if not isinstance(moment, datetime):
            continue
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        samples.append({"ts": _as_utc(moment), "value": value})
    return {"samples": samples, "sensor_id": int(sensor["id"])}
