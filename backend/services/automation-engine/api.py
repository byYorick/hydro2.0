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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_client import Gauge
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
_AE_TASK_RECOVERY_ENABLED = os.getenv("AE_TASK_RECOVERY_ENABLED", "1") == "1"
_AE_TASK_RECOVERY_SCAN_LIMIT = max(10, int(os.getenv("AE_TASK_RECOVERY_SCAN_LIMIT", "500")))
TASK_RECOVERY_SUCCESS_RATE = Gauge(
    "task_recovery_success_rate",
    "Share of startup recovery tasks finalized successfully",
)
COMMAND_EFFECT_CONFIRM_RATE = Gauge(
    "command_effect_confirm_rate",
    "Share of commands confirmed by node DONE for closed-loop scheduler tasks",
    ["task_type"],
)
_command_effect_totals: Dict[str, int] = {}
_command_effect_confirmed_totals: Dict[str, int] = {}

ERR_TASK_EXPIRED = "task_expired"
ERR_TASK_DUE_DEADLINE_EXCEEDED = "task_due_deadline_exceeded"
ERR_COMMAND_BUS_UNAVAILABLE = "command_bus_unavailable"
ERR_TASK_EXECUTION_FAILED = "task_execution_failed"
ERR_EXECUTION_EXCEPTION = "execution_exception"

# Test hooks для детерминированных ошибок (только в test mode)
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}  # zone_id -> {controller: error_type, ...}
_zone_states_override: Dict[int, Dict[str, Any]] = {}  # zone_id -> {error_streak: int, next_allowed_run_at: datetime}


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid
    _command_bus = command_bus
    _gh_uid = gh_uid


def _update_command_effect_confirm_rate(task_type: str, result: Dict[str, Any]) -> None:
    normalized_task_type = str(task_type or "unknown")

    commands_total_raw = result.get("commands_total")
    commands_confirmed_raw = result.get("commands_effect_confirmed")
    bool_confirmed = result.get("command_effect_confirmed")

    try:
        commands_total = int(commands_total_raw) if commands_total_raw is not None else 0
    except (TypeError, ValueError):
        commands_total = 0

    if commands_total <= 0:
        return

    try:
        commands_confirmed = int(commands_confirmed_raw) if commands_confirmed_raw is not None else None
    except (TypeError, ValueError):
        commands_confirmed = None

    if commands_confirmed is None:
        if isinstance(bool_confirmed, bool):
            commands_confirmed = commands_total if bool_confirmed else 0
        else:
            commands_confirmed = 0

    total = _command_effect_totals.get(normalized_task_type, 0) + commands_total
    confirmed = _command_effect_confirmed_totals.get(normalized_task_type, 0) + max(0, min(commands_confirmed, commands_total))
    _command_effect_totals[normalized_task_type] = total
    _command_effect_confirmed_totals[normalized_task_type] = confirmed
    COMMAND_EFFECT_CONFIRM_RATE.labels(task_type=normalized_task_type).set(confirmed / max(total, 1))


def set_zone_service(zone_service: Any) -> None:
    """Установить ZoneAutomationService для выполнения scheduler-task diagnostics."""
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
    due_at: str = Field(..., description="ISO datetime when task must be started")
    expires_at: str = Field(..., description="ISO datetime when task should be rejected")
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
        "due_at": task.get("due_at"),
        "expires_at": task.get("expires_at"),
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
    if (existing_task.get("due_at") or None) != (req.due_at or None):
        return False
    if (existing_task.get("expires_at") or None) != (req.expires_at or None):
        return False
    return _canonical_json(existing_task.get("payload") or {}) == _canonical_json(req.payload or {})


def _is_scheduler_protocol_supported(protocol_version: Optional[str]) -> bool:
    version = str(protocol_version or "2.0").strip()
    return version.startswith("2.")


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    return parse_enqueue_iso_datetime(value)


