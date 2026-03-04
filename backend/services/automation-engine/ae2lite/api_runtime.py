from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Coroutine, Dict, Optional, Set

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import Gauge

from ae2lite.api_runtime_start_cycle import bind_start_cycle_route
from ae2lite.api_runtime_zone_routes import bind_zone_routes
from ae2lite.api_runtime_concurrency import (
    build_scheduler_single_writer_lease_key as policy_build_scheduler_single_writer_lease_key,
    drain_background_tasks as policy_drain_background_tasks,
    execute_scheduler_task_with_single_writer_lease as policy_execute_scheduler_task_with_single_writer_lease,
    is_scheduler_single_writer_active as policy_is_scheduler_single_writer_active,
    release_scheduler_single_writer_lease as policy_release_scheduler_single_writer_lease,
    set_scheduler_single_writer_lease as policy_set_scheduler_single_writer_lease,
    spawn_background_task as policy_spawn_runtime_background_task,
)
from ae2lite.api_contracts import SchedulerTaskRequest, StartCycleRequest
from ae2lite.api_health import build_readiness_payload as policy_build_readiness_payload
from ae2lite.api_intents import (
    build_scheduler_task_request_from_intent as policy_build_scheduler_task_request_from_intent,
    claim_start_cycle_intent as policy_claim_start_cycle_intent,
    mark_intent_pending as policy_mark_intent_pending,
    mark_intent_running as policy_mark_intent_running,
    mark_intent_terminal as policy_mark_intent_terminal,
)
from ae2lite.api_rate_limit import SlidingWindowRateLimiter
from ae2lite.api_recovery import (
    recover_inflight_scheduler_tasks as policy_recover_inflight_scheduler_tasks,
    recover_zone_workflow_states as policy_recover_zone_workflow_states,
)
from ae2lite.policy_runtime import (
    process_trace_request as policy_process_trace_request,
    spawn_background_task as policy_spawn_background_task,
    update_command_effect_confirm_rate as policy_update_command_effect_confirm_rate,
)
from ae2lite.api_scheduler_execution import execute_scheduler_task as policy_execute_scheduler_task
from ae2lite.api_scheduler_helpers import (
    build_execution_terminal_result as policy_build_execution_terminal_result,
    new_scheduler_task_id as policy_new_scheduler_task_id,
    normalize_failed_execution_result as policy_normalize_failed_execution_result,
    task_payload_fingerprint as policy_task_payload_fingerprint,
    task_payload_matches as policy_task_payload_matches,
)
from ae2lite.api_scheduler_security import (
    validate_scheduler_security_baseline as policy_validate_scheduler_security_baseline,
)
from ae2lite.api_scheduler_store import (
    cleanup_scheduler_tasks_locked as policy_cleanup_scheduler_tasks_locked,
    create_scheduler_task as policy_create_scheduler_task,
    load_scheduler_task_by_correlation_id as policy_load_scheduler_task_by_correlation_id,
    persist_scheduler_task_snapshot as policy_persist_scheduler_task_snapshot,
    update_scheduler_task as policy_update_scheduler_task,
)
from ae2lite.api_scheduler_validation import validate_scheduler_zone as policy_validate_scheduler_zone
from ae2lite.api_start_cycle import build_start_cycle_response as policy_build_start_cycle_response
from ae2lite.api_test_hooks import (
    get_test_hook_for_zone as policy_get_test_hook_for_zone,
    get_zone_state_override as policy_get_zone_state_override,
)
from ae2lite.api_zone_task_loader import load_latest_zone_task as policy_load_latest_zone_task
from common.db import create_scheduler_log, create_zone_event, execute, fetch
from common.infra_alerts import send_infra_alert, send_infra_exception_alert, send_infra_resolved_alert
from common.trace_context import extract_trace_id_from_headers
from infrastructure import CommandBus
from infrastructure.workflow_state_store import WorkflowStateStore
from scheduler_internal_enqueue import enqueue_internal_scheduler_task
from scheduler_task_executor import SchedulerTaskExecutor
from services.resilience_contract import (
    SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH,
    SCHEDULER_ERR_COMMAND_BUS_UNAVAILABLE,
    SCHEDULER_ERR_EXECUTION_EXCEPTION,
    SCHEDULER_ERR_TASK_EXECUTION_FAILED,
    SCHEDULER_ERR_ZONE_NOT_FOUND,
    SCHEDULER_ERR_ZONE_SERVICE_LOOP_MISMATCH,
)
from utils.logging_context import get_trace_id, set_trace_id

