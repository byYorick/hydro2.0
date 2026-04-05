"""Внутренние HTTP-endpoint'ы AE3-Lite."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, HTTPException, Request

from ae3lite.application.dto import TaskStatusView


def bind_internal_task_route(
    app: FastAPI,
    *,
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    load_task_status_fn: Callable[[int], Awaitable[Optional[TaskStatusView]]],
) -> Callable[..., Awaitable[dict[str, Any]]]:
    def _serialize_dt(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if isinstance(value, datetime) else None

    @app.get("/internal/tasks/{task_id}")
    async def internal_task_status(task_id: int, request: Request) -> dict[str, Any]:
        await validate_scheduler_security_baseline_fn(request)
        task = await load_task_status_fn(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail={"error": "task_not_found", "task_id": task_id})
        return {
            "status": "ok",
            "data": {
                "task_id": task.task_id,
                "zone_id": task.zone_id,
                "task_type": task.task_type,
                "status": task.status,
                "error_code": task.error_code,
                "error_message": task.error_message,
                "created_at": _serialize_dt(task.created_at),
                "updated_at": _serialize_dt(task.updated_at),
                "completed_at": _serialize_dt(task.completed_at),
            },
        }

    return internal_task_status
