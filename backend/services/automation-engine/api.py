"""
FastAPI endpoints для automation-engine.
Предоставляет REST API для scheduler и других сервисов.
"""
import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal, Tuple

from infrastructure import CommandBus
from common.infra_alerts import send_infra_exception_alert
from common.db import fetch, create_scheduler_log, create_zone_event
from common.trace_context import extract_trace_id_from_headers
from utils.logging_context import set_trace_id, get_trace_id
from scheduler_task_executor import SchedulerTaskExecutor
from scheduler_internal_enqueue import (
    SUPPORTED_SCHEDULER_TASK_TYPES,
    enqueue_internal_scheduler_task,
    parse_iso_datetime as parse_enqueue_iso_datetime,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Automation Engine API")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = extract_trace_id_from_headers(request.headers)
    if trace_id:
        set_trace_id(trace_id)
    else:
        trace_id = set_trace_id()
    response = await call_next(request)
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response

# Глобальные переменные для доступа к CommandBus
_command_bus: Optional[CommandBus] = None
_gh_uid: str = ""
_zone_service: Optional[Any] = None
_scheduler_tasks: Dict[str, Dict[str, Any]] = {}
_scheduler_tasks_lock = asyncio.Lock()
_SCHEDULER_TASK_TTL_SECONDS = max(60, int(os.getenv("SCHEDULER_TASK_TTL_SECONDS", "3600")))
_SCHEDULER_TASK_MAX_IN_MEMORY = max(100, int(os.getenv("SCHEDULER_TASK_MAX_IN_MEMORY", "5000")))
_SCHEDULER_DEDUPE_WINDOW_SEC = max(60, int(os.getenv("SCHEDULER_DEDUPE_WINDOW_SEC", "86400")))
_SCHEDULER_TASK_TYPES = set(SUPPORTED_SCHEDULER_TASK_TYPES)
_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC = max(10, int(os.getenv("SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC", "60")))
_SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC = max(1, int(os.getenv("SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC", "5")))
_SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC = max(1, int(os.getenv("SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC", "30")))
_SCHEDULER_BOOTSTRAP_ENFORCE = os.getenv("SCHEDULER_BOOTSTRAP_ENFORCE", "1") == "1"
_scheduler_bootstrap_leases: Dict[str, Dict[str, Any]] = {}
_scheduler_bootstrap_lock = asyncio.Lock()

# Test hooks для детерминированных ошибок (только в test mode)
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}  # zone_id -> {controller: error_type, ...}
_zone_states_override: Dict[int, Dict[str, Any]] = {}  # zone_id -> {error_streak: int, next_allowed_run_at: datetime}


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid
    _command_bus = command_bus
    _gh_uid = gh_uid


def set_zone_service(zone_service: Any) -> None:
    """Установить ZoneAutomationService для scheduler-task fallback сценариев."""
    global _zone_service
    _zone_service = zone_service


async def _validate_scheduler_zone(zone_id: int) -> None:
    """Проверка, что зона существует."""
    try:
        rows = await fetch(
            """
            SELECT id
            FROM zones
            WHERE id = $1
            LIMIT 1
            """,
            zone_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to validate scheduler zone: zone_id=%s error=%s",
            zone_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Zone validation unavailable") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")


class SchedulerTaskRequest(BaseModel):
    """Абстрактная задача расписания от scheduler."""

    zone_id: int = Field(..., ge=1, description="Zone ID")
    task_type: Literal[
        "irrigation",
        "lighting",
        "ventilation",
        "solution_change",
        "mist",
        "diagnostics",
    ] = Field(..., description="Abstract task type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task payload")
    scheduled_for: Optional[str] = Field(default=None, description="ISO datetime when task was scheduled")
    due_at: Optional[str] = Field(default=None, description="ISO datetime when task must be started")
    expires_at: Optional[str] = Field(default=None, description="ISO datetime when task should be rejected")
    correlation_id: str = Field(..., min_length=8, max_length=128, description="Mandatory idempotency correlation ID")


