"""Общий helper для постановки internal enqueue задач scheduler."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from common.db import create_scheduler_log, create_zone_event

logger = logging.getLogger(__name__)

SUPPORTED_SCHEDULER_TASK_TYPES = {
    "irrigation",
    "lighting",
    "ventilation",
    "solution_change",
    "mist",
    "diagnostics",
}


def _env_true(name: str, default: str = "1") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


_AE_INTERNAL_ENQUEUE_RUNTIME_DISPATCH_ENABLED = _env_true("AE_INTERNAL_ENQUEUE_RUNTIME_DISPATCH_ENABLED", "1")
_INTERNAL_ENQUEUE_DUE_SEC = max(5, int(os.getenv("AE_INTERNAL_ENQUEUE_DUE_SEC", "60")))
_INTERNAL_ENQUEUE_EXPIRES_SEC = max(
    _INTERNAL_ENQUEUE_DUE_SEC + 5,
    int(os.getenv("AE_INTERNAL_ENQUEUE_EXPIRES_SEC", "900")),
)


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


async def _schedule_runtime_dispatch_if_possible(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    scheduled_for_dt: datetime,
    expires_at_dt: Optional[datetime],
    correlation_id: str,
    enqueue_id: str,
    task_name: str,
) -> Optional[Dict[str, Any]]:
    if not _AE_INTERNAL_ENQUEUE_RUNTIME_DISPATCH_ENABLED:
        return None

    try:
        from ae2lite.api_contracts import SchedulerTaskRequest
        import ae2lite.api_runtime as api_runtime
        from utils.logging_context import get_trace_id
    except Exception:
        return None

    create_task_fn = getattr(api_runtime, "_create_scheduler_task", None)
    execute_task_fn = getattr(api_runtime, "_execute_scheduler_task", None)
    spawn_task_fn = getattr(api_runtime, "_spawn_background_task", None)
    if not callable(create_task_fn) or not callable(execute_task_fn) or not callable(spawn_task_fn):
        return None
    # NOTE: We intentionally do NOT abort here if command_bus/zone_service are None.
    # At startup, workflow-state recovery runs before run_runtime_cycle initialises these.
    # _dispatch_when_due will poll for readiness instead.
    _task_type_normalized = str(task_type).strip().lower()

    due_at_dt = scheduled_for_dt + timedelta(seconds=_INTERNAL_ENQUEUE_DUE_SEC)
    effective_expires_dt = expires_at_dt or (scheduled_for_dt + timedelta(seconds=_INTERNAL_ENQUEUE_EXPIRES_SEC))
    if effective_expires_dt <= due_at_dt:
        effective_expires_dt = due_at_dt + timedelta(seconds=5)

    req = SchedulerTaskRequest(
        zone_id=int(zone_id),
        task_type=str(task_type).strip().lower(),
        payload=payload,
        scheduled_for=scheduled_for_dt.isoformat(),
        due_at=due_at_dt.isoformat(),
        expires_at=effective_expires_dt.isoformat(),
        correlation_id=correlation_id,
    )

    async def _dispatch_when_due() -> None:
        delay_sec = (scheduled_for_dt - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()
        if delay_sec > 0:
            await asyncio.sleep(delay_sec)

        # Wait for runtime services to become available.
        # This handles the startup race: workflow-state recovery may run during FastAPI lifespan
        # before run_runtime_cycle has initialised _command_bus / _zone_service.
        _svc_wait_timeout_sec = 30.0
        _svc_waited = 0.0
        while True:
            _cb = getattr(api_runtime, "_command_bus", None)
            _zs = getattr(api_runtime, "_zone_service", None)
            if _cb is not None and (_task_type_normalized != "diagnostics" or _zs is not None):
                break
            if _svc_waited >= _svc_wait_timeout_sec:
                logger.warning(
                    "Internal enqueue dispatch aborted: runtime services not ready after %.0fs "
                    "(enqueue_id=%s zone_id=%s task_type=%s command_bus=%s zone_service=%s)",
                    _svc_wait_timeout_sec,
                    enqueue_id,
                    zone_id,
                    _task_type_normalized,
                    "ready" if _cb is not None else "None",
                    "ready" if _zs is not None else "None",
                )
                return
            await asyncio.sleep(0.5)
            _svc_waited += 0.5

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if expires_at_dt is not None and now >= expires_at_dt:
            try:
                await create_scheduler_log(
                    task_name,
                    "expired",
                    {
                        "enqueue_id": enqueue_id,
                        "zone_id": int(zone_id),
                        "task_type": str(task_type).strip().lower(),
                        "status": "expired",
                        "scheduled_for": scheduled_for_dt.isoformat(),
                        "expires_at": expires_at_dt.isoformat(),
                        "correlation_id": correlation_id,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to persist internal enqueue expiration snapshot: enqueue_id=%s zone_id=%s",
                    enqueue_id,
                    zone_id,
                    exc_info=True,
                )
            return

        task, is_duplicate = await create_task_fn(req)
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            logger.warning(
                "Internal enqueue runtime dispatch skipped: task created without task_id (enqueue_id=%s zone_id=%s)",
                enqueue_id,
                zone_id,
            )
            return

        dispatch_status = "deduplicated" if bool(is_duplicate) else "accepted"
        try:
            await create_scheduler_log(
                task_name,
                dispatch_status,
                {
                    "enqueue_id": enqueue_id,
                    "zone_id": int(zone_id),
                    "task_type": str(task_type).strip().lower(),
                    "status": dispatch_status,
                    "scheduled_for": scheduled_for_dt.isoformat(),
                    "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
                    "correlation_id": correlation_id,
                    "scheduler_task_id": task_id,
                },
            )
        except Exception:
            logger.warning(
                "Failed to persist internal enqueue dispatch snapshot: enqueue_id=%s zone_id=%s task_id=%s",
                enqueue_id,
                zone_id,
                task_id,
                exc_info=True,
            )

        if bool(is_duplicate):
            return

        trace_id: Optional[str] = None
        try:
            trace_id = get_trace_id()
        except Exception:
            trace_id = None
        await execute_task_fn(task_id, req, trace_id)

    spawn_task_fn(
        _dispatch_when_due(),
        task_name=f"internal_enqueue_dispatch_{enqueue_id}",
        zone_id=int(zone_id),
        task_type=str(task_type).strip().lower(),
    )
    return {
        "status": "scheduled",
        "scheduled_for": scheduled_for_dt.isoformat(),
        "due_at": due_at_dt.isoformat(),
        "expires_at": effective_expires_dt.isoformat(),
    }


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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    scheduled_for_dt = parse_iso_datetime(scheduled_for)
    if scheduled_for is not None and scheduled_for_dt is None:
        raise ValueError("scheduled_for_invalid")
    if scheduled_for_dt is None:
        scheduled_for_dt = now

    expires_at_dt = parse_iso_datetime(expires_at)
    if expires_at is not None and expires_at_dt is None:
        raise ValueError("expires_at_invalid")
    if expires_at_dt and expires_at_dt <= now:
        raise ValueError("expires_at_is_in_the_past")
    if expires_at_dt and expires_at_dt < scheduled_for_dt:
        raise ValueError("expires_at_before_scheduled_for")

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
    try:
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
    except Exception:
        # Не роняем enqueue после успешного pending-log, иначе клиентский retry
        # может создать дубликаты self-task.
        logger.warning(
            "Failed to create SELF_TASK_ENQUEUED event for enqueue_id=%s zone_id=%s",
            enqueue_id,
            zone_id,
            exc_info=True,
        )

    runtime_dispatch = await _schedule_runtime_dispatch_if_possible(
        zone_id=int(zone_id),
        task_type=normalized_task_type,
        payload=details["payload"],
        scheduled_for_dt=scheduled_for_dt,
        expires_at_dt=expires_at_dt,
        correlation_id=effective_correlation_id,
        enqueue_id=enqueue_id,
        task_name=task_name,
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
        "runtime_dispatch": runtime_dispatch,
    }