def _require_iso_datetime(value: Optional[str], field_name: str) -> datetime:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        raise HTTPException(status_code=422, detail=f"{field_name}_required_or_invalid")
    return parsed


def _build_deadline_terminal_result(
    *,
    status: str,
    now: datetime,
    due_at: datetime,
    expires_at: datetime,
) -> Dict[str, Any]:
    if status == "expired":
        reason_code = ERR_TASK_EXPIRED
        reason = "Задача получена после expires_at и не может быть исполнена"
        error_code = ERR_TASK_EXPIRED
    else:
        reason_code = ERR_TASK_DUE_DEADLINE_EXCEEDED
        reason = "Задача получена позже due_at и отклонена без запуска исполнения"
        error_code = ERR_TASK_DUE_DEADLINE_EXCEEDED

    return {
        "success": False,
        "mode": "deadline_rejected",
        "action_required": False,
        "decision": "skip",
        "reason_code": reason_code,
        "reason": reason,
        "received_at": now.isoformat(),
        "due_at": due_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "error": error_code,
        "error_code": error_code,
    }


def _build_execution_terminal_result(
    *,
    error_code: str,
    reason: str,
    mode: str,
    action_required: bool = True,
    decision: str = "fail",
    reason_code: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": False,
        "mode": mode,
        "action_required": action_required,
        "decision": decision,
        "reason_code": reason_code or error_code,
        "reason": reason,
        "error": error_code,
        "error_code": error_code,
    }
    if isinstance(extra, dict):
        result.update(extra)
    return result


