"""Zone automation state data-loading helpers for API decomposition."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional


def system_config_from_task_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}

    tanks_count = execution.get("tanks_count")
    if tanks_count is None:
        tanks_count = payload.get("tanks_count")

    system_type = execution.get("system_type")
    if not system_type:
        system_type = payload.get("system_type")

    clean_capacity = execution.get("clean_tank_fill_l")
    if clean_capacity is None:
        clean_capacity = execution.get("clean_tank_capacity_l")
    if clean_capacity is None:
        clean_capacity = payload.get("clean_tank_fill_l")

    nutrient_capacity = execution.get("nutrient_tank_target_l")
    if nutrient_capacity is None:
        nutrient_capacity = execution.get("nutrient_tank_capacity_l")
    if nutrient_capacity is None:
        nutrient_capacity = payload.get("nutrient_tank_target_l")

    return {
        "tanks_count": tanks_count if tanks_count is not None else 2,
        "system_type": system_type or "drip",
        "clean_tank_capacity_l": clean_capacity,
        "nutrient_tank_capacity_l": nutrient_capacity,
    }


async def load_zone_system_config(
    zone_id: int,
    task_payload: Dict[str, Any],
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    task_config = system_config_from_task_payload(task_payload)

    try:
        rows = await fetch_fn(
            """
            SELECT settings
            FROM zones
            WHERE id = $1
            LIMIT 1
            """,
            zone_id,
        )
    except Exception:
        return task_config

    if not rows:
        return task_config

    zone_settings = rows[0].get("settings") if isinstance(rows[0].get("settings"), dict) else {}
    legacy_config = zone_settings.get("config") if isinstance(zone_settings.get("config"), dict) else {}
    automation = zone_settings.get("automation") if isinstance(zone_settings.get("automation"), dict) else {}
    if not automation:
        automation = legacy_config.get("automation") if isinstance(legacy_config.get("automation"), dict) else {}
    two_tank = automation.get("two_tank") if isinstance(automation.get("two_tank"), dict) else {}

    tanks_count = two_tank.get("tanks_count")
    if tanks_count is None:
        tanks_count = task_config.get("tanks_count", 2)

    system_type = two_tank.get("system_type") or task_config.get("system_type") or "drip"

    clean_capacity = two_tank.get("clean_tank_fill_l")
    if clean_capacity is None:
        clean_capacity = task_config.get("clean_tank_capacity_l")

    nutrient_capacity = two_tank.get("nutrient_tank_target_l")
    if nutrient_capacity is None:
        nutrient_capacity = task_config.get("nutrient_tank_capacity_l")

    return {
        "tanks_count": tanks_count,
        "system_type": system_type,
        "clean_tank_capacity_l": clean_capacity,
        "nutrient_tank_capacity_l": nutrient_capacity,
    }


def normalize_level_percent(raw_value: Any) -> Optional[float]:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    if value < 0.0:
        return 0.0
    if value > 100.0:
        return 100.0
    return round(value, 2)


async def load_zone_current_levels(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    levels: Dict[str, Any] = {
        "clean_tank_level_percent": None,
        "nutrient_tank_level_percent": None,
        "ph": None,
        "ec": None,
    }

    try:
        rows = await fetch_fn(
            """
            SELECT
                s.type AS sensor_type,
                LOWER(TRIM(COALESCE(s.label, ''))) AS sensor_label,
                tl.last_value AS value
            FROM telemetry_last tl
            JOIN sensors s ON s.id = tl.sensor_id
            WHERE s.zone_id = $1
              AND s.is_active = TRUE
              AND (
                (s.type = 'WATER_LEVEL'
                 AND LOWER(TRIM(COALESCE(s.label, ''))) IN ('lvl_clean', 'lvl_solution'))
                OR s.type IN ('PH', 'EC')
              )
            ORDER BY s.type, tl.last_ts DESC NULLS LAST, tl.updated_at DESC NULLS LAST
            LIMIT 10
            """,
            zone_id,
        )
    except Exception:
        return levels

    for row in rows:
        sensor_type = str(row.get("sensor_type") or "").strip().upper()
        sensor_label = str(row.get("sensor_label") or "").strip().lower()
        raw_value = row.get("value")

        if sensor_type == "WATER_LEVEL":
            if sensor_label == "lvl_clean" and levels["clean_tank_level_percent"] is None:
                levels["clean_tank_level_percent"] = normalize_level_percent(raw_value)
            elif sensor_label == "lvl_solution" and levels["nutrient_tank_level_percent"] is None:
                levels["nutrient_tank_level_percent"] = normalize_level_percent(raw_value)
        elif sensor_type == "PH" and levels["ph"] is None:
            try:
                levels["ph"] = round(float(raw_value), 2) if raw_value is not None else None
            except (TypeError, ValueError):
                pass
        elif sensor_type == "EC" and levels["ec"] is None:
            try:
                levels["ec"] = round(float(raw_value), 1) if raw_value is not None else None
            except (TypeError, ValueError):
                pass

    return levels


_IRR_STATE_FIELDS = (
    "clean_level_max",
    "clean_level_min",
    "solution_level_max",
    "solution_level_min",
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
    "pump_main",
)


_IRR_STATE_ALIASES = {
    "clean_level_max": ("clean_level_max", "level_clean_max"),
    "clean_level_min": ("clean_level_min", "level_clean_min"),
    "solution_level_max": ("solution_level_max", "level_solution_max"),
    "solution_level_min": ("solution_level_min", "level_solution_min"),
    "valve_clean_fill": ("valve_clean_fill",),
    "valve_clean_supply": ("valve_clean_supply",),
    "valve_solution_fill": ("valve_solution_fill",),
    "valve_solution_supply": ("valve_solution_supply",),
    "valve_irrigation": ("valve_irrigation",),
    "pump_main": ("pump_main", "main_pump"),
}


def _to_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def normalize_irr_node_state_snapshot(raw_snapshot: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_snapshot, dict):
        return None

    normalized: Dict[str, Any] = {}
    for field in _IRR_STATE_FIELDS:
        value: Optional[bool] = None
        for alias in _IRR_STATE_ALIASES[field]:
            if alias in raw_snapshot:
                value = _to_optional_bool(raw_snapshot.get(alias))
                break
        normalized[field] = value

    if not any(value is not None for value in normalized.values()):
        return None
    return normalized


async def load_latest_irr_node_state(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Optional[logging.Logger] = None,
) -> Optional[Dict[str, Any]]:
    try:
        rows = await fetch_fn(
            """
            SELECT payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'IRR_STATE_SNAPSHOT'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
    except Exception:
        if logger is not None:
            logger.debug("Failed to load irr node state snapshot for zone_id=%s", zone_id, exc_info=True)
        return None

    if not rows:
        return None

    row = rows[0]
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    snapshot_raw = payload.get("snapshot")
    if not isinstance(snapshot_raw, dict):
        snapshot_raw = payload.get("state")
    snapshot = normalize_irr_node_state_snapshot(snapshot_raw)
    if snapshot is None:
        return None

    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        snapshot["updated_at"] = created_at.isoformat()
    else:
        snapshot["updated_at"] = None
    return snapshot


