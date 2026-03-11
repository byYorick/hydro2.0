"""Standalone FastAPI app for AE3-Lite runtime."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from ae3lite.api import bind_internal_task_route, bind_start_cycle_route
from ae3lite.api.intents import claim_start_cycle_intent, mark_intent_running, mark_intent_terminal
from ae3lite.api.rate_limit import SlidingWindowRateLimiter
from ae3lite.api.responses import build_start_cycle_response
from ae3lite.api.security import validate_scheduler_security_baseline
from ae3lite.api.validation import validate_scheduler_zone
from ae3lite.runtime.bootstrap import build_ae3_runtime_bundle
from ae3lite.runtime.config import Ae3RuntimeConfig
from common.db import execute, fetch, get_pool
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.service_logs import send_service_log
from common.trace_context import clear_trace_id, extract_trace_id_from_headers, set_trace_id

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _drain_background_tasks(background_tasks: set[asyncio.Task], timeout_sec: float = 5.0) -> None:
    pending = [task for task in background_tasks if not task.done()]
    if not pending:
        return

    for task in pending:
        task.cancel()

    try:
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout_sec)
    except asyncio.TimeoutError:
        logger.warning("Timed out draining AE3 background tasks: pending=%s", len(pending))
    finally:
        background_tasks.difference_update(pending)


def _spawn_background_task(
    coro: Any,
    *,
    task_name: str,
    background_tasks: set[asyncio.Task],
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> asyncio.Task:
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
                "Failed to inspect AE3 background task result: task_name=%s error=%s",
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
                "Failed to schedule alert for crashed AE3 background task: task_name=%s",
                task_name,
                exc_info=True,
            )

    task.add_done_callback(_on_done)
    return task


def create_app(config: Optional[Ae3RuntimeConfig] = None) -> FastAPI:
    runtime_config = config or Ae3RuntimeConfig.from_env()
    if config is None:
        runtime_config.validate()
    background_tasks: set[asyncio.Task] = set()
    rate_limiter = SlidingWindowRateLimiter(
        max_requests=runtime_config.start_cycle_rate_limit_max_requests,
        window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
    )

    async def _mark_intent_running_fn(*, intent_id: int, now: datetime) -> None:
        await mark_intent_running(intent_id=intent_id, now=now, execute_fn=execute)

    async def _mark_intent_terminal_fn(
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Optional[str],
        error_message: Optional[str],
    ) -> None:
        await mark_intent_terminal(
            intent_id=intent_id,
            now=now,
            success=success,
            error_code=error_code,
            error_message=error_message,
            execute_fn=execute,
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
        mark_intent_running_fn=_mark_intent_running_fn,
        mark_intent_terminal_fn=_mark_intent_terminal_fn,
        now_fn=_utcnow,
        logger=logger,
    )

    @asynccontextmanager
    async def _app_lifespan(app: FastAPI) -> AsyncIterator[None]:
        await get_pool()
        await bundle.worker.recover_on_startup()
        bundle.worker.kick()
        app.state.ae3_runtime_bundle = bundle
        app.state.ae3_runtime_config = runtime_config
        try:
            yield
        finally:
            await _drain_background_tasks(background_tasks)

    app = FastAPI(title="Automation Engine API", lifespan=_app_lifespan)
    app.state.ae3_runtime_bundle = bundle
    app.state.ae3_runtime_config = runtime_config
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
                logger.warning("Failed to send alert for AE3 API exception", exc_info=True)
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
                    message=f"AE3 API returned HTTP {response.status_code} for {request.method} {request.url.path}",
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
                logger.warning("Failed to send alert for AE3 API HTTP 5xx", exc_info=True)

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
        claim_start_cycle_intent_fn=lambda *, zone_id, req, now: claim_start_cycle_intent(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=runtime_config.start_cycle_claim_stale_sec,
            fetch_fn=fetch,
        ),
        create_task_from_intent_fn=lambda *, zone_id, source, idempotency_key, intent_row, now: bundle.create_task_from_intent_use_case.run(
            zone_id=zone_id,
            source=source,
            idempotency_key=idempotency_key,
            intent_row=intent_row,
            now=now,
        ),
        kick_worker_fn=bundle.worker.kick,
        build_start_cycle_response_fn=build_start_cycle_response,
        mark_intent_terminal_fn=_mark_intent_terminal_fn,
        logger=logger,
    )
    bind_internal_task_route(
        app,
        validate_scheduler_security_baseline_fn=_validate_scheduler_security_baseline,
        load_task_status_fn=lambda task_id: bundle.task_status_read_model.get_by_task_id(task_id=task_id),
    )

    @app.get("/zones/{zone_id}/state")
    async def get_zone_state(zone_id: int) -> dict[str, Any]:
        """Return full automation state for a zone (tasks, phases, errors)."""
        return await bundle.get_zone_automation_state_use_case.run(zone_id=zone_id)

    @app.get("/zones/{zone_id}/control-mode")
    async def get_zone_control_mode(zone_id: int) -> dict[str, Any]:
        """Return current control_mode and allowed manual steps for a zone."""
        result = await bundle.get_zone_control_state_use_case.run(zone_id=zone_id)
        return {"data": {**result, "zone_id": zone_id}}

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
            logger.warning("AE3 readiness DB probe failed: %s", exc, exc_info=True)

        payload = {
            "status": "ok" if db_ready else "degraded",
            "service": "automation-engine",
            "ready": db_ready,
            "checks": {
                "db": {"ok": db_ready, "reason": db_reason},
                "worker": {"ok": True, "reason": runtime_config.worker_owner},
            },
        }
        return payload if db_ready else JSONResponse(status_code=503, content=payload)

    return app


async def serve(config: Optional[Ae3RuntimeConfig] = None) -> None:
    runtime_config = config or Ae3RuntimeConfig.from_env()
    app = create_app(runtime_config)

    send_service_log(
        service="automation-engine",
        level="info",
        message="AE3-Lite runtime service started",
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
