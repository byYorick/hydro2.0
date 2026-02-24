"""Scheduler task in-memory/DB snapshot helpers for API decomposition."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from fastapi import HTTPException
from prometheus_client import Counter
from services.resilience_contract import (
    SCHEDULER_IDEMPOTENCY_PAYLOAD_MISMATCH,
    SCHEDULER_STATUS_ACCEPTED,
)

SCHEDULER_DEDUPE_DECISIONS_TOTAL = Counter(
    "scheduler_dedupe_decisions_total",
    "Scheduler dedupe/idempotency decisions",
    ["outcome"],
)


def scheduler_task_log_name(task_id: str) -> str:
    return f"ae_scheduler_task_{task_id}"


async def persist_scheduler_task_snapshot(
    task: Dict[str, Any],
    *,
    create_scheduler_log_fn: Callable[[str, str, Dict[str, Any]], Awaitable[Any]],
    logger: Any,
) -> None:
    try:
        await create_scheduler_log_fn(
            scheduler_task_log_name(task["task_id"]),
            str(task.get("status") or "unknown"),
            dict(task),
        )
    except Exception:
        logger.warning(
            "Failed to persist scheduler task snapshot: task_id=%s",
            task.get("task_id"),
            exc_info=True,
        )


async def load_scheduler_task_snapshot(
    task_id: str,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> Optional[Dict[str, Any]]:
    try:
        rows = await fetch_fn(
            """
            SELECT status, details, created_at
            FROM scheduler_logs
            WHERE task_name = $1
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            scheduler_task_log_name(task_id),
        )
    except Exception:
        logger.warning("Failed to read scheduler task snapshot from DB: task_id=%s", task_id, exc_info=True)
        return None

    if not rows:
        return None

    row = rows[0]
    details = row.get("details")
    if not isinstance(details, dict):
        details = {}
    row_created_at = row.get("created_at")
    row_created_iso = row_created_at.isoformat() if row_created_at else None

    task_snapshot = {
        "task_id": details.get("task_id") or task_id,
        "zone_id": details.get("zone_id"),
        "task_type": details.get("task_type"),
        "status": details.get("status") or row.get("status") or "unknown",
        "created_at": details.get("created_at") or row_created_iso,
        "updated_at": details.get("updated_at") or row_created_iso,
        "scheduled_for": details.get("scheduled_for"),
        "due_at": details.get("due_at"),
        "expires_at": details.get("expires_at"),
        "correlation_id": details.get("correlation_id"),
        "payload_fingerprint": details.get("payload_fingerprint"),
        "result": details.get("result"),
        "error": details.get("error"),
        "error_code": details.get("error_code"),
        "payload": details.get("payload") if isinstance(details.get("payload"), dict) else {},
    }

    if not task_snapshot["zone_id"] or not task_snapshot["task_type"]:
        return None
    return task_snapshot


async def cleanup_scheduler_tasks_locked(
    now: datetime,
    *,
    scheduler_tasks: Dict[str, Dict[str, Any]],
    scheduler_task_ttl_seconds: int,
    scheduler_task_max_in_memory: int,
    normalize_cleanup_timestamp_fn: Callable[[Any, datetime], datetime],
) -> None:
    to_delete = []
    threshold = now - timedelta(seconds=scheduler_task_ttl_seconds)
    for task_id, task in scheduler_tasks.items():
        updated_at = normalize_cleanup_timestamp_fn(task.get("updated_at"), now)
        if updated_at < threshold:
            to_delete.append(task_id)
    for task_id in to_delete:
        scheduler_tasks.pop(task_id, None)

    overflow = len(scheduler_tasks) - scheduler_task_max_in_memory
    if overflow > 0:
        sortable = []
        for task_id, task in scheduler_tasks.items():
            updated_at = normalize_cleanup_timestamp_fn(task.get("updated_at"), now)
            sortable.append((updated_at, task_id))
        sortable.sort(key=lambda item: item[0])
        for _, task_id in sortable[:overflow]:
            scheduler_tasks.pop(task_id, None)


