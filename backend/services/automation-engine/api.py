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
from typing import Optional, Dict, Any, Literal, Tuple, Coroutine

from infrastructure import CommandBus
from infrastructure.workflow_state_store import WorkflowStateStore
from common.infra_alerts import send_infra_exception_alert, send_infra_alert
from common.db import fetch, create_scheduler_log, create_zone_event
from common.trace_context import extract_trace_id_from_headers
from utils.logging_context import set_trace_id, get_trace_id
from scheduler_task_executor import SchedulerTaskExecutor
from scheduler_internal_enqueue import (
    SUPPORTED_SCHEDULER_TASK_TYPES,
    enqueue_internal_scheduler_task,
    parse_iso_datetime as parse_enqueue_iso_datetime,
)
from application.api_automation_state import (
    build_timeline_label as policy_build_timeline_label,
    derive_active_processes as policy_derive_active_processes,
    derive_automation_state as policy_derive_automation_state,
    estimate_completion_seconds as policy_estimate_completion_seconds,
    estimate_progress_percent as policy_estimate_progress_percent,
    extract_timeline_reason as policy_extract_timeline_reason,
    resolve_state_started_at as policy_resolve_state_started_at,
)
from application.api_payload_parsing import (
    coerce_datetime as policy_coerce_datetime,
    extract_topology as policy_extract_topology,
    extract_workflow as policy_extract_workflow,
    to_optional_float as policy_to_optional_float,
    to_optional_int as policy_to_optional_int,
)
from application.api_task_snapshot import (
    is_task_active as policy_is_task_active,
    pick_preferred_zone_task as policy_pick_preferred_zone_task,
    sanitize_scheduler_task_snapshot as policy_sanitize_scheduler_task_snapshot,
    task_sort_key as policy_task_sort_key,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Automation Engine API")


def _env_true(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


_APP_ENV = str(os.getenv("APP_ENV", "local")).strip().lower()
_AE_VERBOSE_HTTP_LOGGING = _env_true(
    "AE_DEV_VERBOSE_HTTP_LOGGING",
    "1" if _APP_ENV in {"local", "dev", "development"} else "0",
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = extract_trace_id_from_headers(request.headers)
    if trace_id:
        set_trace_id(trace_id)
    else:
        trace_id = set_trace_id()
    request_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = max(0.0, (datetime.now(timezone.utc).replace(tzinfo=None) - request_started_at).total_seconds() * 1000.0)
        logger.error(
            "Unhandled API exception: method=%s path=%s duration_ms=%.2f error=%s",
            request.method,
            request.url.path,
            duration_ms,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )
        try:
            await send_infra_exception_alert(
                error=exc,
                code="infra_automation_api_unhandled_exception",
                alert_type="Automation API Unhandled Exception",
                severity="error",
                zone_id=None,
                service="automation-engine",
                component=f"api:{request.url.path}",
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "trace_id": trace_id,
                },
            )
        except Exception as alert_exc:
            logger.warning(
                "Failed to send infra alert for unhandled API exception: %s",
                alert_exc,
                exc_info=True,
            )
        raise

    duration_ms = max(0.0, (datetime.now(timezone.utc).replace(tzinfo=None) - request_started_at).total_seconds() * 1000.0)
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id

    if _AE_VERBOSE_HTTP_LOGGING or response.status_code >= 500:
        log_level = logging.ERROR if response.status_code >= 500 else logging.DEBUG
        logger.log(
            log_level,
            "API request completed: method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"trace_id": trace_id},
        )

    if response.status_code >= 500:
        try:
            await send_infra_alert(
                code="infra_automation_api_http_5xx",
                alert_type="Automation API HTTP 5xx",
                message=(
                    f"Automation API вернул HTTP {response.status_code} "
                    f"для {request.method} {request.url.path}"
                ),
                severity="error",
                zone_id=None,
                service="automation-engine",
                component=f"api:{request.url.path}",
                error_type=f"http_{response.status_code}",
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "trace_id": trace_id,
                },
            )
        except Exception as alert_exc:
            logger.warning(
                "Failed to send infra alert for API HTTP 5xx: %s",
                alert_exc,
                exc_info=True,
            )

    return response

# Глобальные переменные для доступа к CommandBus
_command_bus: Optional[CommandBus] = None
_gh_uid: str = ""
_zone_service: Optional[Any] = None
_command_bus_loop_id: Optional[int] = None
_zone_service_loop_id: Optional[int] = None
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
_AE_WORKFLOW_STATE_RECOVERY_ENABLED = os.getenv("AE_WORKFLOW_STATE_RECOVERY_ENABLED", "1") == "1"
_AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = max(
    60,
    int(os.getenv("AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC", "1800")),
)
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
_workflow_state_store = WorkflowStateStore()

ERR_TASK_EXPIRED = "task_expired"
ERR_TASK_DUE_DEADLINE_EXCEEDED = "task_due_deadline_exceeded"
ERR_COMMAND_BUS_UNAVAILABLE = "command_bus_unavailable"
ERR_COMMAND_BUS_LOOP_MISMATCH = "command_bus_loop_mismatch"
ERR_ZONE_SERVICE_LOOP_MISMATCH = "zone_service_loop_mismatch"
ERR_TASK_EXECUTION_FAILED = "task_execution_failed"
ERR_EXECUTION_EXCEPTION = "execution_exception"

AUTOMATION_STATE_IDLE = "IDLE"
AUTOMATION_STATE_TANK_FILLING = "TANK_FILLING"
AUTOMATION_STATE_TANK_RECIRC = "TANK_RECIRC"
AUTOMATION_STATE_READY = "READY"
AUTOMATION_STATE_IRRIGATING = "IRRIGATING"
AUTOMATION_STATE_IRRIG_RECIRC = "IRRIG_RECIRC"

AUTOMATION_STATE_LABELS: Dict[str, str] = {
    AUTOMATION_STATE_IDLE: "Система в ожидании",
    AUTOMATION_STATE_TANK_FILLING: "Набор бака с раствором",
    AUTOMATION_STATE_TANK_RECIRC: "Рециркуляция бака",
    AUTOMATION_STATE_READY: "Раствор готов к поливу",
    AUTOMATION_STATE_IRRIGATING: "Полив",
    AUTOMATION_STATE_IRRIG_RECIRC: "Рециркуляция после полива",
}

AUTOMATION_STATE_NEXT: Dict[str, Optional[str]] = {
    AUTOMATION_STATE_IDLE: AUTOMATION_STATE_TANK_FILLING,
    AUTOMATION_STATE_TANK_FILLING: AUTOMATION_STATE_TANK_RECIRC,
    AUTOMATION_STATE_TANK_RECIRC: AUTOMATION_STATE_READY,
    AUTOMATION_STATE_READY: AUTOMATION_STATE_IRRIGATING,
    AUTOMATION_STATE_IRRIGATING: AUTOMATION_STATE_IRRIG_RECIRC,
    AUTOMATION_STATE_IRRIG_RECIRC: AUTOMATION_STATE_IDLE,
}

AUTOMATION_TIMELINE_EVENT_LABELS: Dict[str, str] = {
    "SCHEDULE_TASK_ACCEPTED": "Scheduler: задача принята",
    "SCHEDULE_TASK_COMPLETED": "Scheduler: задача завершена",
    "SCHEDULE_TASK_FAILED": "Scheduler: задача с ошибкой",
    "TASK_RECEIVED": "Automation-engine: задача получена",
    "TASK_STARTED": "Automation-engine: выполнение начато",
    "DECISION_MADE": "Automation-engine: принято решение",
    "COMMAND_DISPATCHED": "Отправлена команда узлу",
    "COMMAND_FAILED": "Ошибка отправки команды",
    "TASK_FINISHED": "Automation-engine: выполнение завершено",
    "CLEAN_FILL_COMPLETED": "Бак чистой воды заполнен",
    "SOLUTION_FILL_COMPLETED": "Бак рабочего раствора заполнен",
    "CLEAN_FILL_RETRY_STARTED": "Запущен повторный цикл clean-fill",
    "PREPARE_TARGETS_REACHED": "Целевые pH/EC достигнуты",
    "TWO_TANK_STARTUP_INITIATED": "Запущен старт 2-баковой схемы",
    "SCHEDULE_TASK_EXECUTION_STARTED": "Старт исполнения scheduler-task",
    "SCHEDULE_TASK_EXECUTION_FINISHED": "Финиш исполнения scheduler-task",
}

# Test hooks для детерминированных ошибок (только в test mode)
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}  # zone_id -> {controller: error_type, ...}
_zone_states_override: Dict[int, Dict[str, Any]] = {}  # zone_id -> {error_streak: int, next_allowed_run_at: datetime}


