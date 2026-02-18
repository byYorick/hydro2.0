"""Structured logging helpers for automation-engine components."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _duration_ms(started_at: Optional[datetime]) -> Optional[int]:
    if started_at is None:
        return None
    try:
        delta = datetime.now(timezone.utc).replace(tzinfo=None) - started_at
    except Exception:
        return None
    return max(0, int(delta.total_seconds() * 1000))


def build_structured_extra(
    *,
    component: str,
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
    workflow: Optional[str] = None,
    workflow_phase: Optional[str] = None,
    decision: Optional[str] = None,
    reason_code: Optional[str] = None,
    command_count: Optional[int] = None,
    result_status: Optional[str] = None,
    correlation_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    started_at: Optional[datetime] = None,
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "component": component,
        "zone_id": zone_id,
        "task_id": task_id,
        "task_type": task_type,
        "workflow": workflow,
        "workflow_phase": workflow_phase,
        "decision": decision,
        "reason_code": reason_code,
        "command_count": command_count,
        "result_status": result_status,
        "correlation_id": correlation_id,
        "duration_ms": duration_ms if duration_ms is not None else _duration_ms(started_at),
    }
    payload.update(extra)
    return payload


def log_structured(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    component: str,
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
    workflow: Optional[str] = None,
    workflow_phase: Optional[str] = None,
    decision: Optional[str] = None,
    reason_code: Optional[str] = None,
    command_count: Optional[int] = None,
    result_status: Optional[str] = None,
    correlation_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    started_at: Optional[datetime] = None,
    **extra: Any,
) -> None:
    logger.log(
        level,
        message,
        extra=build_structured_extra(
            component=component,
            zone_id=zone_id,
            task_id=task_id,
            task_type=task_type,
            workflow=workflow,
            workflow_phase=workflow_phase,
            decision=decision,
            reason_code=reason_code,
            command_count=command_count,
            result_status=result_status,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            started_at=started_at,
            **extra,
        ),
    )
