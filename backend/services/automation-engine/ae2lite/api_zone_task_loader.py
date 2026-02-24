"""Helpers to resolve latest scheduler task for zone in API layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from ae2lite.api_task_snapshot import (
    is_task_active,
    pick_preferred_zone_task,
    sanitize_scheduler_task_snapshot,
    task_sort_key,
)
from ae2lite.api_payload_parsing import coerce_datetime, to_optional_int


def _task_id_from_log_name(task_name: Any) -> Optional[str]:
    if not isinstance(task_name, str):
        return None
    prefix = "ae_scheduler_task_"
    if not task_name.startswith(prefix):
        return None
    task_id = task_name[len(prefix):].strip()
    return task_id or None


def _task_sort_key(task: Dict[str, Any]) -> tuple[int, datetime]:
    return task_sort_key(
        task,
        is_task_active_fn=is_task_active,
        coerce_datetime_fn=coerce_datetime,
        now_fn=datetime.now,
    )


async def load_latest_zone_task_from_db(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> Optional[Dict[str, Any]]:
    try:
        rows = await fetch_fn(
            """
            SELECT task_name, details, created_at
            FROM scheduler_logs
            WHERE task_name LIKE 'ae_scheduler_task_st-%'
              AND details IS NOT NULL
              AND jsonb_typeof(details) = 'object'
              AND details ? 'zone_id'
              AND (details->>'zone_id') ~ '^[0-9]+$'
              AND (details->>'zone_id')::int = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """,
            zone_id,
        )
    except Exception:
        logger.warning(
            "Failed to load latest zone scheduler task from DB: zone_id=%s",
            zone_id,
            exc_info=True,
        )
        return None

    candidates: list[Dict[str, Any]] = []
    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else None
        if not isinstance(details, dict):
            continue
        fallback_task_id = _task_id_from_log_name(row.get("task_name"))
        if not details.get("created_at") and row.get("created_at") is not None:
            details = dict(details)
            details["created_at"] = row["created_at"].isoformat()
        task = sanitize_scheduler_task_snapshot(
            details,
            to_optional_int_fn=to_optional_int,
            fallback_task_id=fallback_task_id,
        )
        if task is not None:
            candidates.append(task)

    return pick_preferred_zone_task(candidates, task_sort_key_fn=_task_sort_key)


async def load_latest_zone_task(
    zone_id: int,
    *,
    scheduler_tasks_lock: Any,
    scheduler_tasks: Dict[str, Dict[str, Any]],
    cleanup_scheduler_tasks_locked_fn: Callable[[datetime], Awaitable[None]],
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    in_memory_candidates: list[Dict[str, Any]] = []
    async with scheduler_tasks_lock:
        await cleanup_scheduler_tasks_locked_fn(now)
        for raw_task in scheduler_tasks.values():
            task = sanitize_scheduler_task_snapshot(raw_task, to_optional_int_fn=to_optional_int)
            if task is None:
                continue
            if int(task.get("zone_id") or 0) != int(zone_id):
                continue
            in_memory_candidates.append(task)

    preferred = pick_preferred_zone_task(in_memory_candidates, task_sort_key_fn=_task_sort_key)
    if preferred is not None:
        return preferred

    from_db = await load_latest_zone_task_from_db(zone_id, fetch_fn=fetch_fn, logger=logger)
    if from_db is None:
        return None

    async with scheduler_tasks_lock:
        scheduler_tasks[str(from_db["task_id"])] = dict(from_db)
    return from_db


__all__ = [
    "load_latest_zone_task",
    "load_latest_zone_task_from_db",
]