logger = logging.getLogger(__name__)
DEFAULT_TWO_TANK_TOPOLOGY = "two_tank_drip_substrate_trays"


def _env_true(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def _app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    await _run_scheduler_task_recovery_on_startup()
    try:
        yield
    finally:
        await _drain_background_tasks()


app = FastAPI(title="Automation Engine API", lifespan=_app_lifespan)
_APP_ENV = str(os.getenv("APP_ENV", "local")).strip().lower()
_AE_VERBOSE_HTTP_LOGGING = _env_true("AE_DEV_VERBOSE_HTTP_LOGGING", "1" if _APP_ENV in {"local", "dev", "development"} else "0")


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


_command_bus: Optional[CommandBus] = None
_gh_uid = ""
_zone_service: Optional[Any] = None
_command_bus_loop_id: Optional[int] = None
_zone_service_loop_id: Optional[int] = None
_scheduler_tasks: Dict[str, Dict[str, Any]] = {}
_scheduler_tasks_lock = asyncio.Lock()
_SCHEDULER_TASK_TTL_SECONDS = max(60, int(os.getenv("SCHEDULER_TASK_TTL_SECONDS", "3600")))
_SCHEDULER_TASK_MAX_IN_MEMORY = max(100, int(os.getenv("SCHEDULER_TASK_MAX_IN_MEMORY", "5000")))
_SCHEDULER_DEDUPE_WINDOW_SEC = max(60, int(os.getenv("SCHEDULER_DEDUPE_WINDOW_SEC", "86400")))
_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE = _env_true("AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", "1")
_AE_SCHEDULER_REQUIRE_TRACE_ID = _env_true("AE_SCHEDULER_REQUIRE_TRACE_ID", "1")
_AE_SCHEDULER_API_TOKEN = str(os.getenv("SCHEDULER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN") or os.getenv("PY_API_TOKEN") or "").strip()
_START_CYCLE_DUE_SEC = max(5, int(os.getenv("AE_START_CYCLE_DUE_SEC", "60")))
_START_CYCLE_EXPIRES_SEC = max(_START_CYCLE_DUE_SEC + 5, int(os.getenv("AE_START_CYCLE_EXPIRES_SEC", "900")))
_START_CYCLE_CLAIM_STALE_SEC = max(30, int(os.getenv("AE_START_CYCLE_CLAIM_STALE_SEC", "180")))
_AE_START_CYCLE_RATE_LIMIT_ENABLED = _env_true("AE_START_CYCLE_RATE_LIMIT_ENABLED", "1")
_AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS = max(0, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS", "30")))
_AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC = max(1, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC", "10")))
_AE2_SCHEDULER_SINGLE_WRITER_LEASE_TTL_SEC = max(30, int(os.getenv("AE2_SCHEDULER_SINGLE_WRITER_LEASE_TTL_SEC", "300")))
_AE2_SCHEDULER_SINGLE_WRITER_LEASE_REFRESH_SEC = max(5, min(_AE2_SCHEDULER_SINGLE_WRITER_LEASE_TTL_SEC - 1, int(os.getenv("AE2_SCHEDULER_SINGLE_WRITER_LEASE_REFRESH_SEC", "15"))))
_scheduler_bootstrap_leases: Dict[str, Dict[str, Any]] = {}
_scheduler_bootstrap_lock = asyncio.Lock()
_AE_TASK_RECOVERY_ENABLED = _env_true("AE_TASK_RECOVERY_ENABLED", "1")
_AE_TASK_RECOVERY_SCAN_LIMIT = max(10, int(os.getenv("AE_TASK_RECOVERY_SCAN_LIMIT", "500")))
_AE_WORKFLOW_STATE_RECOVERY_ENABLED = _env_true("AE_WORKFLOW_STATE_RECOVERY_ENABLED", "1")
_AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = max(60, int(os.getenv("AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC", "1800")))
TASK_RECOVERY_SUCCESS_RATE = Gauge("task_recovery_success_rate", "Share of startup recovery tasks finalized successfully")
COMMAND_EFFECT_CONFIRM_RATE = Gauge("command_effect_confirm_rate", "Share of commands confirmed by node DONE for closed-loop scheduler tasks", ["task_type"])
_command_effect_totals: Dict[str, int] = {}
_command_effect_confirmed_totals: Dict[str, int] = {}
_workflow_state_store = WorkflowStateStore()
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}
_zone_states_override: Dict[int, Dict[str, Any]] = {}
_background_tasks: Set[asyncio.Task] = set()
_start_cycle_rate_limiter = SlidingWindowRateLimiter(max_requests=_AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS, window_sec=float(_AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC))


async def _drain_background_tasks(timeout_sec: float = 5.0) -> None:
    await policy_drain_background_tasks(
        background_tasks=_background_tasks,
        logger=logger,
        timeout_sec=timeout_sec,
    )


def _spawn_background_task(coro: Coroutine[Any, Any, Any], *, task_name: str, zone_id: Optional[int] = None, task_id: Optional[str] = None, task_type: Optional[str] = None) -> asyncio.Task:
    return policy_spawn_runtime_background_task(
        coro,
        task_name=task_name,
        zone_id=zone_id,
        task_id=task_id,
        task_type=task_type,
        background_tasks=_background_tasks,
        spawn_policy_fn=policy_spawn_background_task,
        send_infra_exception_alert_fn=send_infra_exception_alert,
        logger=logger,
    )


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str, loop_id: Optional[int] = None) -> None:
    global _command_bus, _gh_uid, _command_bus_loop_id
    _command_bus, _gh_uid, _command_bus_loop_id = command_bus, gh_uid, loop_id


def set_zone_service(zone_service: Any, loop_id: Optional[int] = None) -> None:
    global _zone_service, _zone_service_loop_id
    _zone_service, _zone_service_loop_id = zone_service, loop_id


async def is_scheduler_single_writer_active(zone_id: Optional[int] = None) -> bool:
    return await policy_is_scheduler_single_writer_active(
        enforce=_env_true("AE2_RUNTIME_SINGLE_WRITER_ENFORCE", "1"),
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        zone_id=zone_id,
    )


def _build_scheduler_single_writer_lease_key(*, zone_id: int, intent_id: int, task_id: str) -> str:
    return policy_build_scheduler_single_writer_lease_key(
        zone_id=zone_id,
        intent_id=intent_id,
        task_id=task_id,
    )


async def _set_scheduler_single_writer_lease(*, lease_key: str, zone_id: int, intent_id: int, task_id: str) -> None:
    await policy_set_scheduler_single_writer_lease(
        lease_key=lease_key,
        zone_id=zone_id,
        intent_id=intent_id,
        task_id=task_id,
        lease_ttl_sec=_AE2_SCHEDULER_SINGLE_WRITER_LEASE_TTL_SEC,
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
    )


async def _release_scheduler_single_writer_lease(lease_key: str) -> None:
    await policy_release_scheduler_single_writer_lease(
        lease_key=lease_key,
        scheduler_bootstrap_lock=_scheduler_bootstrap_lock,
        scheduler_bootstrap_leases=_scheduler_bootstrap_leases,
    )
async def _execute_scheduler_task_with_single_writer_lease(
    task_id: str,
    req: SchedulerTaskRequest,
    trace_id: Optional[str],
    *,
    lease_key: str,
    zone_id: int,
    intent_id: int,
) -> None:
    await policy_execute_scheduler_task_with_single_writer_lease(
        task_id,
        req,
        trace_id,
        lease_key=lease_key,
        zone_id=zone_id,
        intent_id=intent_id,
        execute_scheduler_task_fn=_execute_scheduler_task,
        set_scheduler_single_writer_lease_fn=_set_scheduler_single_writer_lease,
        lease_refresh_sec=_AE2_SCHEDULER_SINGLE_WRITER_LEASE_REFRESH_SEC,
    )
def _is_loop_affinity_mismatch(assigned_loop_id: Optional[int]) -> bool:
    if assigned_loop_id is None:
        return False
    try:
        return assigned_loop_id != id(asyncio.get_running_loop())
    except RuntimeError:
        return False
async def _validate_scheduler_zone(zone_id: int) -> None:
    await policy_validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)
