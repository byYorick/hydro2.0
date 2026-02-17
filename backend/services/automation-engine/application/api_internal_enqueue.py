"""Internal enqueue endpoint helper for scheduler tasks."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Set

from fastapi import HTTPException


async def scheduler_internal_enqueue(
    req: Any,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    scheduler_task_types: Set[str],
    enqueue_internal_scheduler_task_fn: Callable[..., Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    await validate_scheduler_zone_fn(req.zone_id)
    if req.task_type not in scheduler_task_types:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type: {req.task_type}")

    try:
        enqueue_result = await enqueue_internal_scheduler_task_fn(
            zone_id=req.zone_id,
            task_type=req.task_type,
            payload=req.payload or {},
            scheduled_for=req.scheduled_for,
            expires_at=req.expires_at,
            correlation_id=req.correlation_id,
            source=req.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "status": "ok",
        "data": {
            "enqueue_id": enqueue_result["enqueue_id"],
            "status": enqueue_result["status"],
            "zone_id": enqueue_result["zone_id"],
            "task_type": enqueue_result["task_type"],
            "scheduled_for": enqueue_result["scheduled_for"],
            "expires_at": enqueue_result["expires_at"],
            "correlation_id": enqueue_result["correlation_id"],
        },
    }


__all__ = ["scheduler_internal_enqueue"]
