"""Standalone FastAPI-приложение для runtime AE3-Lite."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Mapping, Optional, Annotated

import httpx
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from pydantic import BaseModel, ConfigDict, Field

from ae3lite.api import (
    bind_greenhouse_climate_tick_route,
    bind_internal_task_route,
    bind_start_cycle_route,
    bind_start_irrigation_route,
    bind_start_lighting_tick_route,
    bind_start_solution_change_route,
    bind_start_solution_topup_route,
)
from ae3lite.api.http_errors import api_error_detail, enrich_http_exception_content
from common.error_catalog import enrich_error_payload, present_error
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
from common.trace_context import clear_trace_id, extract_trace_id_from_headers, get_trace_id, set_trace_id
from common.utils.time import utcnow_naive as _utcnow

logger = logging.getLogger(__name__)

_HL_READY_CHECK_CACHE: dict[str, float | bool | str] = {
    "monotonic_at": 0.0,
    "ok": False,
    "reason": "unchecked",
}
_HL_READY_CHECK_TTL_SEC = 10.0
_HL_READY_CHECK_TIMEOUT_SEC = 2.0


from ae3lite.runtime.app_runtime_records import (
    ControlModeRequest,
    OperatorUnblockRequest,
    ManualStepRequest,
    BackgroundTaskLimitError,
)
from ae3lite.runtime.app_runtime_application import AppRuntimeApplication, AppRuntimeApplicationPorts


def _app_runtime_application() -> AppRuntimeApplication:
    return AppRuntimeApplication(
        AppRuntimeApplicationPorts(
            bind_dispatch_ingress=lambda *args, **kwargs: _bind_dispatch_ingress(*args, **kwargs),
            bind_health_routes=lambda *args, **kwargs: _bind_health_routes(*args, **kwargs),
            bind_http_boundary=lambda *args, **kwargs: _bind_http_boundary(*args, **kwargs),
            bind_zone_control_routes=lambda *args, **kwargs: _bind_zone_control_routes(*args, **kwargs),
            build_app_lifespan=lambda *args, **kwargs: _build_app_lifespan(*args, **kwargs),
            build_ingress_guards=lambda *args, **kwargs: _build_ingress_guards(*args, **kwargs),
            spawn_background_task=lambda *args, **kwargs: _spawn_background_task(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            validate_runtime_config=lambda *args, **kwargs: _validate_runtime_config(*args, **kwargs),
            build_ae3_runtime_bundle=lambda *args, **kwargs: build_ae3_runtime_bundle(*args, **kwargs),
            create_app=lambda *args, **kwargs: create_app(*args, **kwargs),
            logger=lambda: logger,
            make_asgi_app=lambda *args, **kwargs: make_asgi_app(*args, **kwargs),
            send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
        )
    )


from ae3lite.runtime.app_runtime_background_tasks import AppRuntimeBackgroundTasks, AppRuntimeBackgroundTasksPorts


def _app_runtime_background_tasks() -> AppRuntimeBackgroundTasks:
    return AppRuntimeBackgroundTasks(
        AppRuntimeBackgroundTasksPorts(
            background_tasks_size_limit=lambda: _BACKGROUND_TASKS_SIZE_LIMIT,
            close_coro=lambda *args, **kwargs: _close_coro(*args, **kwargs),
            logger=lambda: logger,
            send_infra_exception_alert=lambda *args, **kwargs: send_infra_exception_alert(*args, **kwargs),
        )
    )


from ae3lite.runtime.app_runtime_intent_listener import AppRuntimeIntentListener, AppRuntimeIntentListenerPorts


def _app_runtime_intent_listener() -> AppRuntimeIntentListener:
    return AppRuntimeIntentListener(AppRuntimeIntentListenerPorts())


from ae3lite.runtime.app_runtime_zone_events import AppRuntimeZoneEvents, AppRuntimeZoneEventsPorts


def _app_runtime_zone_events() -> AppRuntimeZoneEvents:
    return AppRuntimeZoneEvents(
        AppRuntimeZoneEventsPorts(
            node_runtime_event_kick=lambda: NODE_RUNTIME_EVENT_KICK,
            runtime_critical_node_event_types=lambda: _RUNTIME_CRITICAL_NODE_EVENT_TYPES,
            coerce_optional_bool=lambda *args, **kwargs: _coerce_optional_bool(*args, **kwargs),
            is_runtime_zone_event_relevant=lambda *args, **kwargs: _is_runtime_zone_event_relevant(*args, **kwargs),
            zone_event_indicates_solution_min_depletion=lambda *args, **kwargs: (
                _zone_event_indicates_solution_min_depletion(*args, **kwargs)
            ),
            send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
        )
    )


from ae3lite.runtime.app_runtime_http_boundary import AppRuntimeHttpBoundary, AppRuntimeHttpBoundaryPorts


def _app_runtime_http_boundary() -> AppRuntimeHttpBoundary:
    return AppRuntimeHttpBoundary(
        AppRuntimeHttpBoundaryPorts(
            internal_error_response=lambda *args, **kwargs: _internal_error_response(*args, **kwargs),
            request_zone_id=lambda *args, **kwargs: _request_zone_id(*args, **kwargs),
            response_error_code=lambda *args, **kwargs: _response_error_code(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            logger=lambda: logger,
            send_infra_alert=lambda *args, **kwargs: send_infra_alert(*args, **kwargs),
            send_infra_exception_alert=lambda *args, **kwargs: send_infra_exception_alert(*args, **kwargs),
        )
    )


from ae3lite.runtime.app_runtime_health import AppRuntimeHealth, AppRuntimeHealthPorts


def _app_runtime_health() -> AppRuntimeHealth:
    return AppRuntimeHealth(
        AppRuntimeHealthPorts(
            hl_ready_check_cache=lambda: _HL_READY_CHECK_CACHE,
            hl_ready_check_timeout_sec=lambda: _HL_READY_CHECK_TIMEOUT_SEC,
            hl_ready_check_ttl_sec=lambda: _HL_READY_CHECK_TTL_SEC,
            critical_background_tasks_health=lambda *args, **kwargs: _critical_background_tasks_health(*args, **kwargs),
            probe_history_logger_ready=lambda *args, **kwargs: _probe_history_logger_ready(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.runtime.app_runtime_lifespan import AppRuntimeLifespan, AppRuntimeLifespanPorts


def _app_runtime_lifespan() -> AppRuntimeLifespan:
    return AppRuntimeLifespan(
        AppRuntimeLifespanPorts(
            intentstatuslistener=lambda *args, **kwargs: IntentStatusListener(*args, **kwargs),
            zoneeventlistener=lambda *args, **kwargs: ZoneEventListener(*args, **kwargs),
            build_intent_listener_callback=lambda *args, **kwargs: _build_intent_listener_callback(*args, **kwargs),
            build_zone_event_listener_callback=lambda *args, **kwargs: _build_zone_event_listener_callback(
                *args, **kwargs
            ),
            drain_background_tasks=lambda *args, **kwargs: _drain_background_tasks(*args, **kwargs),
            spawn_background_task=lambda *args, **kwargs: _spawn_background_task(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            initialize_counter_series=lambda *args, **kwargs: initialize_counter_series(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.runtime.app_runtime_guards import AppRuntimeGuards, AppRuntimeGuardsPorts


def _app_runtime_guards() -> AppRuntimeGuards:
    return AppRuntimeGuards(
        AppRuntimeGuardsPorts(
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.runtime.app_runtime_dispatch import AppRuntimeDispatch, AppRuntimeDispatchPorts


def _app_runtime_dispatch() -> AppRuntimeDispatch:
    return AppRuntimeDispatch(
        AppRuntimeDispatchPorts(
            spawn_background_task=lambda *args, **kwargs: _spawn_background_task(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            bind_greenhouse_climate_tick_route=lambda *args, **kwargs: bind_greenhouse_climate_tick_route(
                *args, **kwargs
            ),
            bind_internal_task_route=lambda *args, **kwargs: bind_internal_task_route(*args, **kwargs),
            bind_start_cycle_route=lambda *args, **kwargs: bind_start_cycle_route(*args, **kwargs),
            bind_start_irrigation_route=lambda *args, **kwargs: bind_start_irrigation_route(*args, **kwargs),
            bind_start_lighting_tick_route=lambda *args, **kwargs: bind_start_lighting_tick_route(*args, **kwargs),
            bind_start_solution_change_route=lambda *args, **kwargs: bind_start_solution_change_route(*args, **kwargs),
            bind_start_solution_topup_route=lambda *args, **kwargs: bind_start_solution_topup_route(*args, **kwargs),
            logger=lambda: logger,
        )
    )


from ae3lite.runtime.app_runtime_zone_control import AppRuntimeZoneControl, AppRuntimeZoneControlPorts


def _app_runtime_zone_control() -> AppRuntimeZoneControl:
    return AppRuntimeZoneControl(
        AppRuntimeZoneControlPorts(
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            logger=lambda: logger,
        )
    )


async def _probe_history_logger_ready(*, base_url: str) -> tuple[bool, str]:
    return await _app_runtime_health().probe_history_logger_ready(base_url=base_url)


async def _drain_background_tasks(background_tasks: set[asyncio.Task], timeout_sec: float = 5.0) -> None:
    return await _app_runtime_background_tasks().drain_background_tasks(
        background_tasks=background_tasks, timeout_sec=timeout_sec
    )


_BACKGROUND_TASKS_SIZE_LIMIT = 256


def _close_coro(coro: Any) -> None:
    return _app_runtime_background_tasks().close_coro(coro=coro)


def _spawn_background_task(
    coro: Any,
    *,
    task_name: str,
    background_tasks: set[asyncio.Task],
    zone_id: Optional[int] = None,
    task_id: Optional[str] = None,
    task_type: Optional[str] = None,
) -> asyncio.Task:
    return _app_runtime_background_tasks().spawn_background_task(
        coro=coro,
        task_name=task_name,
        background_tasks=background_tasks,
        zone_id=zone_id,
        task_id=task_id,
        task_type=task_type,
    )


def _build_intent_listener_callback(*, worker: Any, logger: logging.Logger) -> Any:
    return _app_runtime_intent_listener().build_intent_listener_callback(worker=worker, logger=logger)


def _coerce_optional_bool(value: Any) -> bool | None:
    return _app_runtime_zone_events().coerce_optional_bool(value=value)


_RUNTIME_CRITICAL_NODE_EVENT_TYPES = frozenset(
    {
        "LEVEL_SWITCH_CHANGED",
        "EMERGENCY_STOP_ACTIVATED",
    }
)


def _is_runtime_zone_event_relevant(data: Mapping[str, Any]) -> bool:
    return _app_runtime_zone_events().is_runtime_zone_event_relevant(data=data)


def _zone_event_indicates_solution_min_depletion(data: Mapping[str, Any]) -> bool:
    return _app_runtime_zone_events().zone_event_indicates_solution_min_depletion(data=data)


def _build_zone_event_listener_callback(
    *,
    worker: Any,
    solution_tank_startup_guard_use_case: Any | None,
    trigger_solution_topup_from_level_event_use_case: Any | None = None,
    now_fn: Any,
    logger: logging.Logger,
) -> Any:
    return _app_runtime_zone_events().build_zone_event_listener_callback(
        worker=worker,
        solution_tank_startup_guard_use_case=solution_tank_startup_guard_use_case,
        trigger_solution_topup_from_level_event_use_case=trigger_solution_topup_from_level_event_use_case,
        now_fn=now_fn,
        logger=logger,
    )


def _validate_runtime_config(runtime_config: Any) -> None:
    return _app_runtime_application().validate_runtime_config(runtime_config=runtime_config)


def _internal_error_response(trace_id: Optional[str]) -> JSONResponse:
    return _app_runtime_http_boundary().internal_error_response(trace_id=trace_id)


def _response_error_code(response: Any) -> str | None:
    return _app_runtime_http_boundary().response_error_code(response=response)


def _request_zone_id(request: Request) -> int | None:
    return _app_runtime_http_boundary().request_zone_id(request=request)


def _critical_background_tasks_health(background_tasks: Mapping[str, Any]) -> tuple[bool, str]:
    return _app_runtime_health().critical_background_tasks_health(background_tasks=background_tasks)


def _build_app_lifespan(
    *, bundle: Any, runtime_config: Any, background_tasks: Any, critical_background_tasks: Any
) -> Any:
    return _app_runtime_lifespan().build_app_lifespan(
        bundle=bundle,
        runtime_config=runtime_config,
        background_tasks=background_tasks,
        critical_background_tasks=critical_background_tasks,
    )


def _bind_http_boundary(*, app: Any, runtime_config: Any) -> Any:
    return _app_runtime_http_boundary().bind_http_boundary(app=app, runtime_config=runtime_config)


def _build_ingress_guards(*, runtime_config: Any) -> Any:
    return _app_runtime_guards().build_ingress_guards(runtime_config=runtime_config)


def _bind_dispatch_ingress(
    *,
    app: Any,
    runtime_config: Any,
    bundle: Any,
    background_tasks: Any,
    start_cycle_rate_limiter: Any,
    start_irrigation_rate_limiter: Any,
    start_lighting_tick_rate_limiter: Any,
    start_solution_topup_rate_limiter: Any,
    start_solution_change_rate_limiter: Any,
    climate_tick_rate_limiter: Any,
    _validate_scheduler_zone: Any,
    _validate_scheduler_security_baseline: Any,
    _load_zone_workflow_phase: Any,
) -> Any:
    return _app_runtime_dispatch().bind_dispatch_ingress(
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


def _bind_zone_control_routes(
    *,
    app: Any,
    runtime_config: Any,
    bundle: Any,
    zone_read_rate_limiter: Any,
    _validate_scheduler_security_baseline: Any,
    _validate_scheduler_zone: Any,
) -> Any:
    return _app_runtime_zone_control().bind_zone_control_routes(
        app=app,
        runtime_config=runtime_config,
        bundle=bundle,
        zone_read_rate_limiter=zone_read_rate_limiter,
        _validate_scheduler_security_baseline=_validate_scheduler_security_baseline,
        _validate_scheduler_zone=_validate_scheduler_zone,
    )


def _bind_health_routes(*, app: Any, runtime_config: Any, bundle: Any) -> Any:
    return _app_runtime_health().bind_health_routes(app=app, runtime_config=runtime_config, bundle=bundle)


def create_app(config: Optional[Ae3RuntimeConfig] = None) -> FastAPI:
    return _app_runtime_application().create_app(config=config)


async def serve(config: Optional[Ae3RuntimeConfig] = None) -> None:
    return await _app_runtime_application().serve(config=config)


__all__ = ["create_app", "serve"]
