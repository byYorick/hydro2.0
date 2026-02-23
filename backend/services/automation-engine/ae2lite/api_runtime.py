from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Coroutine, Dict, Optional, Set

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Gauge

from ae2lite.api_runtime_zone_routes import bind_zone_routes
from application.api_contracts import SchedulerTaskRequest, StartCycleRequest
from application.api_health import build_readiness_payload as policy_build_readiness_payload
from application.api_intents import (
    build_scheduler_task_request_from_intent as policy_build_scheduler_task_request_from_intent,
    claim_start_cycle_intent as policy_claim_start_cycle_intent,
    mark_intent_running as policy_mark_intent_running,
    mark_intent_terminal as policy_mark_intent_terminal,
)
from application.api_rate_limit import SlidingWindowRateLimiter
from application.api_recovery import (
    recover_inflight_scheduler_tasks as policy_recover_inflight_scheduler_tasks,
    recover_zone_workflow_states as policy_recover_zone_workflow_states,
)
from application.api_runtime import (
    process_trace_request as policy_process_trace_request,
    spawn_background_task as policy_spawn_background_task,
    update_command_effect_confirm_rate as policy_update_command_effect_confirm_rate,
)
from application.api_scheduler_execution import execute_scheduler_task as policy_execute_scheduler_task
from application.api_scheduler_helpers import (
    build_execution_terminal_result as policy_build_execution_terminal_result,
    new_scheduler_task_id as policy_new_scheduler_task_id,
    normalize_failed_execution_result as policy_normalize_failed_execution_result,
    task_payload_fingerprint as policy_task_payload_fingerprint,
    task_payload_matches as policy_task_payload_matches,
)
from application.api_scheduler_security import (
    validate_scheduler_security_baseline as policy_validate_scheduler_security_baseline,
)
from application.api_scheduler_store import (
    cleanup_scheduler_tasks_locked as policy_cleanup_scheduler_tasks_locked,
    create_scheduler_task as policy_create_scheduler_task,
    load_scheduler_task_by_correlation_id as policy_load_scheduler_task_by_correlation_id,
    persist_scheduler_task_snapshot as policy_persist_scheduler_task_snapshot,
    update_scheduler_task as policy_update_scheduler_task,
)
from application.api_scheduler_validation import validate_scheduler_zone as policy_validate_scheduler_zone
from application.api_start_cycle import build_start_cycle_response as policy_build_start_cycle_response
from application.api_test_hooks import (
    get_test_hook_for_zone as policy_get_test_hook_for_zone,
    get_zone_state_override as policy_get_zone_state_override,
)
from application.api_zone_task_loader import load_latest_zone_task as policy_load_latest_zone_task
from common.db import create_scheduler_log, create_zone_event, execute, fetch
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
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
_AE_START_CYCLE_RATE_LIMIT_ENABLED = _env_true("AE_START_CYCLE_RATE_LIMIT_ENABLED", "1")
_AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS = max(0, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS", "30")))
_AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC = max(1, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC", "10")))
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
    if not _background_tasks:
        return
    pending = [t for t in list(_background_tasks) if not t.done()]
    for task in pending:
        task.cancel()
    try:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=max(float(timeout_sec), 0.1))
    except asyncio.TimeoutError:
        logger.warning("Background task shutdown timeout: pending=%s", sum(1 for t in pending if not t.done()))
    finally:
        for task in list(_background_tasks):
            if task.done():
                _background_tasks.discard(task)


def _spawn_background_task(coro: Coroutine[Any, Any, Any], *, task_name: str, zone_id: Optional[int] = None, task_id: Optional[str] = None, task_type: Optional[str] = None) -> asyncio.Task:
    task = policy_spawn_background_task(coro, task_name=task_name, zone_id=zone_id, task_id=task_id, task_type=task_type, send_infra_exception_alert_fn=send_infra_exception_alert, logger=logger)
    _background_tasks.add(task)
    task.add_done_callback(lambda done_task: _background_tasks.discard(done_task))
    return task


def set_command_bus(command_bus: Optional[CommandBus], gh_uid: str, loop_id: Optional[int] = None) -> None:
    global _command_bus, _gh_uid, _command_bus_loop_id
    _command_bus, _gh_uid, _command_bus_loop_id = command_bus, gh_uid, loop_id


def set_zone_service(zone_service: Any, loop_id: Optional[int] = None) -> None:
    global _zone_service, _zone_service_loop_id
    _zone_service, _zone_service_loop_id = zone_service, loop_id


async def is_scheduler_single_writer_active() -> bool:
    if not _env_true("AE2_RUNTIME_SINGLE_WRITER_ENFORCE", "1"):
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with _scheduler_bootstrap_lock:
        stale = [k for k, v in _scheduler_bootstrap_leases.items() if not isinstance(v.get("expires_at"), datetime) or v.get("expires_at") <= now]
        for key in stale:
            _scheduler_bootstrap_leases.pop(key, None)
        return bool(_scheduler_bootstrap_leases)


def _is_loop_affinity_mismatch(assigned_loop_id: Optional[int]) -> bool:
    if assigned_loop_id is None:
        return False
    try:
        return assigned_loop_id != id(asyncio.get_running_loop())
    except RuntimeError:
        return False


async def _validate_scheduler_zone(zone_id: int) -> None:
    await policy_validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)


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


