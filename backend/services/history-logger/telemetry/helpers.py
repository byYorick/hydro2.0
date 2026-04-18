"""Pure helpers для telemetry pipeline: normalisation, keys, FK detection.

Все функции — без зависимостей от module-state в ``telemetry_processing``.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

from common.db import fetch
from common.utils.time import utcnow

# «Шумные» infra-коды: в dev/e2e (APP_ENV=local|testing) увеличиваем интервал,
# либо задаётся TELEMETRY_INFRA_ANOMALY_THROTTLE_SEC (секунды).
INFRA_TELEMETRY_LONG_THROTTLE_CODES = frozenset(
    {
        "infra_telemetry_node_not_found",
        "infra_telemetry_sample_dropped_node_not_found",
        "infra_telemetry_invalid_timestamp",
    }
)


def effective_anomaly_throttle_sec(code: str) -> float:
    base = float(os.getenv("TELEMETRY_ANOMALY_ALERT_THROTTLE_SEC", "300"))
    if code not in INFRA_TELEMETRY_LONG_THROTTLE_CODES:
        return base
    override = float(os.getenv("TELEMETRY_INFRA_ANOMALY_THROTTLE_SEC", "0") or 0)
    if override > 0:
        return override
    app_env = (os.getenv("APP_ENV", "") or "").strip().lower()
    if app_env in ("testing", "local"):
        return max(base, 86400.0)
    return base


def is_sensor_fk_error(error: Exception) -> bool:
    message = str(error)
    return (
        "telemetry_last_sensor_id_foreign" in message
        or "telemetry_samples_sensor_id_foreign" in message
        or "sensors_greenhouse_id_foreign" in message
        or "sensors_zone_id_foreign" in message
        or "sensors_node_id_foreign" in message
        or ("foreign key" in message and "sensors" in message and "sensor_id" in message)
        or ('foreign key' in message and 'table "sensors"' in message)
    )


async def filter_existing_sensor_ids(sensor_ids: list[int]) -> set[int]:
    if not sensor_ids:
        return set()
    rows = await fetch(
        """
        SELECT id
        FROM sensors
        WHERE id = ANY($1::bigint[])
        """,
        sensor_ids,
    )
    return {int(row["id"]) for row in rows if row.get("id") is not None}


def normalize_metric_type(metric_type: str) -> str:
    return (metric_type or "").strip().upper()


def infer_sensor_type(metric_type: str) -> str:
    normalized = normalize_metric_type(metric_type)
    # Дискретные датчики уровня приводим к каноническому типу WATER_LEVEL.
    if normalized == "WATER_LEVEL_SWITCH":
        return "WATER_LEVEL"
    valid_types = {
        "PH",
        "EC",
        "TEMPERATURE",
        "HUMIDITY",
        "CO2",
        "LIGHT_INTENSITY",
        "WATER_LEVEL",
        "FLOW_RATE",
        "PUMP_CURRENT",
        "SOIL_MOISTURE",
        "SOIL_TEMP",
        "PRESSURE",
        "WIND_SPEED",
        "OUTSIDE_TEMP",
        "WIND_DIRECTION",
        "OTHER",
    }
    if normalized in valid_types:
        return normalized
    return "OTHER"


def build_sensor_label(metric_type: str, channel: Optional[str], sensor_type: str) -> str:
    if channel:
        return channel
    if metric_type:
        return metric_type
    return sensor_type


def normalize_ts_for_db(sample_ts: Optional[datetime]) -> datetime:
    ts_value = sample_ts or utcnow()
    if getattr(ts_value, "tzinfo", None):
        return ts_value.astimezone(timezone.utc).replace(tzinfo=None)
    return ts_value.replace(tzinfo=None)


def to_timestamp_ms(timestamp: Optional[datetime]) -> int:
    if timestamp is None:
        return int(time.time() * 1000)
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp_utc = timestamp
        return int(timestamp_utc.timestamp() * 1000)
    return int(timestamp * 1000)


def build_realtime_key(
    sensor_id: Optional[int],
    zone_id: int,
    node_id: Optional[int],
    metric_type: str,
    channel: Optional[str],
) -> tuple:
    if sensor_id is not None:
        return ("sensor", sensor_id)
    return ("legacy", zone_id, node_id or 0, metric_type or "", channel or "")


def build_realtime_key_from_update(update: dict) -> tuple:
    return (
        "legacy",
        int(update.get("zone_id") or 0),
        int(update.get("node_id") or 0),
        str(update.get("metric_type") or ""),
        str(update.get("channel") or ""),
    )


def build_anomaly_throttle_key(
    *,
    code: str,
    gh_uid: Optional[str],
    zone_uid: Optional[str],
    node_uid: Optional[str],
    channel: Optional[str],
) -> str:
    return "|".join(
        [
            code,
            gh_uid or "-",
            zone_uid or "-",
            node_uid or "-",
            channel or "-",
        ]
    )


def is_temp_namespace(gh_uid: Optional[str], zone_uid: Optional[str]) -> bool:
    return (gh_uid or "").startswith("gh-temp") or (zone_uid or "").startswith("zn-temp")


def parse_node_info(
    node_info: object,
) -> tuple[Optional[int], Optional[int], Optional[int]]:
    if not isinstance(node_info, tuple) or len(node_info) < 2:
        return None, None, None
    node_id_raw = node_info[0]
    node_zone_id_raw = node_info[1]
    pending_zone_id_raw = node_info[2] if len(node_info) >= 3 else None
    node_id = int(node_id_raw) if isinstance(node_id_raw, int) else None
    node_zone_id = int(node_zone_id_raw) if isinstance(node_zone_id_raw, int) else None
    pending_zone_id = (
        int(pending_zone_id_raw) if isinstance(pending_zone_id_raw, int) else None
    )
    return node_id, node_zone_id, pending_zone_id