async def _scheduler_zone_exists(zone_id: int) -> bool:
    rows = await fetch(
        """
        SELECT 1
        FROM zones
        WHERE id = $1
        LIMIT 1
        """,
        zone_id,
    )
    return bool(rows)
async def _validate_scheduler_security_baseline(request: Request) -> None:
    policy_validate_scheduler_security_baseline(headers=request.headers, enforce=_AE_SCHEDULER_SECURITY_BASELINE_ENFORCE, scheduler_api_token=_AE_SCHEDULER_API_TOKEN, require_trace_id=_AE_SCHEDULER_REQUIRE_TRACE_ID, extract_trace_id_from_headers_fn=extract_trace_id_from_headers)
def _normalize_cleanup_timestamp(raw_value: Any, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw_value))
    except Exception:
        return fallback
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo is not None else parsed
async def _cleanup_scheduler_tasks_locked(now: datetime) -> None:
    await policy_cleanup_scheduler_tasks_locked(now, scheduler_tasks=_scheduler_tasks, scheduler_task_ttl_seconds=_SCHEDULER_TASK_TTL_SECONDS, scheduler_task_max_in_memory=_SCHEDULER_TASK_MAX_IN_MEMORY, normalize_cleanup_timestamp_fn=_normalize_cleanup_timestamp)
