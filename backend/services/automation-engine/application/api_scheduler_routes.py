"""Scheduler route helpers for API decomposition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from fastapi import HTTPException


def task_public_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "zone_id": task["zone_id"],
        "task_type": task["task_type"],
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "scheduled_for": task.get("scheduled_for"),
        "due_at": task.get("due_at"),
        "expires_at": task.get("expires_at"),
        "correlation_id": task.get("correlation_id"),
        "result": task.get("result"),
        "error": task.get("error"),
        "error_code": task.get("error_code"),
    }


async def submit_scheduler_task(
    request: Any,
    req: Any,
    *,
    command_bus: Any,
    scheduler_task_types: Set[str],
    validate_scheduler_dispatch_lease_fn: Callable[[Any], Awaitable[None]],
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    parse_iso_datetime_fn: Callable[[Optional[str]], Optional[datetime]],
    require_iso_datetime_fn: Callable[[Optional[str], str], datetime],
    build_deadline_terminal_result_fn: Callable[..., Dict[str, Any]],
    create_scheduler_task_fn: Callable[..., Awaitable[Any]],
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    spawn_background_task_fn: Callable[..., Any],
    execute_scheduler_task_fn: Callable[[str, Any, Optional[str]], Awaitable[None]],
    get_trace_id_fn: Callable[[], Optional[str]],
    logger: Any,
) -> Dict[str, Any]:
    if not command_bus:
        raise HTTPException(status_code=503, detail="CommandBus not initialized")

    if req.task_type not in scheduler_task_types:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type: {req.task_type}")

    await validate_scheduler_dispatch_lease_fn(request)
    await validate_scheduler_zone_fn(req.zone_id)

    scheduled_for_dt: Optional[datetime] = None
    if req.scheduled_for:
        scheduled_for_dt = parse_iso_datetime_fn(req.scheduled_for)
        if scheduled_for_dt is None:
            raise HTTPException(status_code=422, detail="scheduled_for_invalid")

    due_at_dt = require_iso_datetime_fn(req.due_at, "due_at")
    expires_at_dt = require_iso_datetime_fn(req.expires_at, "expires_at")
    if expires_at_dt <= due_at_dt:
        raise HTTPException(status_code=422, detail="expires_at_must_be_after_due_at")
    if scheduled_for_dt is not None and due_at_dt < scheduled_for_dt:
        raise HTTPException(status_code=422, detail="due_at_must_be_gte_scheduled_for")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    terminal_status: Optional[str] = None
    terminal_result: Optional[Dict[str, Any]] = None
    if now > expires_at_dt:
        terminal_status = "expired"
        terminal_result = build_deadline_terminal_result_fn(
            status=terminal_status,
            now=now,
            due_at=due_at_dt,
            expires_at=expires_at_dt,
        )
    elif now > due_at_dt:
        terminal_status = "rejected"
        terminal_result = build_deadline_terminal_result_fn(
            status=terminal_status,
            now=now,
            due_at=due_at_dt,
            expires_at=expires_at_dt,
        )

    task, is_duplicate = await create_scheduler_task_fn(
        req,
        initial_status=terminal_status or "accepted",
        initial_result=terminal_result if terminal_status else None,
        initial_error=str(terminal_result.get("error")) if terminal_status and terminal_result else None,
        initial_error_code=str(terminal_result.get("error_code")) if terminal_status and terminal_result else None,
    )

    if not is_duplicate:
        if terminal_status and terminal_result:
            await create_zone_event_fn(
                req.zone_id,
                "SCHEDULE_TASK_FAILED",
                {
                    "task_id": task["task_id"],
                    "task_type": req.task_type,
                    "status": terminal_status,
                    "scheduled_for": req.scheduled_for,
                    "due_at": req.due_at,
                    "expires_at": req.expires_at,
                    "correlation_id": req.correlation_id,
                    "error": task["error"],
                    "error_code": task["error_code"],
                    "decision": terminal_result.get("decision"),
                    "reason_code": terminal_result.get("reason_code"),
                    "action_required": terminal_result.get("action_required"),
                },
            )
        else:
            try:
                await create_zone_event_fn(
                    req.zone_id,
                    "SCHEDULE_TASK_ACCEPTED",
                    {
                        "task_id": task["task_id"],
                        "task_type": req.task_type,
                        "scheduled_for": req.scheduled_for,
                        "due_at": req.due_at,
                        "expires_at": req.expires_at,
                        "correlation_id": req.correlation_id,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to create SCHEDULE_TASK_ACCEPTED event, task will still be dispatched",
                    extra={
                        "task_id": task["task_id"],
                        "zone_id": req.zone_id,
                        "task_type": req.task_type,
                        "correlation_id": req.correlation_id,
                    },
                    exc_info=True,
                )

            trace_id = get_trace_id_fn()
            spawn_background_task_fn(
                execute_scheduler_task_fn(task["task_id"], req, trace_id),
                task_name=f"scheduler_task_{task['task_id']}",
                zone_id=req.zone_id,
                task_id=task["task_id"],
                task_type=req.task_type,
            )

    return {
        "status": "ok",
        "data": {
            "task_id": task["task_id"],
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": task["status"],
            "is_duplicate": is_duplicate,
        },
    }


async def get_scheduler_task_status(
    task_id: str,
    *,
    scheduler_tasks_lock: Any,
    scheduler_tasks: Dict[str, Dict[str, Any]],
    cleanup_scheduler_tasks_locked_fn: Callable[[datetime], Awaitable[None]],
    load_scheduler_task_snapshot_fn: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
) -> Dict[str, Any]:
    async with scheduler_tasks_lock:
        await cleanup_scheduler_tasks_locked_fn(datetime.now(timezone.utc).replace(tzinfo=None))
        task = scheduler_tasks.get(task_id)

    if task is None:
        persisted = await load_scheduler_task_snapshot_fn(task_id)
        if persisted is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        async with scheduler_tasks_lock:
            scheduler_tasks[task_id] = persisted
        task = persisted

    return {"status": "ok", "data": task_public_payload(task)}


__all__ = [
    "get_scheduler_task_status",
    "submit_scheduler_task",
    "task_public_payload",
]