class SchedulerBootstrapRequest(BaseModel):
    scheduler_id: str = Field(..., min_length=1, max_length=64)
    scheduler_version: Optional[str] = Field(default=None, max_length=64)
    protocol_version: Optional[str] = Field(default="2.0", max_length=16)
    started_at: Optional[str] = Field(default=None)
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class SchedulerBootstrapHeartbeatRequest(BaseModel):
    scheduler_id: str = Field(..., min_length=1, max_length=64)
    lease_id: str = Field(..., min_length=8, max_length=128)


class SchedulerInternalEnqueueRequest(BaseModel):
    zone_id: int = Field(..., ge=1, description="Zone ID")
    task_type: Literal[
        "irrigation",
        "lighting",
        "ventilation",
        "solution_change",
        "mist",
        "diagnostics",
    ] = Field(..., description="Abstract task type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task payload")
    scheduled_for: Optional[str] = Field(default=None, description="ISO datetime when task should be dispatched")
    expires_at: Optional[str] = Field(default=None, description="ISO datetime when enqueued task expires")
    correlation_id: Optional[str] = Field(default=None, max_length=128, description="Optional custom correlation_id")
    source: str = Field(default="automation-engine", max_length=64)


def _task_public_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "zone_id": task["zone_id"],
        "task_type": task["task_type"],
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "scheduled_for": task.get("scheduled_for"),
        "correlation_id": task.get("correlation_id"),
        "result": task.get("result"),
        "error": task.get("error"),
        "error_code": task.get("error_code"),
    }


def _new_scheduler_task_id() -> str:
    return f"st-{uuid4().hex}"


def _new_scheduler_lease_id() -> str:
    return f"lease-{uuid4().hex}"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _task_payload_fingerprint(req: SchedulerTaskRequest) -> str:
    raw = {
        "zone_id": req.zone_id,
        "task_type": req.task_type,
        "payload": req.payload or {},
        "scheduled_for": req.scheduled_for,
        "due_at": req.due_at,
        "expires_at": req.expires_at,
    }
    return hashlib.sha256(_canonical_json(raw).encode("utf-8")).hexdigest()


def _task_payload_matches(req: SchedulerTaskRequest, existing_task: Dict[str, Any], expected_fingerprint: str) -> bool:
    existing_fingerprint = existing_task.get("payload_fingerprint")
    if isinstance(existing_fingerprint, str) and existing_fingerprint:
        return existing_fingerprint == expected_fingerprint

    if int(existing_task.get("zone_id") or 0) != int(req.zone_id):
        return False
    if str(existing_task.get("task_type") or "").strip().lower() != str(req.task_type).strip().lower():
        return False
    if (existing_task.get("scheduled_for") or None) != (req.scheduled_for or None):
        return False
    return _canonical_json(existing_task.get("payload") or {}) == _canonical_json(req.payload or {})


def _is_scheduler_protocol_supported(protocol_version: Optional[str]) -> bool:
    version = str(protocol_version or "2.0").strip()
    return version.startswith("2.")


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    return parse_enqueue_iso_datetime(value)


async def _cleanup_scheduler_tasks_locked(now: datetime) -> None:
    to_delete = []
    threshold = now - timedelta(seconds=_SCHEDULER_TASK_TTL_SECONDS)
    for task_id, task in _scheduler_tasks.items():
        updated_at_raw = task.get("updated_at")
        try:
            updated_at = datetime.fromisoformat(str(updated_at_raw))
        except Exception:
            updated_at = now
        if updated_at < threshold:
            to_delete.append(task_id)
    for task_id in to_delete:
        _scheduler_tasks.pop(task_id, None)

    overflow = len(_scheduler_tasks) - _SCHEDULER_TASK_MAX_IN_MEMORY
    if overflow > 0:
        sortable = []
        for task_id, task in _scheduler_tasks.items():
            updated_at_raw = task.get("updated_at")
            try:
                updated_at = datetime.fromisoformat(str(updated_at_raw))
            except Exception:
                updated_at = now
            sortable.append((updated_at, task_id))
        sortable.sort(key=lambda item: item[0])
        for _, task_id in sortable[:overflow]:
            _scheduler_tasks.pop(task_id, None)


