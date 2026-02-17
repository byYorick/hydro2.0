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
            SELECT config
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

    zone_config = rows[0].get("config") if isinstance(rows[0].get("config"), dict) else {}
    automation = zone_config.get("automation") if isinstance(zone_config.get("automation"), dict) else {}
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
    levels = {
        "clean_tank_percent": None,
        "solution_tank_percent": None,
    }

    try:
        rows = await fetch_fn(
            """
            SELECT channel, payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type IN ('telemetry', 'status')
              AND channel IN ('lvl_clean', 'lvl_solution')
            ORDER BY created_at DESC, id DESC
            LIMIT 200
            """,
            zone_id,
        )
    except Exception:
        return levels

    for row in rows:
        channel = str(row.get("channel") or "").strip().lower()
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}

        raw_level = None
        if "value" in payload:
            raw_level = payload.get("value")
        elif isinstance(payload.get("metric"), dict):
            raw_level = payload["metric"].get("value")
        elif isinstance(payload.get("telemetry"), dict):
            raw_level = payload["telemetry"].get("value")

        level = normalize_level_percent(raw_level)
        if level is None:
            continue

        if channel == "lvl_clean" and levels["clean_tank_percent"] is None:
            levels["clean_tank_percent"] = level
        elif channel == "lvl_solution" and levels["solution_tank_percent"] is None:
            levels["solution_tank_percent"] = level

        if levels["clean_tank_percent"] is not None and levels["solution_tank_percent"] is not None:
            break

    return levels


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
    "load_zone_current_levels",
    "load_zone_system_config",
    "normalize_level_percent",
    "system_config_from_task_payload",
]
