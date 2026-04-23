"""Standalone FastAPI-приложение для runtime AE3-Lite."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Mapping, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field

from ae3lite.api import (
    bind_internal_task_route,
    bind_start_cycle_route,
    bind_start_irrigation_route,
    bind_start_lighting_tick_route,
)
from ae3lite.application.level_monitor import level_snapshot_aliases
from ae3lite.api.rate_limit import SlidingWindowRateLimiter
from ae3lite.api.responses import build_start_cycle_response
from ae3lite.api.security import validate_scheduler_security_baseline
from ae3lite.api.validation import validate_scheduler_zone
from ae3lite.domain.errors import ManualControlError
from ae3lite.infrastructure.intent_status_listener import IntentStatusListener
from ae3lite.infrastructure.metrics import NODE_RUNTIME_EVENT_KICK, initialize_counter_series
from ae3lite.infrastructure.zone_event_listener import ZoneEventListener
from ae3lite.runtime.bootstrap import build_ae3_runtime_bundle
from ae3lite.runtime.env import Ae3RuntimeConfig
import asyncpg

from common.db import fetch, get_pool
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.service_logs import send_service_log
from common.trace_context import clear_trace_id, extract_trace_id_from_headers, set_trace_id
from common.utils.time import utcnow_naive as _utcnow

logger = logging.getLogger(__name__)


class ControlModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_mode: str = Field(..., min_length=1, max_length=16, pattern="^(auto|semi|manual)$")
    source: str = Field(default="laravel_api", min_length=1, max_length=64)
    user_id: Optional[int] = Field(default=None, ge=0)
    user_role: Optional[str] = Field(default=None, min_length=1, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=500)


class ManualStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_step: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern="^(clean_fill_start|clean_fill_stop|solution_fill_start|force_solution_fill_start|solution_fill_stop|prepare_recirculation_start|prepare_recirculation_stop|irrigation_stop|irrigation_recovery_stop)$",
    )
    source: str = Field(default="laravel_manual_step", min_length=1, max_length=64)


class BackgroundTaskLimitError(RuntimeError):
    """Выбрасывается, когда AE3 отказывается создавать новые отслеживаемые фоновые задачи."""


async def _drain_background_tasks(background_tasks: set[asyncio.Task], timeout_sec: float = 5.0) -> None:
    pending = [task for task in background_tasks if not task.done()]
    if not pending:
        return

    for task in pending:
        task.cancel()

    try:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout_sec)
    except asyncio.TimeoutError:
        logger.warning("Превышено время ожидания завершения фоновых задач AE3: pending=%s", len(pending))
    finally:
        background_tasks.difference_update(pending)


_BACKGROUND_TASKS_SIZE_LIMIT = 256


def _close_coro(coro: Any) -> None:
    close = getattr(coro, "close", None)
    if callable(close):
        close()


def _spawn_background_task(
    coro: Any,
    *,
    task_name: str,
    background_tasks: set[asyncio.Task],
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> asyncio.Task:
    completed_tasks = {task for task in background_tasks if task.done()}
    if completed_tasks:
        background_tasks.difference_update(completed_tasks)
    active_count = len(background_tasks)
    if active_count >= _BACKGROUND_TASKS_SIZE_LIMIT:
        logger.error(
            "AE3 background_tasks limit exceeded: limit=%s active=%s task_name=%s; "
            "rejecting spawn to fail closed",
            _BACKGROUND_TASKS_SIZE_LIMIT,
            active_count,
            task_name,
        )
        _close_coro(coro)
        raise BackgroundTaskLimitError(
            f"ae3_background_task_limit_exceeded: task_name={task_name} active={active_count} limit={_BACKGROUND_TASKS_SIZE_LIMIT}"
        )
    task = asyncio.create_task(coro, name=str(task_name))
    background_tasks.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        background_tasks.discard(done_task)
        if done_task.cancelled():
            return
        try:
            exc = done_task.exception()
        except Exception as callback_exc:
            logger.error(
                "Не удалось проверить результат фоновой задачи AE3: task_name=%s error=%s",
                task_name,
                callback_exc,
                exc_info=True,
            )
            return
        if exc is None:
            return

        logger.error(
            "AE3 background task crashed: task_name=%s zone_id=%s task_id=%s task_type=%s error=%s",
            task_name,
            zone_id,
            task_id,
            task_type,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        async def _send_alert() -> None:
            await send_infra_exception_alert(
                error=exc,
                code="ae3_background_task_crashed",
                alert_type="AE3 Background Task Crashed",
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

        try:
            asyncio.create_task(_send_alert())
        except Exception:
            logger.warning(
                "Не удалось запланировать alert для аварийно завершившейся фоновой задачи AE3: task_name=%s",
                task_name,
                exc_info=True,
            )

    task.add_done_callback(_on_done)
    return task


def _build_intent_listener_callback(*, worker: Any, logger: logging.Logger) -> Any:
    async def _on_terminal_intent(data: dict[str, Any]) -> None:
        intent_id = data.get("intent_id")
        zone_id = data.get("zone_id")
        status = data.get("status")
        logger.info(
            "IntentStatusListener: terminal intent received intent_id=%s zone_id=%s status=%s; kicking worker",
            intent_id,
            zone_id,
            status,
        )
        worker.kick()

    return _on_terminal_intent


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if float(value) == 1.0:
            return True
        if float(value) == 0.0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _is_runtime_zone_event_relevant(data: Mapping[str, Any]) -> bool:
    if str(data.get("source") or "").strip().lower() != "node_event":
        return False
    event_type = str(data.get("event_type") or "").strip().upper()
    channel = str(data.get("channel") or "").strip().lower()
    return event_type == "LEVEL_SWITCH_CHANGED" or channel == "storage_state"


def _zone_event_indicates_solution_min_depletion(data: Mapping[str, Any]) -> bool:
    channel = str(data.get("channel") or "").strip().lower()
    state = _coerce_optional_bool(data.get("state"))
    if channel and channel in level_snapshot_aliases("level_solution_min") and state is False:
        return True

    snapshot = data.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return False
    for alias in level_snapshot_aliases("level_solution_min"):
        if alias not in snapshot:
            continue
        if _coerce_optional_bool(snapshot.get(alias)) is False:
            return True
    return False


def _build_zone_event_listener_callback(
    *,
    worker: Any,
    solution_tank_startup_guard_use_case: Any | None,
    now_fn: Any,
    logger: logging.Logger,
) -> Any:
    async def _on_zone_event(data: dict[str, Any]) -> None:
        if not _is_runtime_zone_event_relevant(data):
            return

        zone_id_raw = data.get("zone_id")
        try:
            zone_id = int(zone_id_raw)
        except (TypeError, ValueError):
            zone_id = 0
        event_type = str(data.get("event_type") or "").strip().upper()
        channel = str(data.get("channel") or "").strip().lower()

        if zone_id > 0 and solution_tank_startup_guard_use_case is not None and _zone_event_indicates_solution_min_depletion(data):
            try:
                guard_result = await solution_tank_startup_guard_use_case.run(zone_id=zone_id, now=now_fn())
                logger.info(
                    "ZoneEventListener: solution tank guard evaluated zone_id=%s reset=%s reason=%s",
                    zone_id,
                    bool(guard_result.get("reset")),
                    guard_result.get("reason"),
                )
            except Exception as exc:
                logger.warning(
                    "ZoneEventListener: startup guard failed for zone_id=%s event_type=%s channel=%s error=%s",
                    zone_id,
                    event_type,
                    channel,
                    exc,
                    exc_info=True,
                )

        logger.info(
            "ZoneEventListener: node runtime event received zone_id=%s event_type=%s channel=%s state=%s initial=%s; kicking worker",
            zone_id if zone_id > 0 else None,
            event_type,
            channel or None,
            data.get("state"),
            data.get("initial"),
        )
        NODE_RUNTIME_EVENT_KICK.labels(
            event_type=event_type or "UNKNOWN",
            channel=channel or "unknown",
        ).inc()
        send_service_log(
            service="automation-engine",
            level="info",
            message="AE3 worker.kick by node runtime event",
            context={
                "zone_id": zone_id if zone_id > 0 else None,
                "event_type": event_type,
                "channel": channel or None,
                "state": data.get("state"),
                "initial": data.get("initial"),
            },
        )
        worker.kick()

    return _on_zone_event


def _validate_runtime_config(runtime_config: Any) -> None:
    validate = getattr(runtime_config, "validate", None)
    if callable(validate):
        validate()


def _critical_background_tasks_health(background_tasks: Mapping[str, Any]) -> tuple[bool, str]:
    if not background_tasks:
        return True, "ok"
    for task_name, task in background_tasks.items():
        if task is None:
            return False, f"{task_name}:missing"
        done = getattr(task, "done", None)
        if not callable(done):
            return False, f"{task_name}:invalid"
        if not done():
            continue
        cancelled = getattr(task, "cancelled", None)
        if callable(cancelled) and cancelled():
            return False, f"{task_name}:cancelled"
        exception = getattr(task, "exception", None)
        if callable(exception):
            try:
                exc = exception()
            except Exception:
                return False, f"{task_name}:exception_unknown"
            if exc is not None:
                return False, f"{task_name}:crashed:{type(exc).__name__}"
        return False, f"{task_name}:stopped"
    return True, "ok"


def create_app(config: Optional[Ae3RuntimeConfig] = None) -> FastAPI:
    runtime_config = config or Ae3RuntimeConfig.from_env()
    _validate_runtime_config(runtime_config)
    background_tasks: set[asyncio.Task] = set()
    critical_background_tasks: dict[str, asyncio.Task] = {}
    rate_limiter = SlidingWindowRateLimiter(
        max_requests=runtime_config.start_cycle_rate_limit_max_requests,
        window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
    )

    bundle = build_ae3_runtime_bundle(
        config=runtime_config,
        spawn_background_task_fn=lambda coro, **kwargs: _spawn_background_task(
            coro,
            background_tasks=background_tasks,
            task_name=str(kwargs.get("task_name") or "ae3-background-task"),
            zone_id=kwargs.get("zone_id"),
            task_id=kwargs.get("task_id"),
            task_type=kwargs.get("task_type"),
        ),
        now_fn=_utcnow,
        logger=logger,
    )

    @asynccontextmanager
    async def _app_lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Retry get_pool на случай race condition при старте контейнера:
        # PostgreSQL может быть healthy, но docker-network DNS / TLS handshake
        # успевает дать transient connect error до того, как сеть стабилизируется.
        # Без retry FastAPI lifespan сразу падает и контейнер уходит в unhealthy.
        pool_attempts = 30
        pool_backoff_sec = 2.0
        for attempt in range(1, pool_attempts + 1):
            try:
                await get_pool()
                break
            except (OSError, ConnectionError, asyncpg.exceptions.PostgresConnectionError) as exc:
                if attempt >= pool_attempts:
                    logger.error(
                        "AE3 lifespan: PostgreSQL pool init failed after %d attempts: %s",
                        attempt,
                        exc,
                    )
                    raise
                logger.warning(
                    "AE3 lifespan: PostgreSQL pool init transient error (attempt %d/%d): %s — retry in %.1fs",
                    attempt,
                    pool_attempts,
                    exc,
                    pool_backoff_sec,
                )
                await asyncio.sleep(pool_backoff_sec)
        initialize_counter_series()
        await bundle.worker.recover_on_startup()
        bundle.worker.kick()
        app.state.ae3_runtime_bundle = bundle
        app.state.ae3_runtime_config = runtime_config
        app.state.ae3_critical_background_tasks = critical_background_tasks

        # Запустить listener статусов intent, если доступен DB DSN.
        intent_listener_task: Optional[asyncio.Task] = None
        intent_listener: Optional[IntentStatusListener] = None
        zone_event_listener_task: Optional[asyncio.Task] = None
        zone_event_listener: Optional[ZoneEventListener] = None
        if runtime_config.db_dsn:
            intent_listener = IntentStatusListener(
                dsn=runtime_config.db_dsn,
                on_terminal_intent=_build_intent_listener_callback(worker=bundle.worker, logger=logger),
            )
            intent_listener_task = _spawn_background_task(
                intent_listener.run(),
                background_tasks=background_tasks,
                task_name="ae3-intent-status-listener",
            )
            critical_background_tasks["ae3-intent-status-listener"] = intent_listener_task
            zone_event_listener = ZoneEventListener(
                dsn=runtime_config.db_dsn,
                on_zone_event=_build_zone_event_listener_callback(
                    worker=bundle.worker,
                    solution_tank_startup_guard_use_case=bundle.solution_tank_startup_guard_use_case,
                    now_fn=_utcnow,
                    logger=logger,
                ),
            )
            zone_event_listener_task = _spawn_background_task(
                zone_event_listener.run(),
                background_tasks=background_tasks,
                task_name="ae3-zone-event-listener",
            )
            critical_background_tasks["ae3-zone-event-listener"] = zone_event_listener_task

        try:
            yield
        finally:
            if intent_listener_task is not None and not intent_listener_task.done():
                intent_listener.stop()
            if zone_event_listener_task is not None and not zone_event_listener_task.done():
                zone_event_listener.stop()
            await _drain_background_tasks(background_tasks)
            await bundle.http_client.aclose()

    app = FastAPI(title="Automation Engine API", lifespan=_app_lifespan)
    app.state.ae3_runtime_bundle = bundle
    app.state.ae3_runtime_config = runtime_config
    app.state.ae3_critical_background_tasks = critical_background_tasks
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next: Any) -> Any:
        trace_id = extract_trace_id_from_headers(request.headers)
        effective_trace_id = set_trace_id(trace_id, allow_generate=True)
        started_at = _utcnow()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = max(0.0, (_utcnow() - started_at).total_seconds() * 1000.0)
            logger.error(
                "Unhandled AE3 API exception: method=%s path=%s duration_ms=%.2f error=%s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
                exc_info=True,
                extra={"trace_id": effective_trace_id},
            )
            try:
                await send_infra_exception_alert(
                    error=exc,
                    code="ae3_api_unhandled_exception",
                    alert_type="AE3 API Unhandled Exception",
                    severity="error",
                    zone_id=None,
                    service="automation-engine",
                    component=f"api:{request.url.path}",
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration_ms, 2),
                        "trace_id": effective_trace_id,
                    },
                )
            except Exception:
                logger.warning("Не удалось отправить alert для исключения AE3 API", exc_info=True)
            clear_trace_id()
            raise

        duration_ms = max(0.0, (_utcnow() - started_at).total_seconds() * 1000.0)
        if effective_trace_id:
            response.headers["X-Trace-Id"] = effective_trace_id

        if runtime_config.verbose_http_logging or response.status_code >= 500:
            log_level = logging.ERROR if response.status_code >= 500 else logging.DEBUG
            logger.log(
                log_level,
                "AE3 API request completed: method=%s path=%s status=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={"trace_id": effective_trace_id},
            )

        if response.status_code >= 500:
            try:
                await send_infra_alert(
                    code="ae3_api_http_5xx",
                    alert_type="AE3 API HTTP 5xx",
                    message=f"AE3 API вернул HTTP {response.status_code} для {request.method} {request.url.path}",
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
                        "trace_id": effective_trace_id,
                    },
                )
            except Exception:
                logger.warning("Не удалось отправить alert для AE3 API HTTP 5xx", exc_info=True)

        clear_trace_id()
        return response

    async def _validate_scheduler_zone(zone_id: int) -> None:
        await validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)

    async def _validate_scheduler_security_baseline(request: Request) -> None:
        validate_scheduler_security_baseline(
            headers=request.headers,
            enforce=runtime_config.scheduler_security_baseline_enforce,
            scheduler_api_token=runtime_config.scheduler_api_token,
            require_trace_id=runtime_config.scheduler_require_trace_id,
            extract_trace_id_from_headers_fn=extract_trace_id_from_headers,
        )

    bind_start_cycle_route(
        app,
        validate_scheduler_zone_fn=_validate_scheduler_zone,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        is_start_cycle_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
        start_cycle_rate_limit_check_fn=lambda zone_id: rate_limiter.check(zone_id=zone_id),
        start_cycle_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
        start_cycle_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
        claim_start_cycle_intent_fn=lambda *, zone_id, req, now: bundle.zone_intent_repository.claim_start_cycle(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
            running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
        ),
        create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: bundle.create_task_from_intent_use_case.run(
            zone_id=zone_id,
            source=source,
            idempotency_key=idempotency_key,
            intent_row=intent_row,
            now=now,
            allow_create=allow_create,
        ),
        ensure_solution_tank_startup_reset_fn=lambda *, zone_id: bundle.solution_tank_startup_guard_use_case.run(
            zone_id=zone_id,
            now=_utcnow(),
        ),
        kick_worker_fn=bundle.worker.kick,
        build_start_cycle_response_fn=build_start_cycle_response,
        mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: bundle.zone_intent_repository.mark_terminal(
            intent_id=intent_id, now=now, success=success,
            error_code=error_code, error_message=error_message,
        ),
        logger=logger,
    )
    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=_validate_scheduler_zone,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        is_start_irrigation_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
        start_irrigation_rate_limit_check_fn=lambda zone_id: rate_limiter.check(zone_id=zone_id),
        start_irrigation_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
        start_irrigation_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
        claim_start_irrigation_intent_fn=lambda *, zone_id, req, now: bundle.zone_intent_repository.claim_start_irrigation(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
            running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
        ),
        create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: bundle.create_task_from_intent_use_case.run(
            zone_id=zone_id,
            source=source,
            idempotency_key=idempotency_key,
            intent_row=intent_row,
            now=now,
            allow_create=allow_create,
        ),
        kick_worker_fn=bundle.worker.kick,
        build_start_cycle_response_fn=build_start_cycle_response,
        mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: bundle.zone_intent_repository.mark_terminal(
            intent_id=intent_id, now=now, success=success,
            error_code=error_code, error_message=error_message,
        ),
        logger=logger,
    )
    bind_start_lighting_tick_route(
        app,
        validate_scheduler_zone_fn=_validate_scheduler_zone,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        is_start_lighting_tick_rate_limit_enabled_fn=lambda: runtime_config.start_cycle_rate_limit_enabled,
        start_lighting_tick_rate_limit_check_fn=lambda zone_id: rate_limiter.check(zone_id=zone_id),
        start_lighting_tick_rate_limit_window_sec_fn=lambda: runtime_config.start_cycle_rate_limit_window_sec,
        start_lighting_tick_rate_limit_max_requests_fn=lambda: runtime_config.start_cycle_rate_limit_max_requests,
        claim_start_lighting_tick_intent_fn=lambda *, zone_id, req, now: bundle.zone_intent_repository.claim_start_lighting_tick(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
            running_stale_after_sec=runtime_config.start_cycle_running_stale_sec,
        ),
        create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now, allow_create=True: bundle.create_task_from_intent_use_case.run(
            zone_id=zone_id,
            source=source,
            idempotency_key=idempotency_key,
            intent_row=intent_row,
            now=now,
            allow_create=allow_create,
        ),
        kick_worker_fn=bundle.worker.kick,
        build_start_cycle_response_fn=build_start_cycle_response,
        mark_intent_terminal_fn=lambda *, intent_id, now, success, error_code, error_message: bundle.zone_intent_repository.mark_terminal(
            intent_id=intent_id, now=now, success=success,
            error_code=error_code, error_message=error_message,
        ),
        logger=logger,
    )
    bind_internal_task_route(
        app,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        load_task_status_fn=lambda task_id: bundle.task_status_read_model.get_by_task_id(task_id=task_id),
    )

    @app.get("/zones/{zone_id}/state")
    async def get_zone_state(zone_id: int) -> dict[str, Any]:
        """Возвращает полное automation state зоны: задачи, фазы и ошибки."""
        await _validate_scheduler_zone(zone_id)
        return await bundle.get_zone_automation_state_use_case.run(zone_id=zone_id)

    @app.get("/zones/{zone_id}/control-mode")
    async def get_zone_control_mode(zone_id: int) -> dict[str, Any]:
        """Возвращает текущий `control_mode` и разрешённые manual step для зоны."""
        await _validate_scheduler_zone(zone_id)
        result = await bundle.get_zone_control_state_use_case.run(zone_id=zone_id)
        return {"status": "ok", "data": {**result, "zone_id": zone_id}}

    @app.post("/zones/{zone_id}/control-mode")
    async def set_zone_control_mode(zone_id: int, request: Request, req: ControlModeRequest) -> dict[str, Any]:
        """Сохраняет `control_mode` зоны и синхронизирует snapshot активной задачи."""
        await _validate_scheduler_security_baseline(request)
        await validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)
        await bundle.set_control_mode_use_case.run(
            zone_id=zone_id,
            control_mode=req.control_mode,
            now=_utcnow(),
            user_id=req.user_id,
            user_role=req.user_role,
            source=req.source,
            reason=req.reason,
        )
        result = await bundle.get_zone_control_state_use_case.run(zone_id=zone_id)
        bundle.worker.kick()
        return {"status": "ok", "data": {**result, "zone_id": zone_id}}

    @app.post("/zones/{zone_id}/manual-step")
    async def request_zone_manual_step(zone_id: int, request: Request, req: ManualStepRequest) -> dict[str, Any]:
        """Сохраняет pending public manual step для активной задачи зоны."""
        await _validate_scheduler_security_baseline(request)
        await validate_scheduler_zone(zone_id, fetch_fn=fetch, logger=logger)
        try:
            result = await bundle.request_manual_step_use_case.run(
                zone_id=zone_id,
                manual_step=req.manual_step,
                now=_utcnow(),
            )
        except ManualControlError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "status": "error",
                    "code": exc.code,
                    "message": str(exc),
                    **exc.details,
                },
            ) from exc
        bundle.worker.kick()
        return {"status": "ok", "data": result}

    @app.get("/health/live")
    async def health_live() -> dict[str, Any]:
        return {"status": "ok", "service": "automation-engine"}

    @app.get("/health/ready")
    async def health_ready() -> Any:
        db_ready = True
        db_reason = "ok"
        try:
            await fetch("SELECT 1 AS ready")
        except Exception as exc:
            db_ready = False
            db_reason = type(exc).__name__
            logger.warning("Проверка готовности AE3 через DB probe завершилась ошибкой: %s", exc, exc_info=True)

        worker_ok, worker_reason = bundle.worker.drain_health()
        critical_ok, critical_reason = _critical_background_tasks_health(
            getattr(app.state, "ae3_critical_background_tasks", {}),
        )
        all_ok = db_ready and worker_ok and critical_ok
        payload = {
            "status": "ok" if all_ok else "degraded",
            "service": "automation-engine",
            "ready": all_ok,
            "checks": {
                "db": {"ok": db_ready, "reason": db_reason},
                "worker": {"ok": worker_ok, "reason": worker_reason},
                "critical_background_tasks": {"ok": critical_ok, "reason": critical_reason},
            },
        }
        return payload if all_ok else JSONResponse(status_code=503, content=payload)

    return app


async def serve(config: Optional[Ae3RuntimeConfig] = None) -> None:
    runtime_config = config or Ae3RuntimeConfig.from_env()
    app = create_app(runtime_config)

    send_service_log(
        service="automation-engine",
        level="info",
        message="Сервис AE3-Lite runtime запущен",
        context={
            "api_port": runtime_config.port,
            "app_env": runtime_config.app_env,
            "history_logger_url": runtime_config.history_logger_url,
        },
    )

    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=runtime_config.host,
            port=runtime_config.port,
            log_level="info",
            access_log=False,
        )
    )
    await server.serve()


app = create_app()


__all__ = ["app", "create_app", "serve"]