def _spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    task_name: str,
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> asyncio.Task:
    task = asyncio.create_task(coro)

    def _on_done(done_task: asyncio.Task) -> None:
        if done_task.cancelled():
            return
        try:
            exc = done_task.exception()
        except Exception as callback_exc:
            logger.error(
                "Failed to inspect background task result: task_name=%s error=%s",
                task_name,
                callback_exc,
                exc_info=True,
            )
            return
        if exc is None:
            return
        logger.error(
            "Background task crashed: task_name=%s task_id=%s task_type=%s zone_id=%s error=%s",
            task_name,
            task_id,
            task_type,
            zone_id,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        try:
            alert_coro = send_infra_exception_alert(
                error=exc,
                code="infra_automation_background_task_crashed",
                alert_type="Automation Background Task Crashed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component=f"background:{task_name}",
                details={
                    "task_id": task_id,
                    "task_type": task_type,
                    "zone_id": zone_id,
                },
            )
            asyncio.create_task(alert_coro)
        except Exception:
            logger.warning(
                "Failed to schedule infra alert for crashed background task: task_name=%s",
                task_name,
                exc_info=True,
            )

    task.add_done_callback(_on_done)
    return task


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str, loop_id: Optional[int] = None):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid, _command_bus_loop_id
    _command_bus = command_bus
    _gh_uid = gh_uid
    _command_bus_loop_id = loop_id


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


def set_zone_service(zone_service: Any, loop_id: Optional[int] = None) -> None:
    """Установить ZoneAutomationService для выполнения scheduler-task diagnostics."""
    global _zone_service, _zone_service_loop_id
    _zone_service = zone_service
    _zone_service_loop_id = loop_id


def _is_loop_affinity_mismatch(assigned_loop_id: Optional[int]) -> bool:
    if assigned_loop_id is None:
        return False
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        return False
    return assigned_loop_id != current_loop_id


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


def _to_optional_int(raw_value: Any) -> Optional[int]:
    return policy_to_optional_int(raw_value)


def _to_optional_float(raw_value: Any) -> Optional[float]:
    return policy_to_optional_float(raw_value)


def _coerce_datetime(raw_value: Any) -> Optional[datetime]:
    return policy_coerce_datetime(raw_value)


def _extract_workflow(payload: Dict[str, Any]) -> str:
    return policy_extract_workflow(payload)


def _extract_topology(payload: Dict[str, Any]) -> str:
    return policy_extract_topology(payload)


def _is_task_active(task: Dict[str, Any]) -> bool:
    return policy_is_task_active(task)


