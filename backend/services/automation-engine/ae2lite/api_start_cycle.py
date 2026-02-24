"""Helpers for canonical /zones/{zone_id}/start-cycle endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from ae2lite.api_contracts import SchedulerTaskRequest, StartCycleRequest

DEFAULT_START_CYCLE_WORKFLOW = "cycle_start"


def build_start_cycle_scheduler_task_request(
    *,
    zone_id: int,
    req: StartCycleRequest,
    now: datetime,
    due_in_sec: int,
    expires_in_sec: int,
    default_topology: str,
) -> SchedulerTaskRequest:
    due_at = now + timedelta(seconds=max(1, int(due_in_sec)))
    expires_at = now + timedelta(seconds=max(2, int(expires_in_sec)))

    execution = {
        "topology": default_topology,
        "workflow": DEFAULT_START_CYCLE_WORKFLOW,
    }
    payload: Dict[str, Any] = {
        "workflow": DEFAULT_START_CYCLE_WORKFLOW,
        "topology": default_topology,
        "source": req.source,
        "config": {"execution": execution},
        "trigger": "start_cycle_api",
    }

    return SchedulerTaskRequest(
        zone_id=zone_id,
        task_type="diagnostics",
        payload=payload,
        scheduled_for=now.isoformat(),
        due_at=due_at.isoformat(),
        expires_at=expires_at.isoformat(),
        correlation_id=f"start-cycle:{zone_id}:{req.idempotency_key}",
    )


def build_start_cycle_response(
    *,
    zone_id: int,
    req: StartCycleRequest,
    is_duplicate: bool,
    task_id: str,
) -> Dict[str, Any]:
    return {
        "status": "ok",
        "data": {
            "zone_id": zone_id,
            "accepted": True,
            "runner_state": "active",
            "deduplicated": is_duplicate,
            "task_id": task_id,
            "idempotency_key": req.idempotency_key,
        },
    }


__all__ = [
    "DEFAULT_START_CYCLE_WORKFLOW",
    "build_start_cycle_response",
    "build_start_cycle_scheduler_task_request",
]
