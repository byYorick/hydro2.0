"""AE3-Lite ingress for canonical `POST /zones/{id}/start-cycle`."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Any, Awaitable, Callable, Mapping

from fastapi import Body, FastAPI, Path, Request

from ae3lite.api.contracts import (
    StartCycleRequest,
    StartIrrigationRequest,
    StartLightingTickRequest,
    StartSolutionChangeRequest,
    StartSolutionTopupRequest,
)
from ae3lite.api.http_errors import api_error_detail
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.errors import ErrorCodes, TaskCreateError
from ae3lite.infrastructure.metrics import IRRIGATION_BLOCKED
from common.db import create_zone_event
from common.trace_context import get_trace_id
from common.utils.time import utcnow_naive as _utcnow


from ae3lite.api.compat_ingress_values import CompatIngressValues, CompatIngressValuesPorts


def _compat_ingress_values() -> CompatIngressValues:
    return CompatIngressValues(CompatIngressValuesPorts())


from ae3lite.api.compat_ingress_cycle import CompatIngressCycle, CompatIngressCyclePorts


def _compat_ingress_cycle() -> CompatIngressCycle:
    return CompatIngressCycle(
        CompatIngressCyclePorts(
            error_extra=lambda *args, **kwargs: _error_extra(*args, **kwargs),
            log_route_info=lambda *args, **kwargs: _log_route_info(*args, **kwargs),
            normalized_status=lambda *args, **kwargs: _normalized_status(*args, **kwargs),
            optional_int=lambda *args, **kwargs: _optional_int(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
        )
    )


from ae3lite.api.compat_ingress_irrigation import CompatIngressIrrigation, CompatIngressIrrigationPorts


def _compat_ingress_irrigation() -> CompatIngressIrrigation:
    return CompatIngressIrrigation(
        CompatIngressIrrigationPorts(
            irrigation_blocked=lambda: IRRIGATION_BLOCKED,
            error_extra=lambda *args, **kwargs: _error_extra(*args, **kwargs),
            log_route_info=lambda *args, **kwargs: _log_route_info(*args, **kwargs),
            normalized_status=lambda *args, **kwargs: _normalized_status(*args, **kwargs),
            optional_int=lambda *args, **kwargs: _optional_int(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
        )
    )


from ae3lite.api.compat_ingress_lighting import CompatIngressLighting, CompatIngressLightingPorts


def _compat_ingress_lighting() -> CompatIngressLighting:
    return CompatIngressLighting(
        CompatIngressLightingPorts(
            error_extra=lambda *args, **kwargs: _error_extra(*args, **kwargs),
            log_route_info=lambda *args, **kwargs: _log_route_info(*args, **kwargs),
            normalized_status=lambda *args, **kwargs: _normalized_status(*args, **kwargs),
            optional_int=lambda *args, **kwargs: _optional_int(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
        )
    )


from ae3lite.api.compat_ingress_topup import CompatIngressTopup, CompatIngressTopupPorts


def _compat_ingress_topup() -> CompatIngressTopup:
    return CompatIngressTopup(
        CompatIngressTopupPorts(
            error_extra=lambda *args, **kwargs: _error_extra(*args, **kwargs),
            log_route_info=lambda *args, **kwargs: _log_route_info(*args, **kwargs),
            normalized_status=lambda *args, **kwargs: _normalized_status(*args, **kwargs),
            optional_int=lambda *args, **kwargs: _optional_int(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
        )
    )


from ae3lite.api.compat_ingress_change import CompatIngressChange, CompatIngressChangePorts


def _compat_ingress_change() -> CompatIngressChange:
    return CompatIngressChange(
        CompatIngressChangePorts(
            error_extra=lambda *args, **kwargs: _error_extra(*args, **kwargs),
            log_route_info=lambda *args, **kwargs: _log_route_info(*args, **kwargs),
            normalized_status=lambda *args, **kwargs: _normalized_status(*args, **kwargs),
            optional_int=lambda *args, **kwargs: _optional_int(*args, **kwargs),
            utcnow=lambda *args, **kwargs: _utcnow(*args, **kwargs),
            get_trace_id=lambda *args, **kwargs: get_trace_id(*args, **kwargs),
        )
    )


def _optional_int(value: Any) -> int | None:
    return _compat_ingress_values().optional_int(value=value)


def _normalized_status(value: Any) -> str | None:
    return _compat_ingress_values().normalized_status(value=value)


def _error_extra(details: Any, **overrides: Any) -> dict[str, Any]:
    return _compat_ingress_values().error_extra(details=details, **overrides)


def _log_route_info(logger: Any, message: str, **extra: object) -> None:
    return _compat_ingress_values().log_route_info(logger=logger, message=message, **extra)


def bind_start_cycle_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    is_start_cycle_rate_limit_enabled_fn: Callable[[], bool],
    start_cycle_rate_limit_check_fn: Callable[[int], bool],
    start_cycle_rate_limit_window_sec_fn: Callable[[], int],
    start_cycle_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_cycle_intent_fn: Callable[..., Awaitable[dict[str, Any]]],
    create_task_from_intent_fn: Callable[..., Awaitable[Any]],
    ensure_solution_tank_startup_reset_fn: Callable[..., Awaitable[dict[str, Any]]] | None,
    kick_worker_fn: Callable[[], Any],
    build_start_cycle_response_fn: Callable[..., dict[str, Any]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    logger: Any,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    return _compat_ingress_cycle().bind_start_cycle_route(
        app=app,
        validate_scheduler_zone_fn=validate_scheduler_zone_fn,
        validate_scheduler_security_baseline_fn=validate_scheduler_security_baseline_fn,
        is_start_cycle_rate_limit_enabled_fn=is_start_cycle_rate_limit_enabled_fn,
        start_cycle_rate_limit_check_fn=start_cycle_rate_limit_check_fn,
        start_cycle_rate_limit_window_sec_fn=start_cycle_rate_limit_window_sec_fn,
        start_cycle_rate_limit_max_requests_fn=start_cycle_rate_limit_max_requests_fn,
        claim_start_cycle_intent_fn=claim_start_cycle_intent_fn,
        create_task_from_intent_fn=create_task_from_intent_fn,
        ensure_solution_tank_startup_reset_fn=ensure_solution_tank_startup_reset_fn,
        kick_worker_fn=kick_worker_fn,
        build_start_cycle_response_fn=build_start_cycle_response_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        logger=logger,
    )


def bind_start_irrigation_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    is_start_irrigation_rate_limit_enabled_fn: Callable[[], bool],
    start_irrigation_rate_limit_check_fn: Callable[[int], bool],
    start_irrigation_rate_limit_window_sec_fn: Callable[[], int],
    start_irrigation_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_irrigation_intent_fn: Callable[..., Awaitable[dict[str, Any]]],
    load_zone_workflow_phase_fn: Callable[[int], Awaitable[str | None]],
    create_task_from_intent_fn: Callable[..., Awaitable[Any]],
    kick_worker_fn: Callable[[], Any],
    build_start_cycle_response_fn: Callable[..., dict[str, Any]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    logger: Any,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    return _compat_ingress_irrigation().bind_start_irrigation_route(
        app=app,
        validate_scheduler_zone_fn=validate_scheduler_zone_fn,
        validate_scheduler_security_baseline_fn=validate_scheduler_security_baseline_fn,
        is_start_irrigation_rate_limit_enabled_fn=is_start_irrigation_rate_limit_enabled_fn,
        start_irrigation_rate_limit_check_fn=start_irrigation_rate_limit_check_fn,
        start_irrigation_rate_limit_window_sec_fn=start_irrigation_rate_limit_window_sec_fn,
        start_irrigation_rate_limit_max_requests_fn=start_irrigation_rate_limit_max_requests_fn,
        claim_start_irrigation_intent_fn=claim_start_irrigation_intent_fn,
        load_zone_workflow_phase_fn=load_zone_workflow_phase_fn,
        create_task_from_intent_fn=create_task_from_intent_fn,
        kick_worker_fn=kick_worker_fn,
        build_start_cycle_response_fn=build_start_cycle_response_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        logger=logger,
    )


def bind_start_lighting_tick_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    is_start_lighting_tick_rate_limit_enabled_fn: Callable[[], bool],
    start_lighting_tick_rate_limit_check_fn: Callable[[int], bool],
    start_lighting_tick_rate_limit_window_sec_fn: Callable[[], int],
    start_lighting_tick_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_lighting_tick_intent_fn: Callable[..., Awaitable[dict[str, Any]]],
    create_task_from_intent_fn: Callable[..., Awaitable[Any]],
    kick_worker_fn: Callable[[], Any],
    build_start_cycle_response_fn: Callable[..., dict[str, Any]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    logger: Any,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    return _compat_ingress_lighting().bind_start_lighting_tick_route(
        app=app,
        validate_scheduler_zone_fn=validate_scheduler_zone_fn,
        validate_scheduler_security_baseline_fn=validate_scheduler_security_baseline_fn,
        is_start_lighting_tick_rate_limit_enabled_fn=is_start_lighting_tick_rate_limit_enabled_fn,
        start_lighting_tick_rate_limit_check_fn=start_lighting_tick_rate_limit_check_fn,
        start_lighting_tick_rate_limit_window_sec_fn=start_lighting_tick_rate_limit_window_sec_fn,
        start_lighting_tick_rate_limit_max_requests_fn=start_lighting_tick_rate_limit_max_requests_fn,
        claim_start_lighting_tick_intent_fn=claim_start_lighting_tick_intent_fn,
        create_task_from_intent_fn=create_task_from_intent_fn,
        kick_worker_fn=kick_worker_fn,
        build_start_cycle_response_fn=build_start_cycle_response_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        logger=logger,
    )


def bind_start_solution_topup_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    load_zone_workflow_phase_fn: Callable[[int], Awaitable[str | None]],
    is_start_solution_topup_rate_limit_enabled_fn: Callable[[], bool],
    start_solution_topup_rate_limit_check_fn: Callable[[int], bool],
    start_solution_topup_rate_limit_window_sec_fn: Callable[[], int],
    start_solution_topup_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_solution_topup_intent_fn: Callable[..., Awaitable[dict[str, Any]]],
    create_task_from_intent_fn: Callable[..., Awaitable[Any]],
    kick_worker_fn: Callable[[], Any],
    build_start_cycle_response_fn: Callable[..., dict[str, Any]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    logger: Any,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    return _compat_ingress_topup().bind_start_solution_topup_route(
        app=app,
        validate_scheduler_zone_fn=validate_scheduler_zone_fn,
        validate_scheduler_security_baseline_fn=validate_scheduler_security_baseline_fn,
        load_zone_workflow_phase_fn=load_zone_workflow_phase_fn,
        is_start_solution_topup_rate_limit_enabled_fn=is_start_solution_topup_rate_limit_enabled_fn,
        start_solution_topup_rate_limit_check_fn=start_solution_topup_rate_limit_check_fn,
        start_solution_topup_rate_limit_window_sec_fn=start_solution_topup_rate_limit_window_sec_fn,
        start_solution_topup_rate_limit_max_requests_fn=start_solution_topup_rate_limit_max_requests_fn,
        claim_start_solution_topup_intent_fn=claim_start_solution_topup_intent_fn,
        create_task_from_intent_fn=create_task_from_intent_fn,
        kick_worker_fn=kick_worker_fn,
        build_start_cycle_response_fn=build_start_cycle_response_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        logger=logger,
    )


def bind_start_solution_change_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    load_zone_workflow_phase_fn: Callable[[int], Awaitable[str | None]],
    is_start_solution_change_rate_limit_enabled_fn: Callable[[], bool],
    start_solution_change_rate_limit_check_fn: Callable[[int], bool],
    start_solution_change_rate_limit_window_sec_fn: Callable[[], int],
    start_solution_change_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_solution_change_intent_fn: Callable[..., Awaitable[dict[str, Any]]],
    create_task_from_intent_fn: Callable[..., Awaitable[Any]],
    kick_worker_fn: Callable[[], Any],
    build_start_cycle_response_fn: Callable[..., dict[str, Any]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    logger: Any,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    return _compat_ingress_change().bind_start_solution_change_route(
        app=app,
        validate_scheduler_zone_fn=validate_scheduler_zone_fn,
        validate_scheduler_security_baseline_fn=validate_scheduler_security_baseline_fn,
        load_zone_workflow_phase_fn=load_zone_workflow_phase_fn,
        is_start_solution_change_rate_limit_enabled_fn=is_start_solution_change_rate_limit_enabled_fn,
        start_solution_change_rate_limit_check_fn=start_solution_change_rate_limit_check_fn,
        start_solution_change_rate_limit_window_sec_fn=start_solution_change_rate_limit_window_sec_fn,
        start_solution_change_rate_limit_max_requests_fn=start_solution_change_rate_limit_max_requests_fn,
        claim_start_solution_change_intent_fn=claim_start_solution_change_intent_fn,
        create_task_from_intent_fn=create_task_from_intent_fn,
        kick_worker_fn=kick_worker_fn,
        build_start_cycle_response_fn=build_start_cycle_response_fn,
        mark_intent_terminal_fn=mark_intent_terminal_fn,
        logger=logger,
    )
