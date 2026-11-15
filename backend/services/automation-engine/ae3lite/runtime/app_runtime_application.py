"""app runtime application: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import FastAPI

from ae3lite.api.rate_limit import SlidingWindowRateLimiter
from ae3lite.runtime.env import Ae3RuntimeConfig


@dataclass(frozen=True)
class AppRuntimeApplicationPorts:
    bind_dispatch_ingress: Callable[..., Any]
    bind_health_routes: Callable[..., Any]
    bind_http_boundary: Callable[..., Any]
    bind_zone_control_routes: Callable[..., Any]
    build_app_lifespan: Callable[..., Any]
    build_ingress_guards: Callable[..., Any]
    spawn_background_task: Callable[..., Any]
    utcnow: Callable[..., Any]
    validate_runtime_config: Callable[..., Any]
    build_ae3_runtime_bundle: Callable[..., Any]
    create_app: Callable[..., Any]
    logger: Callable[..., Any]
    make_asgi_app: Callable[..., Any]
    send_service_log: Callable[..., Any]


class AppRuntimeApplication:
    def __init__(self, ports: AppRuntimeApplicationPorts) -> None:
        self._ports = ports

    def create_app(self, config: Optional[Ae3RuntimeConfig]) -> FastAPI:
        runtime_config = config or Ae3RuntimeConfig.from_env()
        self._ports.validate_runtime_config(runtime_config)
        background_tasks: set[asyncio.Task] = set()
        critical_background_tasks: dict[str, asyncio.Task] = {}
        start_cycle_rate_limiter = SlidingWindowRateLimiter(
            max_requests=runtime_config.start_cycle_rate_limit_max_requests,
            window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
        )
        start_irrigation_rate_limiter = SlidingWindowRateLimiter(
            max_requests=runtime_config.start_cycle_rate_limit_max_requests,
            window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
        )
        start_lighting_tick_rate_limiter = SlidingWindowRateLimiter(
            max_requests=runtime_config.start_cycle_rate_limit_max_requests,
            window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
        )
        start_solution_topup_rate_limiter = SlidingWindowRateLimiter(
            max_requests=runtime_config.start_cycle_rate_limit_max_requests,
            window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
        )
        start_solution_change_rate_limiter = SlidingWindowRateLimiter(
            max_requests=runtime_config.start_cycle_rate_limit_max_requests,
            window_sec=float(runtime_config.start_cycle_rate_limit_window_sec),
        )
        zone_read_rate_limiter = SlidingWindowRateLimiter(max_requests=60, window_sec=10.0)
        climate_tick_rate_limiter = SlidingWindowRateLimiter(max_requests=60, window_sec=10.0)

        bundle = self._ports.build_ae3_runtime_bundle(
            config=runtime_config,
            spawn_background_task_fn=lambda coro, **kwargs: self._ports.spawn_background_task(
                coro,
                background_tasks=background_tasks,
                task_name=str(kwargs.get("task_name") or "ae3-background-task"),
                zone_id=kwargs.get("zone_id"),
                task_id=kwargs.get("task_id"),
                task_type=kwargs.get("task_type"),
            ),
            now_fn=self._ports.utcnow,
            logger=self._ports.logger(),
        )

        _app_lifespan = self._ports.build_app_lifespan(
            bundle=bundle,
            runtime_config=runtime_config,
            background_tasks=background_tasks,
            critical_background_tasks=critical_background_tasks,
        )

        app = FastAPI(title="Automation Engine API", lifespan=_app_lifespan)

        self._ports.bind_http_boundary(app=app, runtime_config=runtime_config)

        app.state.ae3_runtime_bundle = bundle
        app.state.ae3_runtime_config = runtime_config
        app.state.ae3_critical_background_tasks = critical_background_tasks
        app.mount("/metrics", self._ports.make_asgi_app())

        _validate_scheduler_zone, _validate_scheduler_security_baseline, _load_zone_workflow_phase = (
            self._ports.build_ingress_guards(runtime_config=runtime_config)
        )

        self._ports.bind_dispatch_ingress(
            app=app,
            runtime_config=runtime_config,
            bundle=bundle,
            background_tasks=background_tasks,
            start_cycle_rate_limiter=start_cycle_rate_limiter,
            start_irrigation_rate_limiter=start_irrigation_rate_limiter,
            start_lighting_tick_rate_limiter=start_lighting_tick_rate_limiter,
            start_solution_topup_rate_limiter=start_solution_topup_rate_limiter,
            start_solution_change_rate_limiter=start_solution_change_rate_limiter,
            climate_tick_rate_limiter=climate_tick_rate_limiter,
            _validate_scheduler_zone=_validate_scheduler_zone,
            _validate_scheduler_security_baseline=_validate_scheduler_security_baseline,
            _load_zone_workflow_phase=_load_zone_workflow_phase,
        )

        self._ports.bind_zone_control_routes(
            app=app,
            runtime_config=runtime_config,
            bundle=bundle,
            zone_read_rate_limiter=zone_read_rate_limiter,
            _validate_scheduler_security_baseline=_validate_scheduler_security_baseline,
            _validate_scheduler_zone=_validate_scheduler_zone,
        )

        self._ports.bind_health_routes(app=app, runtime_config=runtime_config, bundle=bundle)

        return app

    async def serve(self, config: Optional[Ae3RuntimeConfig]) -> None:
        runtime_config = config or Ae3RuntimeConfig.from_env()
        app = self._ports.create_app(runtime_config)

        self._ports.send_service_log(
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

    def validate_runtime_config(self, runtime_config: Any) -> None:
        validate = getattr(runtime_config, "validate", None)
        if callable(validate):
            validate()
