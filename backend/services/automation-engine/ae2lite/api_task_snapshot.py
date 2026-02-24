"""Helpers for selecting/sanitizing scheduler task snapshots in API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple


def is_task_active(task: Dict[str, Any]) -> bool:
    status = str(task.get("status") or "").strip().lower()
    return status in {"accepted", "running"}


def task_sort_key(
    task: Dict[str, Any],
    *,
    is_task_active_fn: Callable[[Dict[str, Any]], bool],
    coerce_datetime_fn: Callable[[Any], Optional[datetime]],
    now_fn: Callable[[], datetime],
) -> Tuple[int, datetime]:
    active_rank = 1 if is_task_active_fn(task) else 0
    timestamp = coerce_datetime_fn(task.get("updated_at")) or coerce_datetime_fn(task.get("created_at")) or now_fn()
    return active_rank, timestamp


def pick_preferred_zone_task(
    tasks: list[Dict[str, Any]],
    *,
    task_sort_key_fn: Callable[[Dict[str, Any]], Tuple[int, datetime]],
) -> Optional[Dict[str, Any]]:
    if not tasks:
        return None
    ordered = sorted(tasks, key=task_sort_key_fn, reverse=True)
    return dict(ordered[0])


def sanitize_scheduler_task_snapshot(
    raw_task: Dict[str, Any],
    *,
    to_optional_int_fn: Callable[[Any], Optional[int]],
    fallback_task_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    task_id_raw = raw_task.get("task_id") or fallback_task_id
    task_id = str(task_id_raw or "").strip()
    zone_id = to_optional_int_fn(raw_task.get("zone_id"))
    task_type = str(raw_task.get("task_type") or "").strip().lower()
    status = str(raw_task.get("status") or "").strip().lower()
    payload = raw_task.get("payload") if isinstance(raw_task.get("payload"), dict) else {}
    result = raw_task.get("result") if isinstance(raw_task.get("result"), dict) else {}

    if not task_id or zone_id is None or not task_type:
        return None

    return {
        "task_id": task_id,
        "zone_id": zone_id,
        "task_type": task_type,
        "status": status or "unknown",
        "payload": payload,
        "result": result,
        "created_at": raw_task.get("created_at"),
        "updated_at": raw_task.get("updated_at"),
        "scheduled_for": raw_task.get("scheduled_for"),
        "due_at": raw_task.get("due_at"),
        "expires_at": raw_task.get("expires_at"),
        "correlation_id": raw_task.get("correlation_id"),
        "error": raw_task.get("error"),
        "error_code": raw_task.get("error_code"),
    }


__all__ = [
    "is_task_active",
    "pick_preferred_zone_task",
    "sanitize_scheduler_task_snapshot",
    "task_sort_key",
]