async def _load_scheduler_task_by_correlation_id(correlation_id: str) -> Optional[Dict[str, Any]]:
    return await policy_load_scheduler_task_by_correlation_id(correlation_id, fetch_fn=fetch, scheduler_dedupe_window_sec=_SCHEDULER_DEDUPE_WINDOW_SEC, logger=logger)
_new_scheduler_task_id = policy_new_scheduler_task_id
_task_payload_fingerprint = policy_task_payload_fingerprint
_task_payload_matches = policy_task_payload_matches
async def _persist_scheduler_task_snapshot(task: Dict[str, Any]) -> None:
    await policy_persist_scheduler_task_snapshot(task, create_scheduler_log_fn=create_scheduler_log, logger=logger)
async def _create_scheduler_task(req: SchedulerTaskRequest, *, initial_status: str = "accepted", initial_result: Optional[Dict[str, Any]] = None, initial_error: Optional[str] = None, initial_error_code: Optional[str] = None):
    return await policy_create_scheduler_task(req, scheduler_tasks=_scheduler_tasks, scheduler_tasks_lock=_scheduler_tasks_lock, cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked, load_scheduler_task_by_correlation_id_fn=_load_scheduler_task_by_correlation_id, task_payload_fingerprint_fn=_task_payload_fingerprint, task_payload_matches_fn=_task_payload_matches, new_scheduler_task_id_fn=_new_scheduler_task_id, persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot, initial_status=initial_status, initial_result=initial_result, initial_error=initial_error, initial_error_code=initial_error_code)
async def _update_scheduler_task(*, task_id: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None, error_code: Optional[str] = None) -> None:
    await policy_update_scheduler_task(task_id=task_id, status=status, scheduler_tasks=_scheduler_tasks, scheduler_tasks_lock=_scheduler_tasks_lock, persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot, result=result, error=error, error_code=error_code)
def _build_execution_terminal_result(*, error_code: str, reason: str, mode: str, action_required: bool = True, decision: str = "fail", reason_code: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return policy_build_execution_terminal_result(error_code=error_code, reason=reason, mode=mode, action_required=action_required, decision=decision, reason_code=reason_code, extra=extra)
def _normalize_failed_execution_result(result: Dict[str, Any]) -> Dict[str, Any]:
    return policy_normalize_failed_execution_result(result, err_task_execution_failed=SCHEDULER_ERR_TASK_EXECUTION_FAILED)
def _update_command_effect_confirm_rate(task_type: str, result: Dict[str, Any]) -> None:
    policy_update_command_effect_confirm_rate(task_type, result, command_effect_totals=_command_effect_totals, command_effect_confirmed_totals=_command_effect_confirmed_totals, command_effect_confirm_rate_metric=COMMAND_EFFECT_CONFIRM_RATE)
def _build_scheduler_task_executor(*, command_bus: CommandBus, zone_service: Optional[Any]) -> SchedulerTaskExecutor:
    return SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)