def _cleanup_bootstrap_leases_locked(now: datetime) -> None:
    stale_ids = []
    for scheduler_id, lease in _scheduler_bootstrap_leases.items():
        expires_at = lease.get("expires_at")
        if not isinstance(expires_at, datetime):
            stale_ids.append(scheduler_id)
            continue
        if expires_at <= now:
            stale_ids.append(scheduler_id)
    for scheduler_id in stale_ids:
        _scheduler_bootstrap_leases.pop(scheduler_id, None)


def _bootstrap_status() -> str:
    return "ready" if _command_bus is not None else "wait"


async def _load_scheduler_task_by_correlation_id(correlation_id: str) -> Optional[Dict[str, Any]]:
    threshold = datetime.utcnow() - timedelta(seconds=_SCHEDULER_DEDUPE_WINDOW_SEC)
    try:
        rows = await fetch(
            """
            SELECT details
            FROM scheduler_logs
            WHERE task_name LIKE 'ae_scheduler_task_st-%'
              AND details->>'correlation_id' = $1
              AND created_at >= $2
            ORDER BY created_at DESC
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


async def _create_scheduler_task(req: SchedulerTaskRequest) -> Tuple[Dict[str, Any], bool]:
    now_iso = datetime.utcnow().isoformat()
    payload_fingerprint = _task_payload_fingerprint(req)

    async with _scheduler_tasks_lock:
        await _cleanup_scheduler_tasks_locked(datetime.utcnow())

        existing_in_memory: Optional[Dict[str, Any]] = None
        for candidate in _scheduler_tasks.values():
            if candidate.get("correlation_id") == req.correlation_id:
                existing_in_memory = dict(candidate)
                break

        existing = existing_in_memory
        if existing is None:
            existing = await _load_scheduler_task_by_correlation_id(req.correlation_id)
            if existing is not None:
                _scheduler_tasks[str(existing["task_id"])] = dict(existing)

        if existing is not None:
            if not _task_payload_matches(req, existing, payload_fingerprint):
                raise HTTPException(status_code=409, detail="idempotency_payload_mismatch")
            return dict(existing), True
        task = {
            "task_id": _new_scheduler_task_id(),
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": "accepted",
            "payload": req.payload or {},
            "created_at": now_iso,
            "updated_at": now_iso,
            "scheduled_for": req.scheduled_for,
            "correlation_id": req.correlation_id,
            "payload_fingerprint": payload_fingerprint,
            "result": None,
            "error": None,
            "error_code": None,
        }
        _scheduler_tasks[task["task_id"]] = task
    await _persist_scheduler_task_snapshot(task)
    return task, False


async def _update_scheduler_task(
    *,
    task_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    async with _scheduler_tasks_lock:
        task = _scheduler_tasks.get(task_id)
        if not task:
            return
        task["status"] = status
        task["updated_at"] = datetime.utcnow().isoformat()
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error
        if error_code is not None:
            task["error_code"] = error_code
        snapshot = dict(task)
    await _persist_scheduler_task_snapshot(snapshot)


def _scheduler_task_log_name(task_id: str) -> str:
    return f"ae_scheduler_task_{task_id}"


async def _persist_scheduler_task_snapshot(task: Dict[str, Any]) -> None:
    try:
        await create_scheduler_log(
            _scheduler_task_log_name(task["task_id"]),
            str(task.get("status") or "unknown"),
            dict(task),
        )
    except Exception:
        logger.warning(
            "Failed to persist scheduler task snapshot: task_id=%s",
            task.get("task_id"),
            exc_info=True,
        )


async def _load_scheduler_task_snapshot(task_id: str) -> Optional[Dict[str, Any]]:
    try:
        rows = await fetch(
            """
            SELECT status, details, created_at
            FROM scheduler_logs
            WHERE task_name = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            _scheduler_task_log_name(task_id),
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


async def _execute_scheduler_task(task_id: str, req: SchedulerTaskRequest, trace_id: Optional[str]) -> None:
    if trace_id:
        set_trace_id(trace_id)

    command_bus = _command_bus
    if command_bus is None:
        await _update_scheduler_task(
            task_id=task_id,
            status="failed",
            error="command_bus_unavailable",
            error_code="command_bus_unavailable",
        )
        return

    await _update_scheduler_task(task_id=task_id, status="running")

    try:
        executor = SchedulerTaskExecutor(command_bus=command_bus, zone_service=_zone_service)
        result = await executor.execute(
            zone_id=req.zone_id,
            task_type=req.task_type,
            payload=req.payload or {},
            task_context={
                "task_id": task_id,
                "correlation_id": req.correlation_id,
                "scheduled_for": req.scheduled_for,
            },
        )
        success = bool(result.get("success"))
        await _update_scheduler_task(
            task_id=task_id,
            status="completed" if success else "failed",
            result=result,
            error=None if success else str(result.get("error") or "task_execution_failed"),
            error_code=None if success else str(result.get("error_code") or "task_execution_failed"),
        )
    except Exception as exc:
        logger.error(
            "Scheduler task execution failed: task_id=%s zone_id=%s task_type=%s error=%s",
            task_id,
            req.zone_id,
            req.task_type,
            exc,
            exc_info=True,
        )
        await _update_scheduler_task(
            task_id=task_id,
            status="failed",
            error=str(exc),
            error_code="execution_exception",
        )
        await send_infra_exception_alert(
            error=exc,
            code="infra_unknown_error",
            alert_type="Automation Scheduler Task Execution Error",
            severity="error",
            zone_id=req.zone_id,
            service="automation-engine",
            component="api:/scheduler/task",
            error_type=type(exc).__name__,
            details={"task_id": task_id, "task_type": req.task_type},
        )


async def _validate_scheduler_dispatch_lease(request: Request) -> None:
    if not _SCHEDULER_BOOTSTRAP_ENFORCE:
        return

    scheduler_id = str(request.headers.get("x-scheduler-id") or "").strip()
    lease_id = str(request.headers.get("x-scheduler-lease-id") or "").strip()
    if not scheduler_id or not lease_id:
        raise HTTPException(status_code=403, detail="scheduler_bootstrap_required")

    now = datetime.utcnow()
    async with _scheduler_bootstrap_lock:
        _cleanup_bootstrap_leases_locked(now)
        lease = _scheduler_bootstrap_leases.get(scheduler_id)
        if not lease:
            raise HTTPException(status_code=409, detail="scheduler_lease_not_found")
        if lease.get("lease_id") != lease_id:
            raise HTTPException(status_code=409, detail="scheduler_lease_mismatch")
        expires_at = lease.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= now:
            _scheduler_bootstrap_leases.pop(scheduler_id, None)
            raise HTTPException(status_code=409, detail="scheduler_lease_expired")


@app.post("/scheduler/bootstrap")
async def scheduler_bootstrap(req: SchedulerBootstrapRequest = Body(...)):
    now = datetime.utcnow()
    bootstrap_status = _bootstrap_status()
    if not _is_scheduler_protocol_supported(req.protocol_version):
        bootstrap_status = "deny"

    response_payload: Dict[str, Any] = {
        "bootstrap_status": bootstrap_status,
        "lease_ttl_sec": _SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
        "poll_interval_sec": _SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
        "task_timeout_sec": _SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC,
        "dedupe_window_sec": _SCHEDULER_DEDUPE_WINDOW_SEC,
        "server_time": now.isoformat(),
    }

    async with _scheduler_bootstrap_lock:
        _cleanup_bootstrap_leases_locked(now)
        if bootstrap_status == "ready":
            current = _scheduler_bootstrap_leases.get(req.scheduler_id)
            lease_id = str(current.get("lease_id")) if isinstance(current, dict) and current.get("lease_id") else _new_scheduler_lease_id()
            _scheduler_bootstrap_leases[req.scheduler_id] = {
                "lease_id": lease_id,
                "scheduler_version": req.scheduler_version,
                "protocol_version": req.protocol_version,
                "created_at": current.get("created_at") if isinstance(current, dict) and current.get("created_at") else now,
                "last_heartbeat_at": now,
                "expires_at": now + timedelta(seconds=_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC),
            }
            response_payload["lease_id"] = lease_id
        else:
            _scheduler_bootstrap_leases.pop(req.scheduler_id, None)

    await create_scheduler_log(
        f"ae_scheduler_bootstrap_{req.scheduler_id}",
        bootstrap_status,
        {
            "scheduler_id": req.scheduler_id,
            "scheduler_version": req.scheduler_version,
            "protocol_version": req.protocol_version,
            "started_at": req.started_at,
            "bootstrap_status": bootstrap_status,
            "response": response_payload,
        },
    )
    return {"status": "ok", "data": response_payload}


@app.post("/scheduler/bootstrap/heartbeat")
async def scheduler_bootstrap_heartbeat(req: SchedulerBootstrapHeartbeatRequest = Body(...)):
    now = datetime.utcnow()
    async with _scheduler_bootstrap_lock:
        _cleanup_bootstrap_leases_locked(now)
        lease = _scheduler_bootstrap_leases.get(req.scheduler_id)
        if lease is None or str(lease.get("lease_id") or "") != req.lease_id:
            return {
                "status": "ok",
                "data": {
                    "bootstrap_status": "wait",
                    "reason": "lease_not_found",
                    "poll_interval_sec": _SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
                    "server_time": now.isoformat(),
                },
            }
        if _bootstrap_status() != "ready":
            _scheduler_bootstrap_leases.pop(req.scheduler_id, None)
            return {
                "status": "ok",
                "data": {
                    "bootstrap_status": "wait",
                    "reason": "automation_not_ready",
                    "poll_interval_sec": _SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
                    "server_time": now.isoformat(),
                },
            }

        lease["last_heartbeat_at"] = now
        lease["expires_at"] = now + timedelta(seconds=_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC)
        response_payload = {
            "bootstrap_status": "ready",
            "lease_id": req.lease_id,
            "lease_ttl_sec": _SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
            "lease_expires_at": lease["expires_at"].isoformat(),
            "server_time": now.isoformat(),
        }

    await create_scheduler_log(
        f"ae_scheduler_bootstrap_{req.scheduler_id}",
        "heartbeat",
        {
            "scheduler_id": req.scheduler_id,
            "lease_id": req.lease_id,
            "bootstrap_status": response_payload["bootstrap_status"],
            "response": response_payload,
        },
    )
    return {"status": "ok", "data": response_payload}


@app.post("/scheduler/internal/enqueue")
async def scheduler_internal_enqueue(req: SchedulerInternalEnqueueRequest = Body(...)):
    await _validate_scheduler_zone(req.zone_id)
    if req.task_type not in _SCHEDULER_TASK_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type: {req.task_type}")

    try:
        enqueue_result = await enqueue_internal_scheduler_task(
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


@app.post("/scheduler/task")
async def scheduler_task(request: Request, req: SchedulerTaskRequest = Body(...)):
    """
    Абстрактный task-level endpoint для scheduler.
    Scheduler не отправляет device-level команды, а публикует тип задачи.
    """
    if not _command_bus:
        raise HTTPException(status_code=503, detail="CommandBus not initialized")

    if req.task_type not in _SCHEDULER_TASK_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported task_type: {req.task_type}")

    await _validate_scheduler_dispatch_lease(request)
    await _validate_scheduler_zone(req.zone_id)

    task, is_duplicate = await _create_scheduler_task(req)
    if not is_duplicate:
        await create_zone_event(
            req.zone_id,
            "SCHEDULE_TASK_ACCEPTED",
            {
                "task_id": task["task_id"],
                "task_type": req.task_type,
                "scheduled_for": req.scheduled_for,
                "correlation_id": req.correlation_id,
            },
        )

        trace_id = get_trace_id()
        asyncio.create_task(_execute_scheduler_task(task["task_id"], req, trace_id))

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


@app.get("/scheduler/task/{task_id}")
async def scheduler_task_status(task_id: str):
    """Статус абстрактной задачи scheduler."""
    async with _scheduler_tasks_lock:
        await _cleanup_scheduler_tasks_locked(datetime.utcnow())
        task = _scheduler_tasks.get(task_id)
    if task is None:
        persisted = await _load_scheduler_task_snapshot(task_id)
        if persisted is None:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        async with _scheduler_tasks_lock:
            _scheduler_tasks[task_id] = persisted
        task = persisted
    payload = _task_public_payload(task)

    return {"status": "ok", "data": payload}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "automation-engine"}


# Test hooks (только в test mode)
class TestHookRequest(BaseModel):
    """Request model для test hooks."""
    zone_id: int = Field(..., ge=1, description="Zone ID")
    controller: Optional[str] = Field(None, description="Controller name (climate, ph, ec, irrigation, etc.)")
    action: str = Field(..., description="Action: inject_error, clear_error, reset_backoff, set_state, publish_command")
    error_type: Optional[str] = Field(None, description="Error type for inject_error")
    state: Optional[Dict[str, Any]] = Field(None, description="State override for set_state")
    command: Optional[Dict[str, Any]] = Field(
        None,
        description="Command payload for publish_command: {node_uid, channel, cmd, params?, cmd_id?}",
    )


def _parse_optional_datetime(value: Any, field_name: str) -> Optional[datetime]:
    """Нормализовать datetime-поле override из JSON (None|ISO string|datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return None
        # Поддержка ISO вида 2099-01-01T00:00:00Z
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            return datetime.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid datetime format for '{field_name}': {value}",
            ) from exc
    raise HTTPException(
        status_code=400,
        detail=f"Field '{field_name}' must be null or ISO datetime string",
    )


def _normalize_state_override(state: Dict[str, Any]) -> Dict[str, Any]:
    """Привести override состояния зоны к безопасному внутреннему формату."""
    error_streak_raw = state.get("error_streak", 0)
    try:
        error_streak = int(error_streak_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Field 'error_streak' must be integer, got: {error_streak_raw}",
        ) from exc
    if error_streak < 0:
        raise HTTPException(status_code=400, detail="Field 'error_streak' must be >= 0")

    return {
        "error_streak": error_streak,
        "next_allowed_run_at": _parse_optional_datetime(state.get("next_allowed_run_at"), "next_allowed_run_at"),
        "last_backoff_reported_until": _parse_optional_datetime(state.get("last_backoff_reported_until"), "last_backoff_reported_until"),
        "degraded_alert_active": bool(state.get("degraded_alert_active", False)),
        "last_missing_targets_report_at": _parse_optional_datetime(state.get("last_missing_targets_report_at"), "last_missing_targets_report_at"),
    }


@app.post("/test/hook")
async def test_hook(req: TestHookRequest = Body(...)):
    """
    Test hook для детерминированных ошибок и управления состоянием.
    Доступен только если AE_TEST_MODE=1.
    """
    if not _test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled (AE_TEST_MODE=0)")
    
    zone_id = req.zone_id
    controller = req.controller
    action = req.action
    
    if action == "inject_error":
        if not controller or not req.error_type:
            raise HTTPException(status_code=400, detail="inject_error requires controller and error_type")
        
        if zone_id not in _test_hooks:
            _test_hooks[zone_id] = {}
        _test_hooks[zone_id][controller] = {"error_type": req.error_type, "active": True}
        
        logger.info(f"[TEST_HOOK] Injected error for zone {zone_id}, controller {controller}: {req.error_type}")
        return {"status": "ok", "message": f"Error injected for zone {zone_id}, controller {controller}"}
    
    elif action == "clear_error":
        if controller:
            if zone_id in _test_hooks and controller in _test_hooks[zone_id]:
                del _test_hooks[zone_id][controller]
                if not _test_hooks[zone_id]:
                    del _test_hooks[zone_id]
        else:
            # Очистить все ошибки для зоны
            if zone_id in _test_hooks:
                del _test_hooks[zone_id]
        
        logger.info(f"[TEST_HOOK] Cleared errors for zone {zone_id}, controller {controller or 'all'}")
        return {"status": "ok", "message": f"Errors cleared for zone {zone_id}"}
    
    elif action == "reset_backoff":
        # Сброс backoff состояния для зоны
        _zone_states_override[zone_id] = _normalize_state_override({"error_streak": 0})
        
        logger.info(f"[TEST_HOOK] Reset backoff for zone {zone_id}")
        return {"status": "ok", "message": f"Backoff reset for zone {zone_id}"}
    
    elif action == "set_state":
        if not req.state:
            raise HTTPException(status_code=400, detail="set_state requires state")
        
        normalized_state = _normalize_state_override(req.state)
        _zone_states_override[zone_id] = normalized_state
        logger.info(f"[TEST_HOOK] Set state for zone {zone_id}: {normalized_state}")
        return {"status": "ok", "message": f"State set for zone {zone_id}"}

    elif action == "publish_command":
        if not isinstance(req.command, dict):
            raise HTTPException(
                status_code=400,
                detail="publish_command requires command payload",
            )

        node_uid = req.command.get("node_uid")
        channel = req.command.get("channel", "default")
        cmd = req.command.get("cmd")
        params = req.command.get("params") or {}
        cmd_id = req.command.get("cmd_id")

        if not isinstance(node_uid, str) or not node_uid.strip():
            raise HTTPException(
                status_code=400,
                detail="publish_command requires non-empty command.node_uid",
            )
        if not isinstance(channel, str) or not channel.strip():
            raise HTTPException(
                status_code=400,
                detail="publish_command requires non-empty command.channel",
            )
        if not isinstance(cmd, str) or not cmd.strip():
            raise HTTPException(
                status_code=400,
                detail="publish_command requires non-empty command.cmd",
            )
        if not isinstance(params, dict):
            raise HTTPException(
                status_code=400,
                detail="publish_command requires object command.params",
            )
        if cmd_id is not None and not isinstance(cmd_id, str):
            raise HTTPException(
                status_code=400,
                detail="publish_command requires string command.cmd_id",
            )

        command_bus = _command_bus
        temporary_command_bus: Optional[CommandBus] = None
        if command_bus is None:
            history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
            history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
            gh_uid = _gh_uid or os.getenv("GREENHOUSE_UID", "gh-test-1")
            temporary_command_bus = CommandBus(
                mqtt=None,
                gh_uid=gh_uid,
                history_logger_url=history_logger_url,
                history_logger_token=history_logger_token,
                enforce_node_zone_assignment=True,
            )
            try:
                await temporary_command_bus.start()
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"CommandBus init failed: {exc}") from exc
            command_bus = temporary_command_bus
            logger.info("[TEST_HOOK] Temporary CommandBus initialized for publish_command")

        try:
            published = await command_bus.publish_command(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                params=params,
                cmd_id=cmd_id,
            )
        finally:
            if temporary_command_bus is not None:
                try:
                    await temporary_command_bus.stop()
                except Exception:
                    logger.warning("[TEST_HOOK] Failed to stop temporary CommandBus", exc_info=True)
        logger.info(
            "[TEST_HOOK] publish_command for zone %s: cmd=%s node_uid=%s channel=%s published=%s",
            zone_id,
            cmd,
            node_uid,
            channel,
            published,
        )
        return {
            "status": "ok",
            "data": {
                "published": bool(published),
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": cmd_id,
            },
        }
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.get("/test/hook/{zone_id}")
async def get_test_hook(zone_id: int):
    """Получить текущее состояние test hooks для зоны."""
    if not _test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled")
    
    hooks = _test_hooks.get(zone_id, {})
    state = _zone_states_override.get(zone_id, {})
    
    return {
        "status": "ok",
        "data": {
            "zone_id": zone_id,
            "hooks": hooks,
            "state_override": state
        }
    }


def get_test_hook_for_zone(zone_id: int, controller: str) -> Optional[Dict[str, Any]]:
    """Получить test hook для зоны и контроллера (используется в ZoneAutomationService)."""
    if not _test_mode:
        return None
    if zone_id in _test_hooks and controller in _test_hooks[zone_id]:
        return _test_hooks[zone_id][controller]
    return None


def get_zone_state_override(zone_id: int) -> Optional[Dict[str, Any]]:
    """Получить override состояния для зоны (используется в ZoneAutomationService)."""
    if not _test_mode:
        return None
    return _zone_states_override.get(zone_id)