def _normalize_failed_execution_result(result: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(result) if isinstance(result, dict) else {}
    error_code_raw = normalized.get("error_code") or normalized.get("error")
    error_code = str(error_code_raw or ERR_TASK_EXECUTION_FAILED)

    action_required = normalized.get("action_required")
    if not isinstance(action_required, bool):
        action_required = True

    decision = normalized.get("decision")
    if not isinstance(decision, str) or not decision.strip():
        decision = "fail"
    else:
        decision = decision.strip().lower()
        if decision == "execute":
            decision = "run"
        if decision == "run":
            decision = "fail"
        elif decision not in {"skip", "retry", "fail"}:
            decision = "fail"

    reason_code = normalized.get("reason_code")
    if not isinstance(reason_code, str) or not reason_code.strip():
        reason_code = error_code

    reason = normalized.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "Задача завершилась ошибкой в automation-engine"

    error = normalized.get("error")
    if not isinstance(error, str) or not error.strip():
        error = error_code

    normalized["error"] = error
    normalized["error_code"] = error_code
    normalized["action_required"] = action_required
    normalized["decision"] = decision
    normalized["reason_code"] = reason_code
    normalized["reason"] = reason
    normalized.setdefault("mode", "execution_failed")
    normalized["success"] = False
    return normalized


def _normalize_cleanup_timestamp(raw_value: Any, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except Exception:
        return fallback
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def _cleanup_scheduler_tasks_locked(now: datetime) -> None:
    to_delete = []
    threshold = now - timedelta(seconds=_SCHEDULER_TASK_TTL_SECONDS)
    for task_id, task in _scheduler_tasks.items():
        updated_at = _normalize_cleanup_timestamp(task.get("updated_at"), now)
        if updated_at < threshold:
            to_delete.append(task_id)
    for task_id in to_delete:
        _scheduler_tasks.pop(task_id, None)

    overflow = len(_scheduler_tasks) - _SCHEDULER_TASK_MAX_IN_MEMORY
    if overflow > 0:
        sortable = []
        for task_id, task in _scheduler_tasks.items():
            updated_at = _normalize_cleanup_timestamp(task.get("updated_at"), now)
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


async def _scheduler_bootstrap_state() -> Tuple[str, str]:
    command_bus_ready, command_bus_reason = _is_command_bus_ready()
    if not command_bus_ready:
        return "wait", command_bus_reason

    db_ready, db_reason = await _is_db_ready()
    if not db_ready:
        return "wait", db_reason

    bootstrap_store_ready, bootstrap_store_reason = _is_bootstrap_store_ready()
    if not bootstrap_store_ready:
        return "wait", bootstrap_store_reason

    return "ready", "ok"


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


async def _create_scheduler_task(
    req: SchedulerTaskRequest,
    *,
    initial_status: str = "accepted",
    initial_result: Optional[Dict[str, Any]] = None,
    initial_error: Optional[str] = None,
    initial_error_code: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
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
            ORDER BY created_at DESC, id DESC
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


def _task_id_from_log_name(task_name: Any) -> Optional[str]:
    if not isinstance(task_name, str):
        return None
    prefix = "ae_scheduler_task_"
    if not task_name.startswith(prefix):
        return None
    task_id = task_name[len(prefix):].strip()
    return task_id or None


async def _recover_inflight_scheduler_tasks() -> Dict[str, int]:
    if not _AE_TASK_RECOVERY_ENABLED:
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    try:
        rows = await fetch(
            """
            WITH recent_logs AS (
                SELECT id, task_name, status, details, created_at
                FROM scheduler_logs
                WHERE task_name LIKE 'ae_scheduler_task_st-%'
                ORDER BY created_at DESC, id DESC
                LIMIT $1
            )
            SELECT DISTINCT ON (task_name)
                task_name, status, details, created_at
            FROM recent_logs
            ORDER BY task_name, created_at DESC, id DESC
            """,
            _AE_TASK_RECOVERY_SCAN_LIMIT,
        )
    except Exception:
        logger.warning("Scheduler task recovery scan failed", exc_info=True)
        return {"scanned": 0, "inflight": 0, "recovered": 0}

    scanned = len(rows)
    inflight = 0
    recovered = 0
    now_iso = datetime.utcnow().isoformat()

    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        raw_status = details.get("status") if isinstance(details, dict) else None
        if not raw_status:
            raw_status = row.get("status")
        status = str(raw_status or "").strip().lower()
        if status not in {"accepted", "running"}:
            continue
        inflight += 1

        task_id = details.get("task_id") if isinstance(details, dict) else None
        if not task_id:
            task_id = _task_id_from_log_name(row.get("task_name"))
        zone_id = details.get("zone_id") if isinstance(details, dict) else None
        task_type = details.get("task_type") if isinstance(details, dict) else None
        if not task_id or not zone_id or not task_type:
            continue

        recovery_result = _build_execution_terminal_result(
            error_code="task_recovered_after_restart",
            reason="Automation-engine перезапущен: in-flight задача финализирована recovery-политикой",
            mode="startup_recovery_finalize",
            action_required=True,
            decision="fail",
            reason_code="task_recovered_after_restart",
        )

        recovered_task = {
            "task_id": task_id,
            "zone_id": zone_id,
            "task_type": task_type,
            "status": "failed",
            "created_at": details.get("created_at") if isinstance(details, dict) else None,
            "updated_at": now_iso,
            "scheduled_for": details.get("scheduled_for") if isinstance(details, dict) else None,
            "due_at": details.get("due_at") if isinstance(details, dict) else None,
            "expires_at": details.get("expires_at") if isinstance(details, dict) else None,
            "correlation_id": details.get("correlation_id") if isinstance(details, dict) else None,
            "payload_fingerprint": details.get("payload_fingerprint") if isinstance(details, dict) else None,
            "payload": details.get("payload") if isinstance(details.get("payload"), dict) else {},
            "result": recovery_result,
            "error": "task_recovered_after_restart",
            "error_code": "task_recovered_after_restart",
        }

        if not recovered_task["created_at"]:
            created_at = row.get("created_at")
            recovered_task["created_at"] = created_at.isoformat() if hasattr(created_at, "isoformat") else now_iso

        async with _scheduler_tasks_lock:
            _scheduler_tasks[task_id] = recovered_task

        try:
            await _persist_scheduler_task_snapshot(recovered_task)
        except Exception as exc:
            logger.warning(
                "Failed to persist recovered scheduler task snapshot: task_id=%s error=%s",
                task_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=exc,
                code="infra_scheduler_task_recovery_persist_failed",
                alert_type="Scheduler Task Recovery Persist Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )

        try:
            await create_zone_event(
                int(zone_id),
                "SCHEDULE_TASK_FAILED",
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "status": "failed",
                    "error_code": "task_recovered_after_restart",
                    "source": "automation_engine_startup_recovery",
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish recovery zone event: task_id=%s zone_id=%s error=%s",
                task_id,
                zone_id,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=exc,
                code="infra_scheduler_task_recovery_event_failed",
                alert_type="Scheduler Task Recovery Event Failed",
                severity="error",
                zone_id=int(zone_id),
                service="automation-engine",
                component="scheduler_task_recovery",
                error_type=type(exc).__name__,
                details={"task_id": task_id, "task_type": task_type},
            )
        recovered += 1

    if inflight <= 0:
        TASK_RECOVERY_SUCCESS_RATE.set(1.0)
    else:
        TASK_RECOVERY_SUCCESS_RATE.set(recovered / inflight)

    return {"scanned": scanned, "inflight": inflight, "recovered": recovered}


async def _execute_scheduler_task(task_id: str, req: SchedulerTaskRequest, trace_id: Optional[str]) -> None:
    if trace_id:
        set_trace_id(trace_id)

    command_bus = _command_bus
    if command_bus is None:
        failure_result = _build_execution_terminal_result(
            error_code=ERR_COMMAND_BUS_UNAVAILABLE,
            reason="CommandBus недоступен, задача не может быть исполнена",
            mode="dispatch_unavailable",
        )
        await _update_scheduler_task(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
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
        result = result if isinstance(result, dict) else {}
        _update_command_effect_confirm_rate(req.task_type, result)
        success = bool(result.get("success"))
        failed_result = _normalize_failed_execution_result(result)
        await _update_scheduler_task(
            task_id=task_id,
            status="completed" if success else "failed",
            result=result if success else failed_result,
            error=None if success else str(failed_result["error"]),
            error_code=None if success else str(failed_result["error_code"]),
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
        failure_result = _build_execution_terminal_result(
            error_code=ERR_EXECUTION_EXCEPTION,
            reason="Во время исполнения scheduler-task произошло необработанное исключение",
            mode="execution_exception",
            extra={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        await _update_scheduler_task(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
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
    bootstrap_status, readiness_reason = await _scheduler_bootstrap_state()
    if not _is_scheduler_protocol_supported(req.protocol_version):
        bootstrap_status = "deny"
        readiness_reason = "protocol_not_supported"

    response_payload: Dict[str, Any] = {
        "bootstrap_status": bootstrap_status,
        "lease_ttl_sec": _SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
        "poll_interval_sec": _SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
        "task_timeout_sec": _SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC,
        "dedupe_window_sec": _SCHEDULER_DEDUPE_WINDOW_SEC,
        "server_time": now.isoformat(),
    }
    if bootstrap_status != "ready":
        response_payload["reason"] = "automation_not_ready" if bootstrap_status == "wait" else readiness_reason
        response_payload["readiness_reason"] = readiness_reason

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
        bootstrap_status, readiness_reason = await _scheduler_bootstrap_state()
        if bootstrap_status != "ready":
            _scheduler_bootstrap_leases.pop(req.scheduler_id, None)
            return {
                "status": "ok",
                "data": {
                    "bootstrap_status": "wait",
                    "reason": "automation_not_ready",
                    "readiness_reason": readiness_reason,
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

    scheduled_for_dt: Optional[datetime] = None
    if req.scheduled_for:
        scheduled_for_dt = _parse_iso_datetime(req.scheduled_for)
        if scheduled_for_dt is None:
            raise HTTPException(status_code=422, detail="scheduled_for_invalid")

    due_at_dt = _require_iso_datetime(req.due_at, "due_at")
    expires_at_dt = _require_iso_datetime(req.expires_at, "expires_at")
    if expires_at_dt <= due_at_dt:
        raise HTTPException(status_code=422, detail="expires_at_must_be_after_due_at")
    if scheduled_for_dt is not None and due_at_dt < scheduled_for_dt:
        raise HTTPException(status_code=422, detail="due_at_must_be_gte_scheduled_for")

    now = datetime.utcnow()
    terminal_status: Optional[str] = None
    terminal_result: Optional[Dict[str, Any]] = None
    if now > expires_at_dt:
        terminal_status = "expired"
        terminal_result = _build_deadline_terminal_result(
            status=terminal_status,
            now=now,
            due_at=due_at_dt,
            expires_at=expires_at_dt,
        )
    elif now > due_at_dt:
        terminal_status = "rejected"
        terminal_result = _build_deadline_terminal_result(
            status=terminal_status,
            now=now,
            due_at=due_at_dt,
            expires_at=expires_at_dt,
        )

    task, is_duplicate = await _create_scheduler_task(
        req,
        initial_status=terminal_status or "accepted",
        initial_result=terminal_result if terminal_status else None,
        initial_error=str(terminal_result.get("error")) if terminal_status and terminal_result else None,
        initial_error_code=str(terminal_result.get("error_code")) if terminal_status and terminal_result else None,
    )
    if not is_duplicate:
        if terminal_status and terminal_result:
            await create_zone_event(
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
            await create_zone_event(
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


@app.on_event("startup")
async def run_scheduler_task_recovery_on_startup() -> None:
    summary = await _recover_inflight_scheduler_tasks()
    if summary["recovered"] > 0:
        logger.warning(
            "Recovered in-flight scheduler tasks after restart: recovered=%s scanned=%s",
            summary["recovered"],
            summary["scanned"],
        )


def _is_command_bus_ready() -> Tuple[bool, str]:
    if _command_bus is None:
        return False, "command_bus_unavailable"
    return True, "ok"


def _is_bootstrap_store_ready() -> Tuple[bool, str]:
    if not isinstance(_scheduler_bootstrap_leases, dict):
        return False, "lease_store_invalid"
    if _scheduler_bootstrap_lock is None:
        return False, "lease_lock_missing"
    return True, "ok"


async def _is_db_ready() -> Tuple[bool, str]:
    try:
        # Lightweight readiness probe for DB transport path used by API.
        await fetch("SELECT 1 AS ready")
        return True, "ok"
    except Exception as exc:
        logger.warning("Readiness DB probe failed: %s", exc, exc_info=True)
        return False, type(exc).__name__


async def _readiness_payload() -> Dict[str, Any]:
    command_bus_ready, command_bus_reason = _is_command_bus_ready()
    db_ready, db_reason = await _is_db_ready()
    bootstrap_store_ready, bootstrap_store_reason = _is_bootstrap_store_ready()

    ready = command_bus_ready and db_ready and bootstrap_store_ready
    return {
        "status": "ok" if ready else "degraded",
        "service": "automation-engine",
        "ready": ready,
        "checks": {
            "command_bus": {"ok": command_bus_ready, "reason": command_bus_reason},
            "db": {"ok": db_ready, "reason": db_reason},
            "bootstrap_store": {"ok": bootstrap_store_ready, "reason": bootstrap_store_reason},
        },
    }


@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": "automation-engine"}


@app.get("/health/ready")
async def health_ready():
    payload = await _readiness_payload()
    if payload["ready"]:
        return payload
    return JSONResponse(status_code=503, content=payload)


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