async def _execute_scheduler_task(task_id: str, req: SchedulerTaskRequest, trace_id: Optional[str]) -> None:
    await policy_execute_scheduler_task(task_id, req, trace_id, command_bus=_command_bus, command_bus_loop_id=_command_bus_loop_id, zone_service=_zone_service, zone_service_loop_id=_zone_service_loop_id, validate_zone_exists_fn=_scheduler_zone_exists, is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch, update_scheduler_task_fn=_update_scheduler_task, update_command_effect_confirm_rate_fn=_update_command_effect_confirm_rate, normalize_failed_execution_result_fn=_normalize_failed_execution_result, build_execution_terminal_result_fn=_build_execution_terminal_result, send_infra_exception_alert_fn=send_infra_exception_alert, send_infra_resolved_alert_fn=send_infra_resolved_alert, scheduler_task_executor_factory=_build_scheduler_task_executor, set_trace_id_fn=set_trace_id, logger=logger, err_command_bus_unavailable=SCHEDULER_ERR_COMMAND_BUS_UNAVAILABLE, err_command_bus_loop_mismatch=SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH, err_zone_service_loop_mismatch=SCHEDULER_ERR_ZONE_SERVICE_LOOP_MISMATCH, err_zone_not_found=SCHEDULER_ERR_ZONE_NOT_FOUND, err_execution_exception=SCHEDULER_ERR_EXECUTION_EXCEPTION)
async def _load_latest_zone_task(zone_id: int) -> Optional[Dict[str, Any]]:
    return await policy_load_latest_zone_task(zone_id, scheduler_tasks_lock=_scheduler_tasks_lock, scheduler_tasks=_scheduler_tasks, cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked, fetch_fn=fetch, logger=logger)


_is_start_cycle_rate_limit_enabled = lambda: bool(_AE_START_CYCLE_RATE_LIMIT_ENABLED)
_start_cycle_rate_limit_check = lambda zone_id: bool(_start_cycle_rate_limiter.check(zone_id=zone_id))
_start_cycle_rate_limit_window_sec = lambda: int(_AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC)
_start_cycle_rate_limit_max_requests = lambda: int(_AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS)
_start_cycle_claim_stale_sec = lambda: int(_START_CYCLE_CLAIM_STALE_SEC)
_start_cycle_due_sec = lambda: int(_START_CYCLE_DUE_SEC)
_start_cycle_expires_sec = lambda: int(_START_CYCLE_EXPIRES_SEC)


zone_start_cycle = bind_start_cycle_route(
    app,
    validate_scheduler_zone_fn=lambda zone_id: _validate_scheduler_zone(zone_id),
    validate_scheduler_security_baseline_fn=lambda request: _validate_scheduler_security_baseline(request),
    is_start_cycle_rate_limit_enabled_fn=_is_start_cycle_rate_limit_enabled,
    start_cycle_rate_limit_check_fn=_start_cycle_rate_limit_check,
    start_cycle_rate_limit_window_sec_fn=_start_cycle_rate_limit_window_sec,
    start_cycle_rate_limit_max_requests_fn=_start_cycle_rate_limit_max_requests,
    claim_start_cycle_intent_fn=lambda *, zone_id, req, now, claimed_stale_after_sec: policy_claim_start_cycle_intent(zone_id=zone_id, req=req, now=now, claimed_stale_after_sec=claimed_stale_after_sec, fetch_fn=fetch),
    start_cycle_claim_stale_sec_fn=_start_cycle_claim_stale_sec,
    load_latest_zone_task_fn=lambda zone_id: _load_latest_zone_task(zone_id),
    load_zone_workflow_state_fn=lambda zone_id: _workflow_state_store.get(zone_id),
    build_scheduler_task_request_from_intent_fn=policy_build_scheduler_task_request_from_intent,
    start_cycle_due_sec_fn=_start_cycle_due_sec,
    start_cycle_expires_sec_fn=_start_cycle_expires_sec,
    default_topology=DEFAULT_TWO_TANK_TOPOLOGY,
    create_scheduler_task_fn=lambda req: _create_scheduler_task(req),
    get_trace_id_fn=get_trace_id,
    build_scheduler_single_writer_lease_key_fn=lambda *, zone_id, intent_id, task_id: _build_scheduler_single_writer_lease_key(zone_id=zone_id, intent_id=intent_id, task_id=task_id),
    set_scheduler_single_writer_lease_fn=lambda *, lease_key, zone_id, intent_id, task_id: _set_scheduler_single_writer_lease(lease_key=lease_key, zone_id=zone_id, intent_id=intent_id, task_id=task_id),
    execute_scheduler_task_with_single_writer_lease_fn=lambda task_id, req, trace_id, *, lease_key, zone_id, intent_id: _execute_scheduler_task_with_single_writer_lease(task_id, req, trace_id, lease_key=lease_key, zone_id=zone_id, intent_id=intent_id),
    release_scheduler_single_writer_lease_fn=_release_scheduler_single_writer_lease,
    mark_intent_running_fn=lambda **kwargs: policy_mark_intent_running(**kwargs),
    mark_intent_terminal_fn=lambda **kwargs: policy_mark_intent_terminal(**kwargs),
    mark_intent_pending_fn=lambda **kwargs: policy_mark_intent_pending(**kwargs),
    execute_fn=execute,
    scheduler_tasks_ref=_scheduler_tasks,
    build_execution_terminal_result_fn=_build_execution_terminal_result,
    update_scheduler_task_fn=lambda **kwargs: _update_scheduler_task(**kwargs),
    spawn_background_task_fn=lambda coro, **kwargs: _spawn_background_task(coro, **kwargs),
    build_start_cycle_response_fn=policy_build_start_cycle_response,
    scheduler_err_execution_exception=SCHEDULER_ERR_EXECUTION_EXCEPTION,
    logger=logger,
)