async def load_automation_timeline(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    extract_timeline_reason_fn: Callable[[Dict[str, Any]], Optional[str]],
    build_timeline_label_fn: Callable[[str, Optional[str]], str],
    logger: Optional[logging.Logger] = None,
    limit: int = 24,
) -> list[Dict[str, Any]]:
    event_types = [
        "SCHEDULE_TASK_ACCEPTED",
        "SCHEDULE_TASK_COMPLETED",
        "SCHEDULE_TASK_FAILED",
        "SCHEDULE_TASK_EXECUTION_STARTED",
        "SCHEDULE_TASK_EXECUTION_FINISHED",
        "TASK_RECEIVED",
        "TASK_STARTED",
        "DECISION_MADE",
        "COMMAND_DISPATCHED",
        "COMMAND_FAILED",
        "TASK_FINISHED",
        "TWO_TANK_STARTUP_INITIATED",
        "CLEAN_FILL_COMPLETED",
        "SOLUTION_FILL_COMPLETED",
        "CLEAN_FILL_RETRY_STARTED",
        "PREPARE_TARGETS_REACHED",
    ]

    try:
        rows = await fetch_fn(
            """
            SELECT id, type, payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type = ANY($2::text[])
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            """,
            zone_id,
            event_types,
            max(1, min(limit, 50)),
        )
    except Exception:
        if logger is not None:
            logger.debug("Failed to load automation timeline for zone_id=%s", zone_id, exc_info=True)
        return []

    timeline: list[Dict[str, Any]] = []
    for row in reversed(rows):
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        event_type = str(payload.get("event_type") or row.get("type") or "").strip()
        if not event_type:
            continue
        reason_code = extract_timeline_reason_fn(payload)
        created_at = row.get("created_at")
        timestamp = (
            created_at.isoformat()
            if isinstance(created_at, datetime)
            else datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        )
        timeline.append(
            {
                "event": event_type,
                "label": build_timeline_label_fn(event_type, reason_code),
                "timestamp": timestamp,
                "active": False,
            }
        )

    if timeline:
        timeline[-1]["active"] = True
    return timeline


__all__ = [
    "load_automation_timeline",
    "load_latest_irr_node_state",
    "load_zone_current_levels",
    "load_zone_system_config",
    "normalize_level_percent",
    "normalize_irr_node_state_snapshot",
    "system_config_from_task_payload",
]
