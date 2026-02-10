"""Общий helper для постановки internal enqueue задач scheduler."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from common.db import create_scheduler_log, create_zone_event

SUPPORTED_SCHEDULER_TASK_TYPES = {
    "irrigation",
    "lighting",
    "ventilation",
    "solution_change",
    "mist",
    "diagnostics",
}


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def enqueue_internal_scheduler_task(
    *,
    zone_id: int,
    task_type: str,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[str] = None,
    expires_at: Optional[str] = None,
    correlation_id: Optional[str] = None,
    source: str = "automation-engine",
) -> Dict[str, Any]:
    normalized_task_type = str(task_type or "").strip().lower()
    if normalized_task_type not in SUPPORTED_SCHEDULER_TASK_TYPES:
        raise ValueError(f"Unsupported task_type: {task_type}")

    now = datetime.utcnow()
    scheduled_for_dt = parse_iso_datetime(scheduled_for) or now
    expires_at_dt = parse_iso_datetime(expires_at)
    if expires_at_dt and expires_at_dt <= now:
        raise ValueError("expires_at_is_in_the_past")

    enqueue_id = f"enq-{uuid4().hex}"
    effective_correlation_id = correlation_id or f"ae:self:{zone_id}:{normalized_task_type}:{enqueue_id}"
    task_name = f"ae_internal_enqueue_{enqueue_id}"
    details = {
        "enqueue_id": enqueue_id,
        "zone_id": int(zone_id),
        "task_type": normalized_task_type,
        "payload": payload if isinstance(payload, dict) else {},
        "scheduled_for": scheduled_for_dt.isoformat(),
        "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
        "correlation_id": effective_correlation_id,
        "source": source,
        "status": "pending",
        "created_at": now.isoformat(),
    }

    await create_scheduler_log(task_name, "pending", details)
    await create_zone_event(
        int(zone_id),
        "SELF_TASK_ENQUEUED",
        {
            "enqueue_id": enqueue_id,
            "task_type": normalized_task_type,
            "scheduled_for": details["scheduled_for"],
            "expires_at": details["expires_at"],
            "correlation_id": effective_correlation_id,
            "source": source,
        },
    )

    return {
        "enqueue_id": enqueue_id,
        "status": "pending",
        "zone_id": int(zone_id),
        "task_type": normalized_task_type,
        "scheduled_for": details["scheduled_for"],
        "expires_at": details["expires_at"],
        "correlation_id": effective_correlation_id,
        "task_name": task_name,
        "details": details,
    }