async def _run_scheduler_task_recovery_on_startup() -> None:
    await policy_recover_inflight_scheduler_tasks(enabled=_AE_TASK_RECOVERY_ENABLED, fetch_fn=fetch, scan_limit=_AE_TASK_RECOVERY_SCAN_LIMIT, build_execution_terminal_result_fn=_build_execution_terminal_result, scheduler_tasks=_scheduler_tasks, scheduler_tasks_lock=_scheduler_tasks_lock, persist_scheduler_task_snapshot_fn=_persist_scheduler_task_snapshot, create_zone_event_fn=create_zone_event, send_infra_exception_alert_fn=send_infra_exception_alert, task_recovery_success_rate_gauge=TASK_RECOVERY_SUCCESS_RATE, logger=logger)
    await policy_recover_zone_workflow_states(enabled=_AE_WORKFLOW_STATE_RECOVERY_ENABLED, stale_timeout_sec=_AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC, workflow_state_store=_workflow_state_store, logger=logger, create_zone_event_fn=create_zone_event, enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task, send_infra_exception_alert_fn=send_infra_exception_alert, get_trace_id_fn=get_trace_id)


@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": "automation-engine"}


@app.get("/health/ready")
async def health_ready():
    payload = await policy_build_readiness_payload(command_bus=_command_bus, command_bus_loop_id=_command_bus_loop_id, is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch, loop_mismatch_code=SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH, scheduler_bootstrap_leases=_scheduler_bootstrap_leases, scheduler_bootstrap_lock=_scheduler_bootstrap_lock, fetch_fn=fetch, logger=logger)
    return payload if payload.get("ready") else JSONResponse(status_code=503, content=payload)


get_test_hook_for_zone = lambda zone_id, controller: policy_get_test_hook_for_zone(zone_id, controller, test_mode=_test_mode, test_hooks=_test_hooks)
get_zone_state_override = lambda zone_id: policy_get_zone_state_override(zone_id, test_mode=_test_mode, zone_states_override=_zone_states_override)


(zone_automation_state, zone_automation_control_mode, zone_automation_set_control_mode, zone_automation_manual_step) = bind_zone_routes(
    app,
    validate_scheduler_zone_fn=_validate_scheduler_zone,
    validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
    load_latest_zone_task_fn=_load_latest_zone_task,
    create_scheduler_task_fn=_create_scheduler_task,
    execute_scheduler_task_fn=_execute_scheduler_task,
    spawn_background_task_fn=_spawn_background_task,
    workflow_state_store=_workflow_state_store,
    default_topology=DEFAULT_TWO_TANK_TOPOLOGY,
    fetch_fn=fetch,
    create_zone_event_fn=create_zone_event,
    get_trace_id_fn=get_trace_id,
    logger=logger,
)
