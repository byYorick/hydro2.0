"""FastAPI-приложение automation-engine 1.0.0 (один воркер AE4)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator, Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field

from ae4.api.climate_tick import bind_greenhouse_climate_tick_route
from ae4.api.http_errors import api_error_detail, enrich_http_exception_content
from ae4.api.rate_limit import SlidingWindowRateLimiter
from ae4.api.security import validate_scheduler_security_baseline
from ae4.application.zone_http_state import (
    build_zone_automation_state,
    get_zone_control_state,
    operator_unblock_zone,
    set_zone_control_mode,
)
from ae4.runtime.env import Ae4RuntimeConfig
from ae4.runtime.worker import AE4_WORKER_OWNER, Ae4RuntimeWorker
from common.db import fetch, get_pool
from common.logging_setup import install_exception_handlers, setup_standard_logging
from common.service_logs import send_service_log
from common.trace_context import clear_trace_id, extract_trace_id_from_headers, set_trace_id

logger = logging.getLogger(__name__)

SERVICE_VERSION = "1.0.0"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ControlModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_mode: str = Field(..., min_length=1, max_length=32)
    user_id: int | None = None
    user_role: str | None = None
    source: str = Field(default="api", min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class OperatorUnblockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=500)
    confirm: bool = True
    source: str = Field(default="laravel_api", min_length=1, max_length=64)
    user_id: int | None = None
    user_role: str | None = None


async def _probe_history_logger_ready(*, base_url: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{str(base_url).rstrip('/')}/health")
        if response.status_code < 500:
            return True, "ok"
        return False, f"http_{response.status_code}"
    except Exception as exc:
        return False, type(exc).__name__


def create_app(
    config: Optional[Ae4RuntimeConfig] = None,
    *,
    worker: Ae4RuntimeWorker | None = None,
) -> FastAPI:
    runtime_config = config or Ae4RuntimeConfig.from_env()
    runtime_config.validate()
    background_tasks: set[asyncio.Task] = set()
    zone_read_limiter = SlidingWindowRateLimiter(max_requests=60, window_sec=10.0)
    climate_tick_limiter = SlidingWindowRateLimiter(max_requests=60, window_sec=10.0)
    ae4_worker = worker or Ae4RuntimeWorker(config=runtime_config)

    def _spawn_background(coro: Any, **kwargs: Any) -> asyncio.Task:
        task_name = str(kwargs.get("task_name") or "ae4-background")
        task = asyncio.create_task(coro, name=task_name)
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return task

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool_attempts = 30
        for attempt in range(1, pool_attempts + 1):
            try:
                await get_pool()
                break
            except (OSError, ConnectionError, asyncpg.exceptions.PostgresConnectionError) as exc:
                if attempt >= pool_attempts:
                    raise
                logger.warning(
                    "AE lifespan: PostgreSQL transient (%d/%d): %s",
                    attempt,
                    pool_attempts,
                    exc,
                )
                await asyncio.sleep(2.0)

        worker_task = asyncio.create_task(ae4_worker.run(), name="ae4-runtime-worker")
        app.state.ae4_worker = ae4_worker
        app.state.ae4_worker_task = worker_task
        app.state.ae4_runtime_config = runtime_config
        try:
            yield
        finally:
            await ae4_worker.shutdown()
            if not worker_task.done():
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            pending = list(background_tasks)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(
        title="Automation Engine API",
        version=SERVICE_VERSION,
        lifespan=_lifespan,
    )

    @app.exception_handler(HTTPException)
    async def localized_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=enrich_http_exception_content(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request, exc
        http_exc = api_error_detail("validation_error", status_code=422)
        return JSONResponse(
            status_code=422,
            content=enrich_http_exception_content(http_exc),
        )

    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next: Any) -> Any:
        trace_id = extract_trace_id_from_headers(request.headers)
        effective = set_trace_id(trace_id, allow_generate=True)
        try:
            response = await call_next(request)
        except HTTPException:
            clear_trace_id()
            raise
        except Exception:
            clear_trace_id()
            raise
        if effective:
            response.headers["X-Trace-Id"] = effective
        clear_trace_id()
        return response

    async def _validate_security(request: Request) -> None:
        validate_scheduler_security_baseline(
            headers=request.headers,
            enforce=runtime_config.scheduler_security_baseline_enforce,
            scheduler_api_token=runtime_config.scheduler_api_token,
            require_trace_id=runtime_config.scheduler_require_trace_id,
            extract_trace_id_from_headers_fn=extract_trace_id_from_headers,
        )

    async def _validate_zone(zone_id: int) -> None:
        rows = await fetch("SELECT id FROM zones WHERE id = $1 LIMIT 1", zone_id)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Зона '{zone_id}' не найдена")

    def _enforce_zone_read_rate_limit(zone_id: int) -> None:
        if not runtime_config.rate_limit_enabled:
            return
        if zone_read_limiter.check(zone_id=zone_id):
            return
        raise api_error_detail(
            "start_cycle_rate_limited",
            status_code=429,
            zone_id=zone_id,
            window_sec=10,
            max_requests=60,
        )

    bind_greenhouse_climate_tick_route(
        app,
        validate_scheduler_security_baseline_fn=_validate_security,
        is_climate_tick_rate_limit_enabled_fn=lambda: runtime_config.rate_limit_enabled,
        climate_tick_rate_limit_check_fn=lambda greenhouse_id: climate_tick_limiter.check(
            zone_id=greenhouse_id
        ),
        climate_tick_rate_limit_window_sec_fn=lambda: 10,
        climate_tick_rate_limit_max_requests_fn=lambda: 60,
        spawn_background_task_fn=_spawn_background,
        worker_owner=AE4_WORKER_OWNER,
        logger_=logger,
    )

    @app.get("/zones/{zone_id}/state")
    async def get_zone_state(
        zone_id: Annotated[int, Path(gt=0)],
        request: Request,
    ) -> dict[str, Any]:
        await _validate_security(request)
        await _validate_zone(zone_id)
        _enforce_zone_read_rate_limit(zone_id)
        return await build_zone_automation_state(zone_id=zone_id)

    @app.get("/zones/{zone_id}/control-mode")
    async def get_control_mode(
        zone_id: Annotated[int, Path(gt=0)],
        request: Request,
    ) -> dict[str, Any]:
        await _validate_security(request)
        await _validate_zone(zone_id)
        _enforce_zone_read_rate_limit(zone_id)
        result = await get_zone_control_state(zone_id=zone_id)
        return {"status": "ok", "data": {**result, "zone_id": zone_id}}

    @app.post("/zones/{zone_id}/control-mode")
    async def post_control_mode(
        zone_id: Annotated[int, Path(gt=0)],
        request: Request,
        req: ControlModeRequest,
    ) -> dict[str, Any]:
        await _validate_security(request)
        await _validate_zone(zone_id)
        await set_zone_control_mode(
            zone_id=zone_id,
            control_mode=req.control_mode,
            user_id=req.user_id,
            user_role=req.user_role,
            source=req.source,
            reason=req.reason,
        )
        result = await get_zone_control_state(zone_id=zone_id)
        return {"status": "ok", "data": {**result, "zone_id": zone_id}}

    @app.post("/zones/{zone_id}/operator-unblock")
    async def post_operator_unblock(
        zone_id: Annotated[int, Path(gt=0)],
        request: Request,
        req: OperatorUnblockRequest,
    ) -> dict[str, Any]:
        await _validate_security(request)
        await _validate_zone(zone_id)
        result = await operator_unblock_zone(
            zone_id=zone_id,
            reason=req.reason,
            source=req.source,
            user_id=req.user_id,
            user_role=req.user_role,
        )
        return {"status": "ok", "data": result}

    @app.get("/health")
    @app.get("/health/live")
    async def health_live() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "automation-engine",
            "version": SERVICE_VERSION,
        }

    @app.get("/health/ready")
    async def health_ready() -> Any:
        db_ready = True
        db_reason = "ok"
        try:
            await fetch("SELECT 1 AS ready")
        except Exception as exc:
            db_ready = False
            db_reason = type(exc).__name__
        hl_ready, hl_reason = await _probe_history_logger_ready(
            base_url=runtime_config.history_logger_url
        )
        worker_ok = not ae4_worker._stop.is_set()  # noqa: SLF001
        all_ok = db_ready and hl_ready and worker_ok
        payload = {
            "status": "ok" if all_ok else "degraded",
            "service": "automation-engine",
            "version": SERVICE_VERSION,
            "ready": all_ok,
            "checks": {
                "db": {"ok": db_ready, "reason": db_reason},
                "worker": {"ok": worker_ok, "reason": "ok" if worker_ok else "stopped"},
                "history_logger": {"ok": hl_ready, "reason": hl_reason},
            },
        }
        return payload if all_ok else JSONResponse(status_code=503, content=payload)

    return app


async def serve(config: Optional[Ae4RuntimeConfig] = None) -> None:
    setup_standard_logging("automation-engine")
    install_exception_handlers("automation-engine")
    runtime_config = config or Ae4RuntimeConfig.from_env()
    app = create_app(runtime_config)
    send_service_log(
        service="automation-engine",
        level="info",
        message="Сервис automation-engine 1.0.0 запущен",
        context={
            "api_port": runtime_config.port,
            "app_env": runtime_config.app_env,
            "version": SERVICE_VERSION,
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


__all__ = ["create_app", "serve", "SERVICE_VERSION"]