def _task_sort_key(task: Dict[str, Any]) -> Tuple[int, datetime]:
    return policy_task_sort_key(
        task,
        is_task_active_fn=_is_task_active,
        coerce_datetime_fn=_coerce_datetime,
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


def _pick_preferred_zone_task(tasks: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return policy_pick_preferred_zone_task(
        tasks,
        task_sort_key_fn=_task_sort_key,
    )


def _sanitize_scheduler_task_snapshot(raw_task: Dict[str, Any], fallback_task_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return policy_sanitize_scheduler_task_snapshot(
        raw_task,
        to_optional_int_fn=_to_optional_int,
        fallback_task_id=fallback_task_id,
    )


async def _load_latest_zone_task_from_db(zone_id: int) -> Optional[Dict[str, Any]]:
    try:
        rows = await fetch(
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
        task = _sanitize_scheduler_task_snapshot(details, fallback_task_id=fallback_task_id)
        if task is not None:
            candidates.append(task)

    return _pick_preferred_zone_task(candidates)


async def _load_latest_zone_task(zone_id: int) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    in_memory_candidates: list[Dict[str, Any]] = []
    async with _scheduler_tasks_lock:
        await _cleanup_scheduler_tasks_locked(now)
        for raw_task in _scheduler_tasks.values():
            task = _sanitize_scheduler_task_snapshot(raw_task)
            if task is None:
                continue
            if int(task.get("zone_id") or 0) != int(zone_id):
                continue
            in_memory_candidates.append(task)

    preferred = _pick_preferred_zone_task(in_memory_candidates)
    if preferred is not None:
        return preferred

    from_db = await _load_latest_zone_task_from_db(zone_id)
    if from_db is None:
        return None

    async with _scheduler_tasks_lock:
        _scheduler_tasks[str(from_db["task_id"])] = dict(from_db)
    return from_db


def _system_config_from_task_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    startup = execution.get("startup") if isinstance(execution.get("startup"), dict) else {}

    system_type = str(execution.get("system_type") or "").strip().lower() or None
    tanks_count = _to_optional_int(execution.get("tanks_count"))
    clean_capacity = _to_optional_float(execution.get("clean_tank_fill_l"))
    nutrient_capacity = _to_optional_float(execution.get("nutrient_tank_target_l"))
    topology = _extract_topology(payload)

    if tanks_count not in {2, 3}:
        if "three_tank" in topology:
            tanks_count = 3
        elif "two_tank" in topology:
            tanks_count = 2
        elif system_type == "drip":
            tanks_count = 2
        else:
            tanks_count = 2

    if system_type is None:
        if "nft" in topology:
            system_type = "nft"
        elif "substrate" in topology:
            system_type = "substrate_trays"
        else:
            system_type = "drip"

    if clean_capacity is None:
        clean_capacity = _to_optional_float(startup.get("clean_tank_fill_l"))
    if nutrient_capacity is None:
        nutrient_capacity = _to_optional_float(startup.get("nutrient_tank_target_l"))

    return {
        "tanks_count": tanks_count,
        "system_type": system_type,
        "clean_tank_capacity_l": clean_capacity,
        "nutrient_tank_capacity_l": nutrient_capacity,
    }


async def _load_zone_system_config(zone_id: int, task_payload: Dict[str, Any]) -> Dict[str, Any]:
    config = _system_config_from_task_payload(task_payload)

    profile_subsystems: Dict[str, Any] = {}
    try:
        rows = await fetch(
            """
            SELECT subsystems
            FROM zone_automation_logic_profiles
            WHERE zone_id = $1 AND is_active = true
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if rows:
            subsystems = rows[0].get("subsystems")
            if isinstance(subsystems, dict):
                profile_subsystems = subsystems
    except Exception:
        logger.debug("zone_automation_logic_profiles unavailable for zone %s", zone_id, exc_info=True)

    if profile_subsystems:
        irrigation = profile_subsystems.get("irrigation") if isinstance(profile_subsystems.get("irrigation"), dict) else {}
        execution = irrigation.get("execution") if isinstance(irrigation.get("execution"), dict) else {}
        if config.get("system_type") in {None, ""}:
            profile_system_type = str(execution.get("system_type") or "").strip().lower()
            if profile_system_type:
                config["system_type"] = profile_system_type
        if config.get("tanks_count") not in {2, 3}:
            profile_tanks = _to_optional_int(execution.get("tanks_count"))
            if profile_tanks in {2, 3}:
                config["tanks_count"] = profile_tanks
        if config.get("clean_tank_capacity_l") is None:
            config["clean_tank_capacity_l"] = _to_optional_float(execution.get("clean_tank_fill_l"))
        if config.get("nutrient_tank_capacity_l") is None:
            config["nutrient_tank_capacity_l"] = _to_optional_float(execution.get("nutrient_tank_target_l"))

    try:
        rows = await fetch(
            """
            SELECT settings
            FROM grow_cycles
            WHERE zone_id = $1
              AND status IN ('PLANNED', 'RUNNING', 'PAUSED')
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if rows:
            settings = rows[0].get("settings")
            if isinstance(settings, dict):
                irrigation = settings.get("irrigation") if isinstance(settings.get("irrigation"), dict) else {}
                if config.get("system_type") in {None, ""}:
                    cycle_system_type = str(irrigation.get("system_type") or "").strip().lower()
                    if cycle_system_type:
                        config["system_type"] = cycle_system_type
                if config.get("clean_tank_capacity_l") is None:
                    config["clean_tank_capacity_l"] = _to_optional_float(irrigation.get("clean_tank_fill_l"))
                if config.get("nutrient_tank_capacity_l") is None:
                    config["nutrient_tank_capacity_l"] = _to_optional_float(irrigation.get("nutrient_tank_target_l"))
    except Exception:
        logger.debug("grow_cycles.settings unavailable for zone %s", zone_id, exc_info=True)

    if config.get("tanks_count") not in {2, 3}:
        config["tanks_count"] = 2
    if not config.get("system_type"):
        config["system_type"] = "drip"

    return config


def _normalize_level_percent(raw_value: Any) -> Optional[float]:
    value = _to_optional_float(raw_value)
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return max(0.0, min(100.0, value * 100.0))
    return max(0.0, min(100.0, value))


async def _load_zone_current_levels(zone_id: int) -> Dict[str, Any]:
    levels = {
        "clean_tank_level_percent": 0.0,
        "nutrient_tank_level_percent": 0.0,
        "buffer_tank_level_percent": None,
        "ph": None,
        "ec": None,
    }

    try:
        rows = await fetch(
            """
            SELECT s.type, s.label, tl.last_value, tl.last_ts
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.zone_id = $1
              AND s.is_active = true
            ORDER BY tl.last_ts DESC NULLS LAST, s.id DESC
            """,
            zone_id,
        )
    except Exception:
        logger.warning("Failed to load telemetry levels for automation-state: zone_id=%s", zone_id, exc_info=True)
        return levels

    clean_level: Optional[float] = None
    nutrient_level: Optional[float] = None
    buffer_level: Optional[float] = None

    for row in rows:
        sensor_type = str(row.get("type") or "").strip().upper()
        label = str(row.get("label") or "").strip().lower()
        value = row.get("last_value")

        if sensor_type == "PH" and levels["ph"] is None:
            levels["ph"] = _to_optional_float(value)
            continue
        if sensor_type == "EC" and levels["ec"] is None:
            levels["ec"] = _to_optional_float(value)
            continue
        if sensor_type != "WATER_LEVEL":
            continue

        normalized_level = _normalize_level_percent(value)
        if normalized_level is None:
            continue

        if any(token in label for token in ("clean", "чист", "source")):
            clean_level = max(clean_level or 0.0, normalized_level)
            continue
        if any(token in label for token in ("drain", "buffer", "слив")):
            buffer_level = max(buffer_level or 0.0, normalized_level)
            continue
        if any(token in label for token in ("solution", "nutrient", "npk", "mix", "рабоч")):
            nutrient_level = max(nutrient_level or 0.0, normalized_level)
            continue

        if nutrient_level is None:
            nutrient_level = normalized_level

    if clean_level is not None:
        levels["clean_tank_level_percent"] = round(clean_level, 2)
    if nutrient_level is not None:
        levels["nutrient_tank_level_percent"] = round(nutrient_level, 2)
    if buffer_level is not None:
        levels["buffer_tank_level_percent"] = round(buffer_level, 2)

    return levels


def _derive_automation_state(task: Optional[Dict[str, Any]]) -> str:
    return policy_derive_automation_state(
        task,
        extract_workflow=_extract_workflow,
        state_idle=AUTOMATION_STATE_IDLE,
        state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
        state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
        state_ready=AUTOMATION_STATE_READY,
        state_irrigating=AUTOMATION_STATE_IRRIGATING,
        state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
    )


def _resolve_state_started_at(task: Optional[Dict[str, Any]], state: str) -> Optional[datetime]:
    return policy_resolve_state_started_at(
        task,
        state,
        coerce_datetime=_coerce_datetime,
        state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
        state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
        state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
        state_irrigating=AUTOMATION_STATE_IRRIGATING,
    )


def _estimate_progress_percent(task: Optional[Dict[str, Any]], state: str) -> int:
    return policy_estimate_progress_percent(
        task,
        state,
        extract_workflow=_extract_workflow,
        to_optional_int=_to_optional_int,
        state_idle=AUTOMATION_STATE_IDLE,
        state_ready=AUTOMATION_STATE_READY,
        state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
        state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
        state_irrigating=AUTOMATION_STATE_IRRIGATING,
        state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
    )


def _estimate_completion_seconds(task: Optional[Dict[str, Any]]) -> Optional[int]:
    return policy_estimate_completion_seconds(
        task,
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        coerce_datetime=_coerce_datetime,
    )


def _derive_active_processes(task: Optional[Dict[str, Any]], state: str) -> Dict[str, bool]:
    return policy_derive_active_processes(
        task,
        state,
        extract_workflow=_extract_workflow,
        state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
        state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
        state_irrigating=AUTOMATION_STATE_IRRIGATING,
        state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
    )


def _extract_timeline_reason(payload: Dict[str, Any]) -> Optional[str]:
    return policy_extract_timeline_reason(payload)


def _build_timeline_label(event_type: str, reason_code: Optional[str]) -> str:
    return policy_build_timeline_label(
        event_type,
        reason_code,
        event_labels=AUTOMATION_TIMELINE_EVENT_LABELS,
    )


async def _load_automation_timeline(zone_id: int, limit: int = 24) -> list[Dict[str, Any]]:
    event_types = [
        "SCHEDULE_TASK_ACCEPTED",
        "SCHEDULE_TASK_COMPLETED",
        "SCHEDULE_TASK_FAILED",
        "SCHEDULE_TASK_EXECUTION_STARTED",
        "SCHEDULE_TASK_EXECUTION_FINISHED",
        "TASK_RECEIVED",
        "TASK_STARTED",
        "DECISION_MADE",
        "COMMAND_DISPATCHED",
        "COMMAND_FAILED",
        "TASK_FINISHED",
        "TWO_TANK_STARTUP_INITIATED",
        "CLEAN_FILL_COMPLETED",
        "SOLUTION_FILL_COMPLETED",
        "CLEAN_FILL_RETRY_STARTED",
        "PREPARE_TARGETS_REACHED",
    ]

    try:
        rows = await fetch(
            """
            SELECT id, type, payload_json, created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type = ANY($2::text[])
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            """,
            zone_id,
            event_types,
            max(1, min(limit, 50)),
        )
    except Exception:
        logger.debug("Failed to load automation timeline for zone_id=%s", zone_id, exc_info=True)
        return []

    timeline: list[Dict[str, Any]] = []
    for row in reversed(rows):
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        event_type = str(payload.get("event_type") or row.get("type") or "").strip()
        if not event_type:
            continue
        reason_code = _extract_timeline_reason(payload)
        created_at = row.get("created_at")
        timestamp = created_at.isoformat() if isinstance(created_at, datetime) else datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        timeline.append(
            {
                "event": event_type,
                "label": _build_timeline_label(event_type, reason_code),
                "timestamp": timestamp,
                "active": False,
            }
        )

    if timeline:
        timeline[-1]["active"] = True
    return timeline


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
    threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=_SCHEDULER_DEDUPE_WINDOW_SEC)
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
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    payload_fingerprint = _task_payload_fingerprint(req)

    async with _scheduler_tasks_lock:
        await _cleanup_scheduler_tasks_locked(datetime.now(timezone.utc).replace(tzinfo=None))

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
        task["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
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
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

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


def _normalize_recovery_phase(raw_phase: Any) -> str:
    value = str(raw_phase or "").strip().lower()
    if value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}:
        return value
    return "idle"


def _is_valid_recovery_phase(raw_phase: Any) -> bool:
    value = str(raw_phase or "").strip().lower()
    return value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}


def _extract_recovery_execution_workflow(payload: Dict[str, Any]) -> str:
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
    diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
    execution = diagnostics_targets.get("execution") if isinstance(diagnostics_targets.get("execution"), dict) else {}
    return str(execution.get("workflow") or "").strip().lower()


def _extract_payload_workflow_stage(payload: Dict[str, Any]) -> Tuple[str, str]:
    candidates = [
        ("workflow_stage", payload.get("workflow_stage")),
        ("workflow", payload.get("workflow")),
        ("diagnostics_workflow", payload.get("diagnostics_workflow")),
        ("targets.diagnostics.execution.workflow", _extract_recovery_execution_workflow(payload)),
    ]
    for source, raw_value in candidates:
        value = str(raw_value or "").strip().lower()
        if value:
            return value, f"zone_workflow_state.payload.{source}"
    return "", "zone_workflow_state.payload.workflow_stage"


def _resolve_recovery_phase(
    row: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[str, str, Optional[str]]:
    raw_column_phase = row.get("workflow_phase_raw", row.get("workflow_phase"))
    raw_payload_phase = payload.get("workflow_phase")
    if _is_valid_recovery_phase(raw_column_phase):
        return _normalize_recovery_phase(raw_column_phase), "zone_workflow_state.workflow_phase", None
    if _is_valid_recovery_phase(raw_payload_phase):
        return _normalize_recovery_phase(raw_payload_phase), "zone_workflow_state.payload.workflow_phase", None
    if str(raw_column_phase or "").strip() or str(raw_payload_phase or "").strip():
        return "idle", "zone_workflow_state.workflow_phase", "invalid_phase"
    return "idle", "zone_workflow_state.workflow_phase", None


def _resolve_workflow_for_recovery(
    phase: str,
    payload: Dict[str, Any],
    *,
    zone_id: Optional[int] = None,
) -> Dict[str, Any]:
    payload_workflow, workflow_source = _extract_payload_workflow_stage(payload)
    has_clean_timestamps = bool(
        str(payload.get("clean_fill_started_at") or "").strip()
        or str(payload.get("clean_fill_timeout_at") or "").strip()
    )
    has_solution_timestamps = bool(
        str(payload.get("solution_fill_started_at") or "").strip()
        or str(payload.get("solution_fill_timeout_at") or "").strip()
    )

    tank_filling_fallback = "solution_fill_check"
    if has_clean_timestamps and not has_solution_timestamps:
        tank_filling_fallback = "clean_fill_check"
    elif has_solution_timestamps:
        tank_filling_fallback = "solution_fill_check"

    fallback = {
        "tank_filling": tank_filling_fallback,
        "tank_recirc": "prepare_recirculation_check",
        "irrig_recirc": "irrigation_recovery_check",
    }
    allowed_workflows = {
        "tank_filling": {"clean_fill_check", "solution_fill_check"},
        "tank_recirc": {"prepare_recirculation_check"},
        "irrig_recirc": {"irrigation_recovery_check"},
    }

    mapped = payload_workflow
    if payload_workflow in {"startup", "cycle_start", "refill_check"}:
        mapped = fallback.get(phase, "")
    elif payload_workflow == "prepare_recirculation":
        mapped = "prepare_recirculation_check"
    elif payload_workflow == "irrigation_recovery":
        mapped = "irrigation_recovery_check"

    if mapped:
        allowed = allowed_workflows.get(phase)
        if allowed and mapped in allowed:
            if payload_workflow and payload_workflow != mapped:
                logger.info(
                    "Recovery workflow canonicalized from coarse stage: zone_id=%s phase=%s raw_workflow=%s canonical_workflow=%s",
                    zone_id,
                    phase,
                    payload_workflow,
                    mapped,
                )
                return {
                    "workflow": mapped,
                    "workflow_source": workflow_source,
                    "reason_code": "workflow_stage_canonicalized",
                    "fallback_from": payload_workflow,
                    "fallback_to": mapped,
                }
            return {
                "workflow": mapped,
                "workflow_source": workflow_source,
                "reason_code": "workflow_from_payload",
                "fallback_from": None,
                "fallback_to": None,
            }

        logger.warning(
            "Recovery workflow incompatible with phase, fallback will be used: zone_id=%s phase=%s payload_workflow=%s mapped_workflow=%s",
            zone_id,
            phase,
            payload_workflow or None,
            mapped,
        )

    phase_fallback = fallback.get(phase)
    if phase_fallback:
        if payload_workflow:
            logger.info(
                "Recovery workflow resolved via phase fallback: zone_id=%s phase=%s payload_workflow=%s fallback_workflow=%s",
                zone_id,
                phase,
                payload_workflow,
                phase_fallback,
            )
            return {
                "workflow": phase_fallback,
                "workflow_source": workflow_source,
                "reason_code": "workflow_phase_fallback",
                "fallback_from": mapped or payload_workflow,
                "fallback_to": phase_fallback,
            }
        return {
            "workflow": phase_fallback,
            "workflow_source": workflow_source,
            "reason_code": "workflow_missing_phase_fallback",
            "fallback_from": "missing_workflow",
            "fallback_to": phase_fallback,
        }

    if payload_workflow:
        logger.warning(
            "Recovery workflow unresolved for active phase: zone_id=%s phase=%s payload_workflow=%s",
            zone_id,
            phase,
            payload_workflow,
        )
    return {
        "workflow": None,
        "workflow_source": workflow_source,
        "reason_code": "workflow_unresolved",
        "fallback_from": None,
        "fallback_to": None,
    }


def _extract_recovery_correlation_id(payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(payload.get("recovery"), dict):
        nested = str(payload.get("recovery", {}).get("correlation_id") or "").strip()
        if nested:
            return nested
    correlation_id = str(payload.get("correlation_id") or "").strip()
    return correlation_id or None


def _log_workflow_recovery_action(
    *,
    zone_id: Optional[int],
    workflow_phase_source: str,
    workflow_phase_normalized: str,
    workflow_selected: Optional[str],
    scheduler_task_id_previous: Optional[str],
    recovery_action: str,
    reason_code: str,
    state_age_sec: int,
    correlation_id: Optional[str],
    enqueue_id: Optional[str],
    level: int = logging.INFO,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    details: Dict[str, Any] = {
        "component": "workflow_state_recovery",
        "zone_id": zone_id,
        "workflow_phase_source": workflow_phase_source,
        "workflow_phase_normalized": workflow_phase_normalized,
        "workflow_selected": workflow_selected,
        "scheduler_task_id_previous": scheduler_task_id_previous,
        "recovery_action": recovery_action,
        "reason_code": reason_code,
        "state_age_sec": state_age_sec,
        "correlation_id": correlation_id,
        "enqueue_id": enqueue_id,
    }
    if error_type:
        details["error_type"] = error_type
    if error_message:
        details["error_message"] = error_message
    if level >= logging.ERROR:
        details["trace_id"] = get_trace_id()
    logger.log(level, "Workflow state recovery action", extra=details)


async def _send_workflow_recovery_alert_safe(
    *,
    error: Exception,
    code: str,
    alert_type: str,
    zone_id: Optional[int],
    details: Dict[str, Any],
) -> None:
    if zone_id is None:
        return
    try:
        await send_infra_exception_alert(
            error=error,
            code=code,
            alert_type=alert_type,
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="workflow_state_recovery",
            error_type=type(error).__name__,
            details=details,
        )
    except Exception as alert_exc:
        logger.warning(
            "Failed to send workflow recovery infra alert: zone_id=%s code=%s error=%s",
            zone_id,
            code,
            alert_exc,
            exc_info=True,
        )


def _coerce_utc_naive(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _recover_zone_workflow_states() -> Dict[str, int]:
    if not _AE_WORKFLOW_STATE_RECOVERY_ENABLED:
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovered = 0
    stale_stopped = 0
    skipped = 0
    failed = 0

    try:
        active_states = await _workflow_state_store.list_active()
    except Exception:
        logger.warning("Zone workflow state recovery scan failed", exc_info=True)
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    for row in active_states:
        zone_id: Optional[int] = None
        phase_source = "zone_workflow_state.workflow_phase"
        phase = "idle"
        workflow: Optional[str] = None
        age_sec = 0
        enqueue_id: Optional[str] = None
        previous_task_id = str(row.get("scheduler_task_id") or "").strip() or None
        correlation_id: Optional[str] = None

        try:
            raw_zone_id = row.get("zone_id")
            try:
                zone_id = int(raw_zone_id)
            except (TypeError, ValueError):
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid row: invalid zone_id raw_zone_id=%r",
                    raw_zone_id,
                )
                _log_workflow_recovery_action(
                    zone_id=None,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code="invalid_zone_id",
                    state_age_sec=age_sec,
                    correlation_id=None,
                    enqueue_id=None,
                    level=logging.WARNING,
                )
                continue

            raw_payload = row.get("payload")
            if not isinstance(raw_payload, dict):
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid payload: zone_id=%s payload_type=%s",
                    zone_id,
                    type(raw_payload).__name__,
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code="invalid_payload",
                    state_age_sec=age_sec,
                    correlation_id=None,
                    enqueue_id=None,
                    level=logging.WARNING,
                )
                continue

            payload = dict(raw_payload)
            correlation_id = _extract_recovery_correlation_id(payload)
            phase, phase_source, phase_error = _resolve_recovery_phase(row, payload)
            if phase_error is not None:
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped invalid phase: zone_id=%s raw_phase=%r payload_phase=%r",
                    zone_id,
                    row.get("workflow_phase_raw", row.get("workflow_phase")),
                    payload.get("workflow_phase"),
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code=phase_error,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                    level=logging.WARNING,
                )
                continue

            updated_at = _coerce_utc_naive(row.get("updated_at")) or now
            age_sec = max(0, int((now - updated_at).total_seconds()))

            if phase in {"idle", "ready"}:
                skipped += 1
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_idle_ready",
                    reason_code=f"phase_{phase}",
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                )
                continue

            if age_sec > _AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC:
                try:
                    await _workflow_state_store.set(
                        zone_id=zone_id,
                        workflow_phase="idle",
                        payload={**payload, "recovery": {"action": "stale_safety_stop", "age_sec": age_sec}},
                        scheduler_task_id=None,
                    )
                    await create_zone_event(
                        zone_id,
                        "WORKFLOW_RECOVERY_STALE_STOPPED",
                        {
                            "previous_workflow_phase": phase,
                            "age_sec": age_sec,
                            "stale_timeout_sec": _AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC,
                        },
                    )
                    stale_stopped += 1
                    _log_workflow_recovery_action(
                        zone_id=zone_id,
                        workflow_phase_source=phase_source,
                        workflow_phase_normalized=phase,
                        workflow_selected=None,
                        scheduler_task_id_previous=previous_task_id,
                        recovery_action="stale_stop",
                        reason_code="state_stale_timeout",
                        state_age_sec=age_sec,
                        correlation_id=correlation_id,
                        enqueue_id=None,
                    )
                except Exception as exc:
                    failed += 1
                    logger.error(
                        "Failed to stale-stop workflow state during recovery: zone_id=%s phase=%s error=%s",
                        zone_id,
                        phase,
                        exc,
                        exc_info=True,
                    )
                    _log_workflow_recovery_action(
                        zone_id=zone_id,
                        workflow_phase_source=phase_source,
                        workflow_phase_normalized=phase,
                        workflow_selected=None,
                        scheduler_task_id_previous=previous_task_id,
                        recovery_action="failed",
                        reason_code="stale_stop_failed",
                        state_age_sec=age_sec,
                        correlation_id=correlation_id,
                        enqueue_id=None,
                        level=logging.ERROR,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                continue

            workflow_resolution = _resolve_workflow_for_recovery(phase, payload, zone_id=zone_id)
            workflow = str(workflow_resolution.get("workflow") or "").strip().lower() or None
            reason_code = str(workflow_resolution.get("reason_code") or "").strip().lower() or "workflow_unresolved"
            fallback_from = str(workflow_resolution.get("fallback_from") or "").strip().lower() or None
            fallback_to = str(workflow_resolution.get("fallback_to") or "").strip().lower() or None

            if not workflow:
                skipped += 1
                logger.warning(
                    "Workflow recovery skipped: no continuation workflow resolved: zone_id=%s phase=%s workflow_source=%s",
                    zone_id,
                    phase,
                    workflow_resolution.get("workflow_source"),
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=None,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="skip_invalid",
                    reason_code=reason_code,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=None,
                    level=logging.WARNING,
                )
                continue

            if fallback_from and fallback_to and fallback_from != fallback_to:
                logger.warning(
                    "Workflow recovery fallback applied: zone_id=%s phase=%s fallback_from=%s fallback_to=%s reason=%s",
                    zone_id,
                    phase,
                    fallback_from,
                    fallback_to,
                    reason_code,
                )
                try:
                    await create_zone_event(
                        zone_id,
                        "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK",
                        {
                            "workflow_phase": phase,
                            "fallback_from": fallback_from,
                            "fallback_to": fallback_to,
                            "reason_code": reason_code,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist workflow fallback event during recovery: zone_id=%s error=%s",
                        zone_id,
                        exc,
                        exc_info=True,
                    )

            continuation_payload = dict(payload)
            continuation_payload["workflow"] = workflow
            continuation_payload["workflow_stage"] = workflow
            continuation_payload["workflow_phase"] = phase
            continuation_payload.setdefault("payload_contract_version", "v2")
            continuation_payload["recovery"] = {
                "source": "automation_engine_startup_recovery",
                "workflow_phase": phase,
                "workflow_phase_source": phase_source,
                "state_age_sec": age_sec,
                "previous_scheduler_task_id": previous_task_id,
                "reason_code": reason_code,
            }

            try:
                enqueue_result = await enqueue_internal_scheduler_task(
                    zone_id=zone_id,
                    task_type="diagnostics",
                    payload=continuation_payload,
                    scheduled_for=now.isoformat(),
                    source="automation-engine:workflow-state-recovery",
                )
                enqueue_id = str(enqueue_result.get("enqueue_id") or "").strip() or None
                correlation_id = correlation_id or (str(enqueue_result.get("correlation_id") or "").strip() or None)
                await _workflow_state_store.set(
                    zone_id=zone_id,
                    workflow_phase=phase,
                    payload=continuation_payload,
                    scheduler_task_id=enqueue_id or "",
                )
                await create_zone_event(
                    zone_id,
                    "WORKFLOW_RECOVERY_ENQUEUED",
                    {
                        "workflow_phase": phase,
                        "workflow": workflow,
                        "enqueue_id": enqueue_id,
                        "correlation_id": correlation_id,
                        "state_age_sec": age_sec,
                    },
                )
                recovered += 1
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=workflow,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="enqueue_continuation",
                    reason_code=reason_code,
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=enqueue_id,
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "Failed to enqueue workflow continuation during startup recovery: zone_id=%s phase=%s error=%s",
                    zone_id,
                    phase,
                    exc,
                    exc_info=True,
                )
                _log_workflow_recovery_action(
                    zone_id=zone_id,
                    workflow_phase_source=phase_source,
                    workflow_phase_normalized=phase,
                    workflow_selected=workflow,
                    scheduler_task_id_previous=previous_task_id,
                    recovery_action="failed",
                    reason_code="enqueue_failed",
                    state_age_sec=age_sec,
                    correlation_id=correlation_id,
                    enqueue_id=enqueue_id,
                    level=logging.ERROR,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                await _send_workflow_recovery_alert_safe(
                    error=exc,
                    code="infra_workflow_state_recovery_enqueue_failed",
                    alert_type="Workflow State Recovery Enqueue Failed",
                    zone_id=zone_id,
                    details={
                        "workflow_phase": phase,
                        "workflow": workflow,
                    },
                )
        except Exception as exc:
            failed += 1
            logger.error(
                "Unexpected workflow recovery failure for zone row: zone_id=%s error=%s",
                zone_id,
                exc,
                exc_info=True,
            )
            _log_workflow_recovery_action(
                zone_id=zone_id,
                workflow_phase_source=phase_source,
                workflow_phase_normalized=phase,
                workflow_selected=workflow,
                scheduler_task_id_previous=previous_task_id,
                recovery_action="failed",
                reason_code="recovery_exception",
                state_age_sec=age_sec,
                correlation_id=correlation_id,
                enqueue_id=enqueue_id,
                level=logging.ERROR,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            await _send_workflow_recovery_alert_safe(
                error=exc,
                code="infra_workflow_state_recovery_row_failed",
                alert_type="Workflow State Recovery Row Failed",
                zone_id=zone_id,
                details={
                    "workflow_phase": phase,
                    "scheduler_task_id_previous": previous_task_id,
                },
            )

    return {
        "active": len(active_states),
        "recovered": recovered,
        "stale_stopped": stale_stopped,
        "skipped": skipped,
        "failed": failed,
    }


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
    if _is_loop_affinity_mismatch(_command_bus_loop_id):
        failure_result = _build_execution_terminal_result(
            error_code=ERR_COMMAND_BUS_LOOP_MISMATCH,
            reason="CommandBus создан в другом event loop, выполнение задачи отклонено",
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
        zone_service = _zone_service
        if _is_loop_affinity_mismatch(_zone_service_loop_id):
            if req.task_type == "diagnostics":
                failure_result = _build_execution_terminal_result(
                    error_code=ERR_ZONE_SERVICE_LOOP_MISMATCH,
                    reason="ZoneAutomationService создан в другом event loop, diagnostics отклонен",
                    mode="execution_unavailable",
                )
                await _update_scheduler_task(
                    task_id=task_id,
                    status="failed",
                    result=failure_result,
                    error=str(failure_result["error"]),
                    error_code=str(failure_result["error_code"]),
                )
                return
            zone_service = None
        executor = SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)
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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
            try:
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

            trace_id = get_trace_id()
            _spawn_background_task(
                _execute_scheduler_task(task["task_id"], req, trace_id),
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


@app.get("/scheduler/task/{task_id}")
async def scheduler_task_status(task_id: str):
    """Статус абстрактной задачи scheduler."""
    async with _scheduler_tasks_lock:
        await _cleanup_scheduler_tasks_locked(datetime.now(timezone.utc).replace(tzinfo=None))
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


async def _build_zone_automation_state_payload(zone_id: int) -> Dict[str, Any]:
    task = await _load_latest_zone_task(zone_id)
    payload = task.get("payload") if isinstance(task, dict) and isinstance(task.get("payload"), dict) else {}
    state = _derive_automation_state(task)
    state_started_at = _resolve_state_started_at(task, state)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed_sec = int((now - state_started_at).total_seconds()) if state_started_at is not None else 0
    progress_percent = _estimate_progress_percent(task, state)

    system_config = await _load_zone_system_config(zone_id, payload)
    current_levels = await _load_zone_current_levels(zone_id)
    active_processes = _derive_active_processes(task, state)
    timeline = await _load_automation_timeline(zone_id)
    estimated_completion_sec = _estimate_completion_seconds(task)

    return {
        "zone_id": zone_id,
        "state": state,
        "state_label": AUTOMATION_STATE_LABELS.get(state, AUTOMATION_STATE_LABELS[AUTOMATION_STATE_IDLE]),
        "state_details": {
            "started_at": state_started_at.isoformat() if state_started_at is not None else None,
            "elapsed_sec": elapsed_sec,
            "progress_percent": progress_percent,
        },
        "system_config": {
            "tanks_count": int(system_config.get("tanks_count") or 2),
            "system_type": str(system_config.get("system_type") or "drip"),
            "clean_tank_capacity_l": system_config.get("clean_tank_capacity_l"),
            "nutrient_tank_capacity_l": system_config.get("nutrient_tank_capacity_l"),
        },
        "current_levels": current_levels,
        "active_processes": active_processes,
        "timeline": timeline,
        "next_state": AUTOMATION_STATE_NEXT.get(state),
        "estimated_completion_sec": estimated_completion_sec,
    }


@app.get("/zones/{zone_id}/automation-state")
async def zone_automation_state(zone_id: int):
    await _validate_scheduler_zone(zone_id)
    payload = await _build_zone_automation_state_payload(zone_id)
    return payload


@app.on_event("startup")
async def run_scheduler_task_recovery_on_startup() -> None:
    summary = await _recover_inflight_scheduler_tasks()
    if summary["recovered"] > 0:
        logger.warning(
            "Recovered in-flight scheduler tasks after restart: recovered=%s scanned=%s",
            summary["recovered"],
            summary["scanned"],
        )
    workflow_summary = await _recover_zone_workflow_states()
    if workflow_summary["active"] > 0:
        logger.warning(
            "Recovered workflow states after restart: active=%s recovered=%s stale_stopped=%s skipped=%s failed=%s",
            workflow_summary["active"],
            workflow_summary["recovered"],
            workflow_summary["stale_stopped"],
            workflow_summary["skipped"],
            workflow_summary["failed"],
        )


def _is_command_bus_ready() -> Tuple[bool, str]:
    if _command_bus is None:
        return False, "command_bus_unavailable"
    if _is_loop_affinity_mismatch(_command_bus_loop_id):
        return False, ERR_COMMAND_BUS_LOOP_MISMATCH
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