def _new_scheduler_task_id() -> str:
    return policy_new_scheduler_task_id()


def _task_payload_fingerprint(req: SchedulerTaskRequest) -> str:
    return policy_task_payload_fingerprint(req)


def _task_payload_matches(req: SchedulerTaskRequest, existing_task: Dict[str, Any], expected_fingerprint: str) -> bool:
    return policy_task_payload_matches(req, existing_task, expected_fingerprint)


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
    await policy_execute_scheduler_task(task_id, req, trace_id, command_bus=_command_bus, command_bus_loop_id=_command_bus_loop_id, zone_service=_zone_service, zone_service_loop_id=_zone_service_loop_id, is_loop_affinity_mismatch_fn=_is_loop_affinity_mismatch, update_scheduler_task_fn=_update_scheduler_task, update_command_effect_confirm_rate_fn=_update_command_effect_confirm_rate, normalize_failed_execution_result_fn=_normalize_failed_execution_result, build_execution_terminal_result_fn=_build_execution_terminal_result, send_infra_exception_alert_fn=send_infra_exception_alert, scheduler_task_executor_factory=_build_scheduler_task_executor, set_trace_id_fn=set_trace_id, logger=logger, err_command_bus_unavailable=SCHEDULER_ERR_COMMAND_BUS_UNAVAILABLE, err_command_bus_loop_mismatch=SCHEDULER_ERR_COMMAND_BUS_LOOP_MISMATCH, err_zone_service_loop_mismatch=SCHEDULER_ERR_ZONE_SERVICE_LOOP_MISMATCH, err_execution_exception=SCHEDULER_ERR_EXECUTION_EXCEPTION)


async def _load_latest_zone_task(zone_id: int) -> Optional[Dict[str, Any]]:
    return await policy_load_latest_zone_task(zone_id, scheduler_tasks_lock=_scheduler_tasks_lock, scheduler_tasks=_scheduler_tasks, cleanup_scheduler_tasks_locked_fn=_cleanup_scheduler_tasks_locked, fetch_fn=fetch, logger=logger)