async def load_scheduler_task_by_correlation_id(
    correlation_id: str,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    scheduler_dedupe_window_sec: int,
    logger: Any,
) -> Optional[Dict[str, Any]]:
    threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=scheduler_dedupe_window_sec)
    try:
        rows = await fetch_fn(
            """
            SELECT details
            FROM scheduler_logs
            WHERE task_name LIKE 'ae_scheduler_task_st-%'
              AND details->>'correlation_id' = $1
              AND created_at >= $2
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            correlation_id,
            threshold,
        )
    except Exception:
        logger.warning(
            "Failed to read scheduler task by correlation_id from DB: correlation_id=%s",
            correlation_id,
            exc_info=True,
        )
        return None

    if not rows:
        return None
    details = rows[0].get("details")
    if not isinstance(details, dict):
        return None
    if not details.get("task_id") or not details.get("zone_id") or not details.get("task_type"):
        return None
    return details


async def create_scheduler_task(
    req: Any,
    *,
    scheduler_tasks: Dict[str, Dict[str, Any]],
    scheduler_tasks_lock: Any,
    cleanup_scheduler_tasks_locked_fn: Callable[[datetime], Awaitable[None]],
    load_scheduler_task_by_correlation_id_fn: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
    task_payload_fingerprint_fn: Callable[[Any], str],
    task_payload_matches_fn: Callable[[Any, Dict[str, Any], str], bool],
    new_scheduler_task_id_fn: Callable[[], str],
    persist_scheduler_task_snapshot_fn: Callable[[Dict[str, Any]], Awaitable[None]],
    initial_status: str = SCHEDULER_STATUS_ACCEPTED,
    initial_result: Optional[Dict[str, Any]] = None,
    initial_error: Optional[str] = None,
    initial_error_code: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    payload_fingerprint = task_payload_fingerprint_fn(req)

    async with scheduler_tasks_lock:
        await cleanup_scheduler_tasks_locked_fn(datetime.now(timezone.utc).replace(tzinfo=None))

        existing_in_memory: Optional[Dict[str, Any]] = None
        for candidate in scheduler_tasks.values():
            if candidate.get("correlation_id") == req.correlation_id:
                existing_in_memory = dict(candidate)
                break

        existing = existing_in_memory
        if existing is None:
            existing = await load_scheduler_task_by_correlation_id_fn(req.correlation_id)
            if existing is not None:
                scheduler_tasks[str(existing["task_id"])] = dict(existing)

        if existing is not None:
            if not task_payload_matches_fn(req, existing, payload_fingerprint):
                SCHEDULER_DEDUPE_DECISIONS_TOTAL.labels(outcome="payload_mismatch").inc()
                raise HTTPException(status_code=409, detail=SCHEDULER_IDEMPOTENCY_PAYLOAD_MISMATCH)
            SCHEDULER_DEDUPE_DECISIONS_TOTAL.labels(outcome="duplicate").inc()
            return dict(existing), True

        task = {
            "task_id": new_scheduler_task_id_fn(),
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": initial_status,
            "payload": req.payload or {},
            "created_at": now_iso,
            "updated_at": now_iso,
            "scheduled_for": req.scheduled_for,
            "due_at": req.due_at,
            "expires_at": req.expires_at,
            "correlation_id": req.correlation_id,
            "payload_fingerprint": payload_fingerprint,
            "result": dict(initial_result) if isinstance(initial_result, dict) else None,
            "error": initial_error,
            "error_code": initial_error_code,
        }
        scheduler_tasks[task["task_id"]] = task
        SCHEDULER_DEDUPE_DECISIONS_TOTAL.labels(outcome="new").inc()

    await persist_scheduler_task_snapshot_fn(task)
    return task, False


async def update_scheduler_task(
    *,
    task_id: str,
    status: str,
    scheduler_tasks: Dict[str, Dict[str, Any]],
    scheduler_tasks_lock: Any,
    persist_scheduler_task_snapshot_fn: Callable[[Dict[str, Any]], Awaitable[None]],
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    async with scheduler_tasks_lock:
        task = scheduler_tasks.get(task_id)
        if not task:
            return
        task["status"] = status
        task["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error
        if error_code is not None:
            task["error_code"] = error_code
        snapshot = dict(task)

    await persist_scheduler_task_snapshot_fn(snapshot)


__all__ = [
    "cleanup_scheduler_tasks_locked",
    "create_scheduler_task",
    "load_scheduler_task_by_correlation_id",
    "load_scheduler_task_snapshot",
    "persist_scheduler_task_snapshot",
    "scheduler_task_log_name",
    "update_scheduler_task",
]
