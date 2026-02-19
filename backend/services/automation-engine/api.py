"""
FastAPI endpoints для automation-engine.
Предоставляет REST API для scheduler и других сервисов.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import JSONResponse
from prometheus_client import Gauge
from typing import Optional, Dict, Any, Literal, Tuple, Coroutine, Set, AsyncIterator

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
from application.api_automation_state_constants import (
    AUTOMATION_STATE_IDLE,
    AUTOMATION_STATE_IRRIGATING,
    AUTOMATION_STATE_IRRIG_RECIRC,
    AUTOMATION_STATE_LABELS,
    AUTOMATION_STATE_NEXT,
    AUTOMATION_STATE_READY,
    AUTOMATION_STATE_TANK_FILLING,
    AUTOMATION_STATE_TANK_RECIRC,
    AUTOMATION_TIMELINE_EVENT_LABELS,
)
from application.api_health import (
    build_readiness_payload as policy_build_readiness_payload,
    is_bootstrap_store_ready as policy_is_bootstrap_store_ready,
    is_command_bus_ready as policy_is_command_bus_ready,
    is_db_ready as policy_is_db_ready,
)
from application.api_payload_parsing import (
    coerce_datetime as policy_coerce_datetime,
    extract_workflow as policy_extract_workflow,
    to_optional_int as policy_to_optional_int,
)
from application.api_test_hooks import (
    TestHookRequest,
    build_test_hook_state_payload as policy_build_test_hook_state_payload,
    get_test_hook_for_zone as policy_get_test_hook_for_zone,
    get_zone_state_override as policy_get_zone_state_override,
    handle_test_hook as policy_handle_test_hook,
)
from application.api_recovery import (
    recover_inflight_scheduler_tasks as policy_recover_inflight_scheduler_tasks,
    recover_zone_workflow_states as policy_recover_zone_workflow_states,
)
from application.api_scheduler_execution import (
    execute_scheduler_task as policy_execute_scheduler_task,
)
from application.api_scheduler_bootstrap import (
    build_scheduler_bootstrap_heartbeat_response as policy_build_scheduler_bootstrap_heartbeat_response,
    build_scheduler_bootstrap_response as policy_build_scheduler_bootstrap_response,
    validate_scheduler_dispatch_lease as policy_validate_scheduler_dispatch_lease,
)
from application.api_zone_state import (
    load_automation_timeline as policy_load_automation_timeline,
    load_zone_current_levels as policy_load_zone_current_levels,
    load_zone_system_config as policy_load_zone_system_config,
)
from application.api_scheduler_store import (
    cleanup_scheduler_tasks_locked as policy_cleanup_scheduler_tasks_locked,
    create_scheduler_task as policy_create_scheduler_task,
    load_scheduler_task_by_correlation_id as policy_load_scheduler_task_by_correlation_id,
    load_scheduler_task_snapshot as policy_load_scheduler_task_snapshot,
    persist_scheduler_task_snapshot as policy_persist_scheduler_task_snapshot,
    scheduler_task_log_name as policy_scheduler_task_log_name,
    update_scheduler_task as policy_update_scheduler_task,
)
from application.api_scheduler_routes import (
    get_scheduler_task_status as policy_get_scheduler_task_status,
    submit_scheduler_task as policy_submit_scheduler_task,
)
from application.api_scheduler_security import (
    validate_scheduler_security_baseline as policy_validate_scheduler_security_baseline,
)
from application.api_zone_state_payload import (
    build_zone_automation_state_payload as policy_build_zone_automation_state_payload,
)
from application.api_zone_task_loader import (
    load_latest_zone_task as policy_load_latest_zone_task,
)
from application.api_runtime import (
    process_trace_request as policy_process_trace_request,
    spawn_background_task as policy_spawn_background_task,
    update_command_effect_confirm_rate as policy_update_command_effect_confirm_rate,
)
from application.api_contracts import (
    SchedulerBootstrapHeartbeatRequest,
    SchedulerBootstrapRequest,
    SchedulerInternalEnqueueRequest,
    SchedulerTaskRequest,
)
from application.api_scheduler_validation import (
    validate_scheduler_zone as policy_validate_scheduler_zone,
)
from application.api_scheduler_cutover import (
    build_scheduler_cutover_state_payload as policy_build_scheduler_cutover_state_payload,
)
from application.api_scheduler_integration import (
    build_scheduler_integration_contract_payload as policy_build_scheduler_integration_contract_payload,
)
from application.api_scheduler_observability import (
    build_scheduler_observability_contract_payload as policy_build_scheduler_observability_contract_payload,
)
from application.api_internal_enqueue import (
    scheduler_internal_enqueue as policy_scheduler_internal_enqueue,
)
from application.api_scheduler_helpers import (
    build_deadline_terminal_result as policy_build_deadline_terminal_result,
    build_execution_terminal_result as policy_build_execution_terminal_result,
    new_scheduler_lease_id as policy_new_scheduler_lease_id,
    new_scheduler_task_id as policy_new_scheduler_task_id,
    normalize_failed_execution_result as policy_normalize_failed_execution_result,
    task_payload_fingerprint as policy_task_payload_fingerprint,
    task_payload_matches as policy_task_payload_matches,
)
from services.resilience_contract import (
    SCHEDULER_BOOTSTRAP_STATUS_READY,
    SCHEDULER_BOOTSTRAP_STATUS_WAIT,
    SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH,
    SCHEDULER_ERR_COMMAND_BUS_UNAVAILABLE,
    SCHEDULER_ERR_EXECUTION_EXCEPTION,
    SCHEDULER_ERR_TASK_DUE_DEADLINE_EXCEEDED,
    SCHEDULER_ERR_TASK_EXECUTION_FAILED,
    SCHEDULER_ERR_TASK_EXPIRED,
    SCHEDULER_ERR_ZONE_SERVICE_LOOP_MISMATCH,
    SCHEDULER_STATUS_ACCEPTED,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    await _run_scheduler_task_recovery_on_startup()
    try:
        yield
    finally:
        await _drain_background_tasks()


app = FastAPI(title="Automation Engine API", lifespan=_app_lifespan)


def _env_true(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


_APP_ENV = str(os.getenv("APP_ENV", "local")).strip().lower()
_AE_VERBOSE_HTTP_LOGGING = _env_true(
    "AE_DEV_VERBOSE_HTTP_LOGGING",
    "1" if _APP_ENV in {"local", "dev", "development"} else "0",
)
@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    return await policy_process_trace_request(
        request,
        call_next,
        extract_trace_id_from_headers_fn=extract_trace_id_from_headers,
        set_trace_id_fn=set_trace_id,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        send_infra_alert_fn=send_infra_alert,
        logger=logger,
        verbose_http_logging=_AE_VERBOSE_HTTP_LOGGING,
    )

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
_AE2_ROLLOUT_PROFILE = str(os.getenv("AE2_ROLLOUT_PROFILE", "canary-first")).strip().lower() or "canary-first"
_AE2_TIER2_GDD_ENABLED = _env_true("AE2_TIER2_GDD_ENABLED", "0")
_AE2_TIER2_APPROVALS_ENABLED = _env_true("AE2_TIER2_APPROVALS_ENABLED", "0")
_AE2_TIER2_DAILY_DIGEST_ENABLED = _env_true("AE2_TIER2_DAILY_DIGEST_ENABLED", "0")
_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE = _env_true("AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", "1")
_AE_SCHEDULER_REQUIRE_TRACE_ID = _env_true("AE_SCHEDULER_REQUIRE_TRACE_ID", "1")
_AE_SCHEDULER_API_TOKEN = str(
    os.getenv("SCHEDULER_API_TOKEN")
    or os.getenv("PY_INGEST_TOKEN")
    or os.getenv("PY_API_TOKEN")
    or ""
).strip()
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

ERR_TASK_EXPIRED = SCHEDULER_ERR_TASK_EXPIRED
ERR_TASK_DUE_DEADLINE_EXCEEDED = SCHEDULER_ERR_TASK_DUE_DEADLINE_EXCEEDED
ERR_COMMAND_BUS_UNAVAILABLE = SCHEDULER_ERR_COMMAND_BUS_UNAVAILABLE
ERR_COMMAND_BUS_LOOP_MISMATCH = SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH
ERR_ZONE_SERVICE_LOOP_MISMATCH = SCHEDULER_ERR_ZONE_SERVICE_LOOP_MISMATCH
ERR_TASK_EXECUTION_FAILED = SCHEDULER_ERR_TASK_EXECUTION_FAILED
ERR_EXECUTION_EXCEPTION = SCHEDULER_ERR_EXECUTION_EXCEPTION

# Test hooks для детерминированных ошибок (только в test mode)
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}  # zone_id -> {controller: error_type, ...}
_zone_states_override: Dict[int, Dict[str, Any]] = {}  # zone_id -> {error_streak: int, next_allowed_run_at: datetime}
_background_tasks: Set[asyncio.Task] = set()


async def _drain_background_tasks(timeout_sec: float = 5.0) -> None:
    if not _background_tasks:
        return

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        _background_tasks.clear()
        return

    pending: list[asyncio.Task] = []
    foreign_or_closed = 0
    for task in list(_background_tasks):
        if task.done():
            _background_tasks.discard(task)
            continue
        try:
            task_loop = task.get_loop()
        except Exception:
            _background_tasks.discard(task)
            continue

        if task_loop is not current_loop:
            if not task_loop.is_closed():
                try:
                    task_loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass
            _background_tasks.discard(task)
            foreign_or_closed += 1
            continue

        try:
            task.cancel()
            pending.append(task)
        except RuntimeError:
            _background_tasks.discard(task)
            foreign_or_closed += 1

    if foreign_or_closed:
        logger.debug("Skipped background tasks from foreign/closed loops: count=%s", foreign_or_closed)
    if not pending:
        return

    try:
        await asyncio.wait_for(
            asyncio.gather(*pending, return_exceptions=True),
            timeout=max(float(timeout_sec), 0.1),
        )
    except asyncio.TimeoutError:
        still_pending = sum(1 for task in pending if not task.done())
        logger.warning(
            "Background task shutdown timeout: pending=%s timeout_sec=%.1f",
            still_pending,
            timeout_sec,
        )
    finally:
        for task in pending:
            _background_tasks.discard(task)


def _spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    task_name: str,
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> asyncio.Task:
    task = policy_spawn_background_task(
        coro,
        task_name=task_name,
        zone_id=zone_id,
        task_id=task_id,
        task_type=task_type,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        logger=logger,
    )
    _background_tasks.add(task)
    task.add_done_callback(lambda done_task: _background_tasks.discard(done_task))
    return task


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str, loop_id: Optional[int] = None):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid, _command_bus_loop_id
    _command_bus = command_bus
    _gh_uid = gh_uid
    _command_bus_loop_id = loop_id


def _update_command_effect_confirm_rate(task_type: str, result: Dict[str, Any]) -> None:
    policy_update_command_effect_confirm_rate(
        task_type,
        result,
        command_effect_totals=_command_effect_totals,
        command_effect_confirmed_totals=_command_effect_confirmed_totals,
        command_effect_confirm_rate_metric=COMMAND_EFFECT_CONFIRM_RATE,
    )


def set_zone_service(zone_service: Any, loop_id: Optional[int] = None) -> None:
    """Установить ZoneAutomationService для выполнения scheduler-task diagnostics."""
    global _zone_service, _zone_service_loop_id
    _zone_service = zone_service
    _zone_service_loop_id = loop_id


async def is_scheduler_single_writer_active() -> bool:
    """Проверить, активна ли scheduler lease для single-writer арбитража."""
    if not _SCHEDULER_BOOTSTRAP_ENFORCE:
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with _scheduler_bootstrap_lock:
        _cleanup_bootstrap_leases_locked(now)
        return bool(_scheduler_bootstrap_leases)


def _build_scheduler_task_executor(*, command_bus: CommandBus, zone_service: Optional[Any]) -> SchedulerTaskExecutor:
    return SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)


def _is_loop_affinity_mismatch(assigned_loop_id: Optional[int]) -> bool:
    if assigned_loop_id is None:
        return False
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        return False
    return assigned_loop_id != current_loop_id


async def _validate_scheduler_zone(zone_id: int) -> None:
    await policy_validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)


def _new_scheduler_task_id() -> str:
    return policy_new_scheduler_task_id()


def _new_scheduler_lease_id() -> str:
    return policy_new_scheduler_lease_id()


def _task_payload_fingerprint(req: SchedulerTaskRequest) -> str:
    return policy_task_payload_fingerprint(req)


def _task_payload_matches(req: SchedulerTaskRequest, existing_task: Dict[str, Any], expected_fingerprint: str) -> bool:
    return policy_task_payload_matches(req, existing_task, expected_fingerprint)


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
    return policy_build_deadline_terminal_result(
        status=status,
        now=now,
        due_at=due_at,
        expires_at=expires_at,
        err_task_expired=ERR_TASK_EXPIRED,
        err_task_due_deadline_exceeded=ERR_TASK_DUE_DEADLINE_EXCEEDED,
    )


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
    return policy_build_execution_terminal_result(
        error_code=error_code,
        reason=reason,
        mode=mode,
        action_required=action_required,
        decision=decision,
        reason_code=reason_code,
        extra=extra,
    )


def _normalize_failed_execution_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return policy_normalize_failed_execution_result(
        result,
        err_task_execution_failed=ERR_TASK_EXECUTION_FAILED,
    )


def _normalize_cleanup_timestamp(raw_value: Any, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except Exception:
        return fallback
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def _load_latest_zone_task(zone_id: int) -> Optional[Dict[str, Any]]:
    return await policy_load_latest_zone_task(
        zone_id,
        scheduler_tasks_lock=_scheduler_tasks_lock,
        scheduler_tasks=_scheduler_tasks,
        cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked,
        fetch_fn=fetch,
        logger=logger,
    )


async def _cleanup_scheduler_tasks_locked(now: datetime) -> None:
    await policy_cleanup_scheduler_tasks_locked(
        now,
        scheduler_tasks=_scheduler_tasks,
        scheduler_task_ttl_seconds=_SCHEDULER_TASK_TTL_SECONDS,
        scheduler_task_max_in_memory=_SCHEDULER_TASK_MAX_IN_MEMORY,
        normalize_cleanup_timestamp_fn=_normalize_cleanup_timestamp,
    )


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
    command_bus_ready, command_bus_reason = policy_is_command_bus_ready(
        command_bus=_command_bus,
        command_bus_loop_id=_command_bus_loop_id,
        is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch,
        loop_mismatch_code=ERR_COMMAND_BUS_LOOP_MISMATCH,
    )
    if not command_bus_ready:
        return SCHEDULER_BOOTSTRAP_STATUS_WAIT, command_bus_reason

    db_ready, db_reason = await policy_is_db_ready(fetch_fn=fetch, logger=logger)
    if not db_ready:
        return SCHEDULER_BOOTSTRAP_STATUS_WAIT, db_reason

    bootstrap_store_ready, bootstrap_store_reason = policy_is_bootstrap_store_ready(
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
    )
    if not bootstrap_store_ready:
        return SCHEDULER_BOOTSTRAP_STATUS_WAIT, bootstrap_store_reason
    return SCHEDULER_BOOTSTRAP_STATUS_READY, "ok"


async def _load_scheduler_task_by_correlation_id(correlation_id: str) -> Optional[Dict[str, Any]]:
    return await policy_load_scheduler_task_by_correlation_id(
        correlation_id,
        fetch_fn=fetch,
        scheduler_dedupe_window_sec=_SCHEDULER_DEDUPE_WINDOW_SEC,
        logger=logger,
    )


async def _create_scheduler_task(
    req: SchedulerTaskRequest,
    *,
    initial_status: str = SCHEDULER_STATUS_ACCEPTED,
    initial_result: Optional[Dict[str, Any]] = None,
    initial_error: Optional[str] = None,
    initial_error_code: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    return await policy_create_scheduler_task(
        req,
        scheduler_tasks=_scheduler_tasks,
        scheduler_tasks_lock=_scheduler_tasks_lock,
        cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked,
        load_scheduler_task_by_correlation_id_fn=_load_scheduler_task_by_correlation_id,
        task_payload_fingerprint_fn=_task_payload_fingerprint,
        task_payload_matches_fn=_task_payload_matches,
        new_scheduler_task_id_fn=_new_scheduler_task_id,
        persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot,
        initial_status=initial_status,
        initial_result=initial_result,
        initial_error=initial_error,
        initial_error_code=initial_error_code,
    )


async def _update_scheduler_task(
    *,
    task_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    await policy_update_scheduler_task(
        task_id=task_id,
        status=status,
        scheduler_tasks=_scheduler_tasks,
        scheduler_tasks_lock=_scheduler_tasks_lock,
        persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot,
        result=result,
        error=error,
        error_code=error_code,
    )


def _scheduler_task_log_name(task_id: str) -> str:
    return policy_scheduler_task_log_name(task_id)


async def _persist_scheduler_task_snapshot(task: Dict[str, Any]) -> None:
    await policy_persist_scheduler_task_snapshot(
        task,
        create_scheduler_log_fn=create_scheduler_log,
        logger=logger,
    )


async def _load_scheduler_task_snapshot(task_id: str) -> Optional[Dict[str, Any]]:
    return await policy_load_scheduler_task_snapshot(
        task_id,
        fetch_fn=fetch,
        logger=logger,
    )


async def _recover_inflight_scheduler_tasks() -> Dict[str, int]:
    return await policy_recover_inflight_scheduler_tasks(
        enabled=_AE_TASK_RECOVERY_ENABLED,
        fetch_fn=fetch,
        scan_limit=_AE_TASK_RECOVERY_SCAN_LIMIT,
        build_execution_terminal_result_fn=_build_execution_terminal_result,
        scheduler_tasks=_scheduler_tasks,
        scheduler_tasks_lock=_scheduler_tasks_lock,
        persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot,
        create_zone_event_fn=create_zone_event,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        task_recovery_success_rate_gauge=TASK_RECOVERY_SUCCESS_RATE,
        logger=logger,
    )


async def _recover_zone_workflow_states() -> Dict[str, int]:
    return await policy_recover_zone_workflow_states(
        enabled=_AE_WORKFLOW_STATE_RECOVERY_ENABLED,
        stale_timeout_sec=_AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC,
        workflow_state_store=_workflow_state_store,
        logger=logger,
        create_zone_event_fn=create_zone_event,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        get_trace_id_fn=get_trace_id,
    )


async def _execute_scheduler_task(task_id: str, req: SchedulerTaskRequest, trace_id: Optional[str]) -> None:
    await policy_execute_scheduler_task(
        task_id,
        req,
        trace_id,
        command_bus=_command_bus,
        command_bus_loop_id=_command_bus_loop_id,
        zone_service=_zone_service,
        zone_service_loop_id=_zone_service_loop_id,
        is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch,
        update_scheduler_task_fn=_update_scheduler_task,
        update_command_effect_confirm_rate_fn=_update_command_effect_confirm_rate,
        normalize_failed_execution_result_fn=_normalize_failed_execution_result,
        build_execution_terminal_result_fn=_build_execution_terminal_result,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        scheduler_task_executor_factory=_build_scheduler_task_executor,
        set_trace_id_fn=set_trace_id,
        logger=logger,
        err_command_bus_unavailable=ERR_COMMAND_BUS_UNAVAILABLE,
        err_command_bus_loop_mismatch=ERR_COMMAND_BUS_LOOP_MISMATCH,
        err_zone_service_loop_mismatch=ERR_ZONE_SERVICE_LOOP_MISMATCH,
        err_execution_exception=ERR_EXECUTION_EXCEPTION,
    )


async def _validate_scheduler_dispatch_lease(request: Request) -> None:
    await policy_validate_scheduler_dispatch_lease(
        enforce=_SCHEDULER_BOOTSTRAP_ENFORCE,
        headers=request.headers,
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        cleanup_bootstrap_leases_locked_fn=_cleanup_bootstrap_leases_locked,
    )


async def _validate_scheduler_security_baseline(request: Request) -> None:
    policy_validate_scheduler_security_baseline(
        headers=request.headers,
        enforce=_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE,
        scheduler_api_token=_AE_SCHEDULER_API_TOKEN,
        require_trace_id=_AE_SCHEDULER_REQUIRE_TRACE_ID,
        extract_trace_id_from_headers_fn=extract_trace_id_from_headers,
    )


@app.post("/scheduler/bootstrap")
async def scheduler_bootstrap(req: SchedulerBootstrapRequest = Body(...)):
    return await policy_build_scheduler_bootstrap_response(
        req,
        scheduler_bootstrap_state_fn=_scheduler_bootstrap_state,
        is_scheduler_protocol_supported_fn=_is_scheduler_protocol_supported,
        scheduler_bootstrap_lease_ttl_sec=_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
        scheduler_bootstrap_poll_interval_sec=_SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
        scheduler_bootstrap_task_timeout_sec=_SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC,
        scheduler_dedupe_window_sec=_SCHEDULER_DEDUPE_WINDOW_SEC,
        rollout_profile=_AE2_ROLLOUT_PROFILE,
        tier2_capabilities={
            "gdd_phase_transitions": _AE2_TIER2_GDD_ENABLED,
            "mobile_approvals": _AE2_TIER2_APPROVALS_ENABLED,
            "daily_health_digest": _AE2_TIER2_DAILY_DIGEST_ENABLED,
        },
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        cleanup_bootstrap_leases_locked_fn=_cleanup_bootstrap_leases_locked,
        new_scheduler_lease_id_fn=_new_scheduler_lease_id,
        create_scheduler_log_fn=create_scheduler_log,
        send_infra_alert_fn=send_infra_alert,
        logger=logger,
    )


@app.post("/scheduler/bootstrap/heartbeat")
async def scheduler_bootstrap_heartbeat(req: SchedulerBootstrapHeartbeatRequest = Body(...)):
    return await policy_build_scheduler_bootstrap_heartbeat_response(
        req,
        scheduler_bootstrap_state_fn=_scheduler_bootstrap_state,
        scheduler_bootstrap_lease_ttl_sec=_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
        scheduler_bootstrap_poll_interval_sec=_SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
        rollout_profile=_AE2_ROLLOUT_PROFILE,
        tier2_capabilities={
            "gdd_phase_transitions": _AE2_TIER2_GDD_ENABLED,
            "mobile_approvals": _AE2_TIER2_APPROVALS_ENABLED,
            "daily_health_digest": _AE2_TIER2_DAILY_DIGEST_ENABLED,
        },
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        cleanup_bootstrap_leases_locked_fn=_cleanup_bootstrap_leases_locked,
        create_scheduler_log_fn=create_scheduler_log,
    )


@app.get("/scheduler/cutover/state")
async def scheduler_cutover_state():
    return {
        "status": "ok",
        "data": policy_build_scheduler_cutover_state_payload(
            rollout_profile=_AE2_ROLLOUT_PROFILE,
            tier2_capabilities={
                "gdd_phase_transitions": _AE2_TIER2_GDD_ENABLED,
                "mobile_approvals": _AE2_TIER2_APPROVALS_ENABLED,
                "daily_health_digest": _AE2_TIER2_DAILY_DIGEST_ENABLED,
            },
            scheduler_bootstrap_enforce=_SCHEDULER_BOOTSTRAP_ENFORCE,
            scheduler_security_baseline_enforce=_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE,
            scheduler_require_trace_id=_AE_SCHEDULER_REQUIRE_TRACE_ID,
            scheduler_dedupe_window_sec=_SCHEDULER_DEDUPE_WINDOW_SEC,
            scheduler_bootstrap_lease_ttl_sec=_SCHEDULER_BOOTSTRAP_LEASE_TTL_SEC,
            scheduler_bootstrap_poll_interval_sec=_SCHEDULER_BOOTSTRAP_POLL_INTERVAL_SEC,
            scheduler_bootstrap_task_timeout_sec=_SCHEDULER_BOOTSTRAP_TASK_TIMEOUT_SEC,
        ),
    }


@app.get("/scheduler/integration/contracts")
async def scheduler_integration_contracts():
    return {
        "status": "ok",
        "data": policy_build_scheduler_integration_contract_payload(
            rollout_profile=_AE2_ROLLOUT_PROFILE,
            tier2_capabilities={
                "gdd_phase_transitions": _AE2_TIER2_GDD_ENABLED,
                "mobile_approvals": _AE2_TIER2_APPROVALS_ENABLED,
                "daily_health_digest": _AE2_TIER2_DAILY_DIGEST_ENABLED,
            },
        ),
    }


@app.get("/scheduler/observability/contracts")
async def scheduler_observability_contracts():
    return {
        "status": "ok",
        "data": policy_build_scheduler_observability_contract_payload(),
    }


@app.post("/scheduler/internal/enqueue")
async def scheduler_internal_enqueue(req: SchedulerInternalEnqueueRequest = Body(...)):
    return await policy_scheduler_internal_enqueue(
        req,
        validate_scheduler_zone_fn=_validate_scheduler_zone,
        scheduler_task_types=_SCHEDULER_TASK_TYPES,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task,
    )


@app.post("/scheduler/task")
async def scheduler_task(request: Request, req: SchedulerTaskRequest = Body(...)):
    return await policy_submit_scheduler_task(
        request,
        req,
        command_bus=_command_bus,
        scheduler_task_types=_SCHEDULER_TASK_TYPES,
        validate_scheduler_dispatch_lease_fn=_validate_scheduler_dispatch_lease,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        validate_scheduler_zone_fn=_validate_scheduler_zone,
        parse_iso_datetime_fn=_parse_iso_datetime,
        require_iso_datetime_fn=_require_iso_datetime,
        build_deadline_terminal_result_fn=_build_deadline_terminal_result,
        create_scheduler_task_fn=_create_scheduler_task,
        create_zone_event_fn=create_zone_event,
        spawn_background_task_fn=_spawn_background_task,
        execute_scheduler_task_fn=_execute_scheduler_task,
        get_trace_id_fn=get_trace_id,
        logger=logger,
    )


@app.get("/scheduler/task/{task_id}")
async def scheduler_task_status(task_id: str):
    """Статус абстрактной задачи scheduler."""
    return await policy_get_scheduler_task_status(
        task_id,
        scheduler_tasks_lock=_scheduler_tasks_lock,
        scheduler_tasks=_scheduler_tasks,
        cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked,
        load_scheduler_task_snapshot_fn=_load_scheduler_task_snapshot,
    )


@app.get("/zones/{zone_id}/automation-state")
async def zone_automation_state(zone_id: int):
    await _validate_scheduler_zone(zone_id)
    payload = await policy_build_zone_automation_state_payload(
        zone_id,
        load_latest_zone_task_fn=_load_latest_zone_task,
        derive_automation_state_fn=lambda task: policy_derive_automation_state(
            task,
            extract_workflow=policy_extract_workflow,
            state_idle=AUTOMATION_STATE_IDLE,
            state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
            state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
            state_ready=AUTOMATION_STATE_READY,
            state_irrigating=AUTOMATION_STATE_IRRIGATING,
            state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
        ),
        resolve_state_started_at_fn=lambda task, state: policy_resolve_state_started_at(
            task,
            state,
            coerce_datetime=policy_coerce_datetime,
            state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
            state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
            state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
            state_irrigating=AUTOMATION_STATE_IRRIGATING,
        ),
        estimate_progress_percent_fn=lambda task, state: policy_estimate_progress_percent(
            task,
            state,
            extract_workflow=policy_extract_workflow,
            to_optional_int=policy_to_optional_int,
            state_idle=AUTOMATION_STATE_IDLE,
            state_ready=AUTOMATION_STATE_READY,
            state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
            state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
            state_irrigating=AUTOMATION_STATE_IRRIGATING,
            state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
        ),
        load_zone_system_config_fn=lambda zone_id_value, task_payload: policy_load_zone_system_config(
            zone_id_value,
            task_payload,
            fetch_fn=fetch,
        ),
        load_zone_current_levels_fn=lambda zone_id_value: policy_load_zone_current_levels(
            zone_id_value,
            fetch_fn=fetch,
        ),
        derive_active_processes_fn=lambda task, state: policy_derive_active_processes(
            task,
            state,
            extract_workflow=policy_extract_workflow,
            state_tank_filling=AUTOMATION_STATE_TANK_FILLING,
            state_tank_recirc=AUTOMATION_STATE_TANK_RECIRC,
            state_irrigating=AUTOMATION_STATE_IRRIGATING,
            state_irrig_recirc=AUTOMATION_STATE_IRRIG_RECIRC,
        ),
        load_automation_timeline_fn=lambda zone_id_value: policy_load_automation_timeline(
            zone_id_value,
            fetch_fn=fetch,
            extract_timeline_reason_fn=policy_extract_timeline_reason,
            build_timeline_label_fn=lambda event_type, reason_code: policy_build_timeline_label(
                event_type,
                reason_code,
                event_labels=AUTOMATION_TIMELINE_EVENT_LABELS,
            ),
            logger=logger,
        ),
        estimate_completion_seconds_fn=lambda task: policy_estimate_completion_seconds(
            task,
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            coerce_datetime=policy_coerce_datetime,
        ),
        automation_state_labels=AUTOMATION_STATE_LABELS,
        automation_state_idle=AUTOMATION_STATE_IDLE,
        automation_state_next=AUTOMATION_STATE_NEXT,
    )
    return payload


async def _run_scheduler_task_recovery_on_startup() -> None:
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


@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": "automation-engine"}


@app.get("/health/ready")
async def health_ready():
    payload = await policy_build_readiness_payload(
        command_bus=_command_bus,
        command_bus_loop_id=_command_bus_loop_id,
        is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch,
        loop_mismatch_code=ERR_COMMAND_BUS_LOOP_MISMATCH,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        fetch_fn=fetch,
        logger=logger,
    )
    if payload["ready"]:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.post("/test/hook")
async def test_hook(req: TestHookRequest = Body(...)):
    """Test hook для детерминированных ошибок и управления состоянием."""
    return await policy_handle_test_hook(
        req,
        test_mode=_test_mode,
        test_hooks=_test_hooks,
        zone_states_override=_zone_states_override,
        logger=logger,
        command_bus=_command_bus,
        gh_uid=_gh_uid,
        command_bus_cls=CommandBus,
    )


@app.get("/test/hook/{zone_id}")
async def get_test_hook(zone_id: int):
    """Получить текущее состояние test hooks для зоны."""
    return policy_build_test_hook_state_payload(
        zone_id,
        test_mode=_test_mode,
        test_hooks=_test_hooks,
        zone_states_override=_zone_states_override,
    )


def get_test_hook_for_zone(zone_id: int, controller: str) -> Optional[Dict[str, Any]]:
    """Получить test hook для зоны и контроллера (используется в ZoneAutomationService)."""
    return policy_get_test_hook_for_zone(
        zone_id,
        controller,
        test_mode=_test_mode,
        test_hooks=_test_hooks,
    )


def get_zone_state_override(zone_id: int) -> Optional[Dict[str, Any]]:
    """Получить override состояния для зоны (используется в ZoneAutomationService)."""
    return policy_get_zone_state_override(
        zone_id,
        test_mode=_test_mode,
        zone_states_override=_zone_states_override,
    )