@app.post("/zones/{zone_id}/start-cycle")
async def zone_start_cycle(zone_id: int, request: Request, req: StartCycleRequest = Body(...)):
    await _validate_scheduler_zone(zone_id)
    await _validate_scheduler_security_baseline(request)
    if _AE_START_CYCLE_RATE_LIMIT_ENABLED and not _start_cycle_rate_limiter.check(zone_id=zone_id, source=req.source):
        raise HTTPException(status_code=429, detail={"error": "start_cycle_rate_limited", "zone_id": zone_id, "window_sec": _AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC, "max_requests": _AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS})

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    intent_claim = await policy_claim_start_cycle_intent(zone_id=zone_id, req=req, now=now, fetch_fn=fetch)
    intent = intent_claim.get("intent") if isinstance(intent_claim, dict) and isinstance(intent_claim.get("intent"), dict) else {}
    decision = str(intent_claim.get("decision") if isinstance(intent_claim, dict) else "").strip().lower()
    if decision in {"deduplicated", "terminal"}:
        intent_id = int(intent.get("id") or 0)
        return policy_build_start_cycle_response(zone_id=zone_id, req=req, is_duplicate=True, task_id=f"intent-{intent_id}" if intent_id > 0 else "")

    start_cycle_req = policy_build_scheduler_task_request_from_intent(zone_id=zone_id, req=req, intent_row=intent, now=now, due_in_sec=_START_CYCLE_DUE_SEC, expires_in_sec=_START_CYCLE_EXPIRES_SEC, default_topology=DEFAULT_TWO_TANK_TOPOLOGY)
    task, is_duplicate = await _create_scheduler_task(start_cycle_req)
    task_id = str(task.get("task_id") or "")
    intent_id = int(intent.get("id") or 0)
    if not is_duplicate and task_id:
        trace_id = get_trace_id()

        async def _run_start_cycle_intent() -> None:
            if intent_id > 0:
                await policy_mark_intent_running(intent_id=intent_id, now=datetime.now(timezone.utc).replace(tzinfo=None), execute_fn=execute)
            await _execute_scheduler_task(task_id, start_cycle_req, trace_id)
            snapshot = _scheduler_tasks.get(task_id) if isinstance(_scheduler_tasks.get(task_id), dict) else {}
            if intent_id > 0:
                await policy_mark_intent_terminal(intent_id=intent_id, now=datetime.now(timezone.utc).replace(tzinfo=None), success=str(snapshot.get("status") or "").strip().lower() == "completed", error_code=str(snapshot.get("error_code") or "") or None, error_message=str(snapshot.get("error") or "") or None, execute_fn=execute)

        _spawn_background_task(_run_start_cycle_intent(), task_name=f"start_cycle_intent_{intent_id or task_id}", zone_id=zone_id)

    return policy_build_start_cycle_response(zone_id=zone_id, req=req, is_duplicate=bool(is_duplicate), task_id=f"intent-{intent_id}" if intent_id > 0 else task_id)


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


def get_test_hook_for_zone(zone_id: int, controller: str) -> Optional[Dict[str, Any]]:
    return policy_get_test_hook_for_zone(zone_id, controller, test_mode=_test_mode, test_hooks=_test_hooks)


def get_zone_state_override(zone_id: int) -> Optional[Dict[str, Any]]:
    return policy_get_zone_state_override(zone_id, test_mode=_test_mode, zone_states_override=_zone_states_override)


(zone_automation_state, zone_automation_control_mode, zone_automation_set_control_mode, zone_automation_manual_step) = bind_zone_routes(
    app,
    validate_scheduler_zone_fn=_validate_scheduler_zone,
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


__all__ = [
    "app",
    "zone_start_cycle",
    "zone_automation_state",
    "zone_automation_control_mode",
    "zone_automation_set_control_mode",
    "zone_automation_manual_step",
    "health_live",
    "health_ready",
    "set_command_bus",
    "set_zone_service",
    "is_scheduler_single_writer_active",
    "get_test_hook_for_zone",
    "get_zone_state_override",
    "_scheduler_tasks",
    "_validate_scheduler_zone",
    "_validate_scheduler_security_baseline",
    "_create_scheduler_task",
    "_spawn_background_task",
    "_execute_scheduler_task",
    "policy_claim_start_cycle_intent",
    "policy_mark_intent_running",
    "policy_mark_intent_terminal",
    "_AE_START_CYCLE_RATE_LIMIT_ENABLED",
    "_start_cycle_rate_limiter",
]
