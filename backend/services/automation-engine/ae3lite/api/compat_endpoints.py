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


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _normalized_status(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _error_extra(details: Any, **overrides: Any) -> dict[str, Any]:
    """Merge exception details with path/body overrides into one kwargs dict.

    Overrides win over ``details`` so callers can safely do
    ``api_error_detail(code, status_code=..., **_error_extra(details, zone_id=zone_id))``.
    Passing ``zone_id=zone_id, **details`` separately raises ``KeyError('zone_id')``
    under Python 3.11+ (DICT_MERGE on duplicate keyword keys).
    """
    payload = dict(details if isinstance(details, dict) else {})
    payload.update(overrides)
    return payload


def _log_route_info(logger: Any, message: str, **extra: object) -> None:
    info = getattr(logger, "info", None)
    if callable(info):
        info(message, extra=extra)


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
    def _log_debug(message: str, *args: object) -> None:
        debug = getattr(logger, "debug", None)
        if callable(debug):
            debug(message, *args)

    async def _mark_current_intent_terminal(
        *,
        intent_row: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        intent_id = int(intent_row.get("id") or 0)
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=_utcnow(),
                success=False,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-cycle не смог перевести текущий intent в terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed", "running"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_cycle_zone_busy",
                error_message=f"Запуск отклонён: зона занята (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-cycle не смог перевести запрошенный intent в terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-cycle")
    async def zone_start_cycle(
        zone_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartCycleRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        if ensure_solution_tank_startup_reset_fn is not None:
            try:
                await ensure_solution_tank_startup_reset_fn(zone_id=zone_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "AE3 compat start-cycle: startup guard бака раствора завершился ошибкой zone_id=%s trace_id=%s error=%s",
                    zone_id,
                    get_trace_id(),
                    exc,
                    exc_info=True,
                )
                raise api_error_detail(
                    "start_cycle_solution_tank_guard_failed",
                    status_code=503,
                    zone_id=zone_id,
                ) from exc

        if is_start_cycle_rate_limit_enabled_fn() and not start_cycle_rate_limit_check_fn(zone_id):
            raise api_error_detail(
                "start_cycle_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=start_cycle_rate_limit_window_sec_fn(),
                max_requests=start_cycle_rate_limit_max_requests_fn(),
            )

        now = _utcnow()
        intent_claim = await claim_start_cycle_intent_fn(
            zone_id=zone_id,
            req=req,
            now=now,
        )
        decision = str(intent_claim.get("decision") or "").strip().lower()
        intent = intent_claim.get("intent")
        intent_row = dict(intent) if isinstance(intent, Mapping) else {}

        if decision == "zone_busy":
            await _mark_requested_intent_terminal_zone_busy(intent_claim, zone_id)
            active_status = _normalized_status(intent_row.get("status"))
            raise api_error_detail(
                "start_cycle_zone_busy",
                status_code=409,
                zone_id=zone_id,
                active_intent_id=_optional_int(intent_row.get("id")),
                active_status=active_status,
            )
        if decision == "missing":
            raise api_error_detail(
                "start_cycle_intent_not_found",
                status_code=409,
                zone_id=zone_id,
                idempotency_key=req.idempotency_key,
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise api_error_detail(
                "start_cycle_intent_claim_unavailable",
                status_code=503,
                zone_id=zone_id,
            )

        try:
            creation = await create_task_from_intent_fn(
                zone_id=zone_id,
                source=req.source,
                idempotency_key=req.idempotency_key,
                intent_row=intent_row,
                now=now,
                allow_create=decision != "terminal",
            )
        except Exception as exc:
            code = str(getattr(exc, "code", "ae3_task_create_failed")).strip() or "ae3_task_create_failed"
            details = getattr(exc, "details", {})
            if code == "start_cycle_zone_busy":
                await _mark_current_intent_terminal(
                    intent_row=intent_row,
                    error_code=code,
                    error_message=str(exc),
                )
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id),
                ) from exc
            if code == "start_cycle_intent_terminal":
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc
            logger.error(
                "AE3 compat start-cycle: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                zone_id,
                code,
                get_trace_id(),
                exc,
                exc_info=True,
            )
            raise api_error_detail(
                code,
                status_code=503,
                **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
            ) from exc

        task = creation.task
        _log_route_info(
            logger,
            "AE3 compat start-cycle dispatch accepted",
            zone_id=zone_id,
            task_id=int(task.id),
            idempotency_key=str(req.idempotency_key or "").strip() or None,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            _log_debug("AE3 compat start-cycle будит worker: zone_id=%s task_id=%s", zone_id, task.id)
            kick_worker_fn()

        accepted = task.status not in {"completed", "failed", "cancelled"}
        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=(decision != "claimed") or (not creation.created),
            task_id=str(task.id),
            accepted=accepted,
            runner_state="active" if accepted else "terminal",
            task_status=task.status if not accepted else None,
            reason="start_cycle_intent_terminal" if decision == "terminal" else None,
        )

    return zone_start_cycle


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
    async def _mark_current_intent_terminal(
        *,
        intent_row: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        intent_id = int(intent_row.get("id") or 0)
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=_utcnow(),
                success=False,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-irrigation не смог перевести текущий intent в terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed", "running"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_irrigation_zone_busy",
                error_message=f"Запуск отклонён: зона занята (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-irrigation не смог перевести запрошенный intent в terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-irrigation")
    async def zone_start_irrigation(
        zone_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartIrrigationRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        workflow_phase = str((await load_zone_workflow_phase_fn(zone_id)) or "").strip().lower()
        if workflow_phase != "ready":
            IRRIGATION_BLOCKED.labels(reason="setup_pending").inc()
            event_payload = with_runtime_event_contract(
                {
                    "zone_id": int(zone_id),
                    "workflow_phase": workflow_phase if workflow_phase != "" else "missing",
                    "reason": "setup_pending",
                    "source": str(req.source or "").strip().lower() or None,
                    "idempotency_key": str(req.idempotency_key or "").strip() or None,
                    "requested_mode": str(req.mode or "").strip().lower() or None,
                }
            )
            event_payload = {key: value for key, value in event_payload.items() if value is not None}
            try:
                await create_zone_event(
                    int(zone_id),
                    "IRRIGATION_BLOCKED_SETUP_PENDING",
                    event_payload,
                )
            except Exception:
                logger.warning(
                    "AE3 compat start-irrigation не смог записать IRRIGATION_BLOCKED_SETUP_PENDING zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
            raise api_error_detail(
                ErrorCodes.START_IRRIGATION_SETUP_PENDING,
                status_code=409,
                zone_id=zone_id,
                workflow_phase=workflow_phase if workflow_phase != "" else "missing",
            )
        if is_start_irrigation_rate_limit_enabled_fn() and not start_irrigation_rate_limit_check_fn(zone_id):
            raise api_error_detail(
                "start_irrigation_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=start_irrigation_rate_limit_window_sec_fn(),
                max_requests=start_irrigation_rate_limit_max_requests_fn(),
            )

        now = _utcnow()
        intent_claim = await claim_start_irrigation_intent_fn(zone_id=zone_id, req=req, now=now)
        decision = str(intent_claim.get("decision") or "").strip().lower()
        intent = intent_claim.get("intent")
        intent_row = dict(intent) if isinstance(intent, Mapping) else {}

        if decision == "zone_busy":
            await _mark_requested_intent_terminal_zone_busy(intent_claim, zone_id)
            active_status = _normalized_status(intent_row.get("status"))
            raise api_error_detail(
                "start_irrigation_zone_busy",
                status_code=409,
                zone_id=zone_id,
                active_intent_id=_optional_int(intent_row.get("id")),
                active_status=active_status,
            )
        if decision == "missing":
            raise api_error_detail(
                "start_irrigation_intent_not_found",
                status_code=409,
                zone_id=zone_id,
                idempotency_key=req.idempotency_key,
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise api_error_detail(
                "start_irrigation_intent_claim_unavailable",
                status_code=503,
                zone_id=zone_id,
            )

        try:
            creation = await create_task_from_intent_fn(
                zone_id=zone_id,
                source=req.source,
                idempotency_key=req.idempotency_key,
                intent_row=intent_row,
                now=now,
                allow_create=decision != "terminal",
            )
        except Exception as exc:
            raw_code = str(getattr(exc, "code", "ae3_task_create_failed")).strip() or "ae3_task_create_failed"
            details = getattr(exc, "details", {})
            code = raw_code
            if raw_code == "start_cycle_zone_busy":
                code = "start_irrigation_zone_busy"
            elif raw_code == "start_cycle_intent_terminal":
                code = "start_irrigation_intent_terminal"

            if raw_code == "start_cycle_zone_busy":
                await _mark_current_intent_terminal(
                    intent_row=intent_row,
                    error_code=code,
                    error_message=str(exc),
                )
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id),
                ) from exc
            if raw_code == "start_cycle_intent_terminal":
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc
            logger.error(
                "AE3 compat start-irrigation: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                zone_id,
                code,
                get_trace_id(),
                exc,
                exc_info=True,
            )
            raise api_error_detail(
                code,
                status_code=503,
                **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
            ) from exc
        task = creation.task
        _log_route_info(
            logger,
            "AE3 compat start-irrigation dispatch accepted",
            zone_id=zone_id,
            task_id=int(task.id),
            idempotency_key=str(req.idempotency_key or "").strip() or None,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            kick_worker_fn()

        accepted = task.status not in {"completed", "failed", "cancelled"}
        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=(decision != "claimed") or (not creation.created),
            task_id=str(task.id),
            accepted=accepted,
            runner_state="active" if accepted else "terminal",
            task_status=task.status if not accepted else None,
            reason="start_irrigation_intent_terminal" if decision == "terminal" else None,
        )

    return zone_start_irrigation


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
    async def _mark_current_intent_terminal(
        *,
        intent_row: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        intent_id = int(intent_row.get("id") or 0)
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=_utcnow(),
                success=False,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-lighting-tick не смог перевести текущий intent в terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed", "running"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_lighting_tick_zone_busy",
                error_message=f"Запуск отклонён: зона занята (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-lighting-tick не смог перевести запрошенный intent в terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-lighting-tick")
    async def zone_start_lighting_tick(
        zone_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartLightingTickRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        if is_start_lighting_tick_rate_limit_enabled_fn() and not start_lighting_tick_rate_limit_check_fn(zone_id):
            raise api_error_detail(
                "start_lighting_tick_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=start_lighting_tick_rate_limit_window_sec_fn(),
                max_requests=start_lighting_tick_rate_limit_max_requests_fn(),
            )

        now = _utcnow()
        intent_claim = await claim_start_lighting_tick_intent_fn(zone_id=zone_id, req=req, now=now)
        decision = str(intent_claim.get("decision") or "").strip().lower()
        intent = intent_claim.get("intent")
        intent_row = dict(intent) if isinstance(intent, Mapping) else {}

        if decision == "zone_busy":
            await _mark_requested_intent_terminal_zone_busy(intent_claim, zone_id)
            active_status = _normalized_status(intent_row.get("status"))
            raise api_error_detail(
                "start_lighting_tick_zone_busy",
                status_code=409,
                zone_id=zone_id,
                active_intent_id=_optional_int(intent_row.get("id")),
                active_status=active_status,
            )
        if decision == "missing":
            raise api_error_detail(
                "start_lighting_tick_intent_not_found",
                status_code=409,
                zone_id=zone_id,
                idempotency_key=req.idempotency_key,
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise api_error_detail(
                "start_lighting_tick_intent_claim_unavailable",
                status_code=503,
                zone_id=zone_id,
            )

        try:
            creation = await create_task_from_intent_fn(
                zone_id=zone_id,
                source=req.source,
                idempotency_key=req.idempotency_key,
                intent_row=intent_row,
                now=now,
                allow_create=decision != "terminal",
                lighting_desired_state=req.desired_state,
                lighting_brightness_pct=req.brightness_pct,
            )
        except Exception as exc:
            raw_code = str(getattr(exc, "code", "ae3_task_create_failed")).strip() or "ae3_task_create_failed"
            details = getattr(exc, "details", {})
            code = raw_code
            if raw_code == "start_cycle_zone_busy":
                code = "start_lighting_tick_zone_busy"
            elif raw_code == "start_cycle_intent_terminal":
                code = "start_lighting_tick_intent_terminal"

            if raw_code == "start_cycle_zone_busy":
                await _mark_current_intent_terminal(
                    intent_row=intent_row,
                    error_code=code,
                    error_message=str(exc),
                )
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id),
                ) from exc
            if raw_code == "start_cycle_intent_terminal":
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc
            logger.error(
                "AE3 compat start-lighting-tick: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                zone_id,
                code,
                get_trace_id(),
                exc,
                exc_info=True,
            )
            raise api_error_detail(
                code,
                status_code=503,
                **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
            ) from exc
        task = creation.task
        _log_route_info(
            logger,
            "AE3 compat start-lighting-tick dispatch accepted",
            zone_id=zone_id,
            task_id=int(task.id),
            idempotency_key=str(req.idempotency_key or "").strip() or None,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            kick_worker_fn()

        accepted = task.status not in {"completed", "failed", "cancelled"}
        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=(decision != "claimed") or (not creation.created),
            task_id=str(task.id),
            accepted=accepted,
            runner_state="active" if accepted else "terminal",
            task_status=task.status if not accepted else None,
            reason="start_lighting_tick_intent_terminal" if decision == "terminal" else None,
        )

    return zone_start_lighting_tick


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
    async def _mark_current_intent_terminal(
        *,
        intent_row: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        intent_id = int(intent_row.get("id") or 0)
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=_utcnow(),
                success=False,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-solution-topup не смог перевести текущий intent в terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed", "running"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_solution_topup_zone_busy",
                error_message=f"Запуск отклонён: зона занята (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-solution-topup не смог перевести запрошенный intent в terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-solution-topup")
    async def zone_start_solution_topup(
        zone_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartSolutionTopupRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        workflow_phase = str((await load_zone_workflow_phase_fn(zone_id)) or "").strip().lower()
        if workflow_phase != "ready":
            raise api_error_detail(
                "start_solution_topup_not_ready",
                status_code=409,
                zone_id=zone_id,
                workflow_phase=workflow_phase if workflow_phase != "" else "missing",
            )
        if is_start_solution_topup_rate_limit_enabled_fn() and not start_solution_topup_rate_limit_check_fn(zone_id):
            raise api_error_detail(
                "start_solution_topup_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=start_solution_topup_rate_limit_window_sec_fn(),
                max_requests=start_solution_topup_rate_limit_max_requests_fn(),
            )

        now = _utcnow()
        intent_claim = await claim_start_solution_topup_intent_fn(zone_id=zone_id, req=req, now=now)
        decision = str(intent_claim.get("decision") or "").strip().lower()
        intent = intent_claim.get("intent")
        intent_row = dict(intent) if isinstance(intent, Mapping) else {}

        if decision == "zone_busy":
            await _mark_requested_intent_terminal_zone_busy(intent_claim, zone_id)
            active_status = _normalized_status(intent_row.get("status"))
            raise api_error_detail(
                "start_solution_topup_zone_busy",
                status_code=409,
                zone_id=zone_id,
                active_intent_id=_optional_int(intent_row.get("id")),
                active_status=active_status,
            )
        if decision == "missing":
            raise api_error_detail(
                "start_solution_topup_intent_not_found",
                status_code=409,
                zone_id=zone_id,
                idempotency_key=req.idempotency_key,
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise api_error_detail(
                "start_solution_topup_intent_claim_unavailable",
                status_code=503,
                zone_id=zone_id,
            )

        try:
            creation = await create_task_from_intent_fn(
                zone_id=zone_id,
                source=req.source,
                idempotency_key=req.idempotency_key,
                intent_row=intent_row,
                now=now,
                allow_create=decision != "terminal",
                solution_topup_mode=req.mode,
                solution_topup_trigger=req.trigger,
            )
        except Exception as exc:
            raw_code = str(getattr(exc, "code", "ae3_task_create_failed")).strip() or "ae3_task_create_failed"
            details = getattr(exc, "details", {})
            code = raw_code
            if raw_code == "start_cycle_zone_busy":
                code = "start_solution_topup_zone_busy"
            elif raw_code == "start_cycle_intent_terminal":
                code = "start_solution_topup_intent_terminal"

            if raw_code == "start_cycle_zone_busy":
                await _mark_current_intent_terminal(
                    intent_row=intent_row,
                    error_code=code,
                    error_message=str(exc),
                )
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id),
                ) from exc
            if raw_code == "start_cycle_intent_terminal":
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc
            status_code = 409 if code.startswith("start_solution_topup_") else 503
            logger.error(
                "AE3 compat start-solution-topup: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                zone_id,
                code,
                get_trace_id(),
                exc,
                exc_info=True,
            )
            raise api_error_detail(
                code,
                status_code=status_code,
                **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
            ) from exc
        task = creation.task
        _log_route_info(
            logger,
            "AE3 compat start-solution-topup dispatch accepted",
            zone_id=zone_id,
            task_id=int(task.id),
            idempotency_key=str(req.idempotency_key or "").strip() or None,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            kick_worker_fn()

        accepted = task.status not in {"completed", "failed", "cancelled"}
        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=(decision != "claimed") or (not creation.created),
            task_id=str(task.id),
            accepted=accepted,
            runner_state="active" if accepted else "terminal",
            task_status=task.status if not accepted else None,
            reason="start_solution_topup_intent_terminal" if decision == "terminal" else None,
        )

    return zone_start_solution_topup


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
    async def _mark_current_intent_terminal(
        *,
        intent_row: Mapping[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        intent_id = int(intent_row.get("id") or 0)
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=_utcnow(),
                success=False,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-solution-change не смог перевести текущий intent в terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed", "running"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_solution_change_zone_busy",
                error_message=f"Запуск отклонён: зона занята (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-solution-change не смог перевести запрошенный intent в terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-solution-change")
    async def zone_start_solution_change(
        zone_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartSolutionChangeRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        workflow_phase = str((await load_zone_workflow_phase_fn(zone_id)) or "").strip().lower()
        if workflow_phase != "ready":
            raise api_error_detail(
                "solution_change_zone_not_ready",
                status_code=409,
                zone_id=zone_id,
                workflow_phase=workflow_phase if workflow_phase != "" else "missing",
            )
        if is_start_solution_change_rate_limit_enabled_fn() and not start_solution_change_rate_limit_check_fn(zone_id):
            raise api_error_detail(
                "start_solution_change_rate_limited",
                status_code=429,
                zone_id=zone_id,
                window_sec=start_solution_change_rate_limit_window_sec_fn(),
                max_requests=start_solution_change_rate_limit_max_requests_fn(),
            )

        now = _utcnow()
        intent_claim = await claim_start_solution_change_intent_fn(zone_id=zone_id, req=req, now=now)
        decision = str(intent_claim.get("decision") or "").strip().lower()
        intent = intent_claim.get("intent")
        intent_row = dict(intent) if isinstance(intent, Mapping) else {}

        if decision == "zone_busy":
            await _mark_requested_intent_terminal_zone_busy(intent_claim, zone_id)
            active_status = _normalized_status(intent_row.get("status"))
            raise api_error_detail(
                "start_solution_change_zone_busy",
                status_code=409,
                zone_id=zone_id,
                active_intent_id=_optional_int(intent_row.get("id")),
                active_status=active_status,
            )
        if decision == "missing":
            raise api_error_detail(
                "start_solution_change_intent_not_found",
                status_code=409,
                zone_id=zone_id,
                idempotency_key=req.idempotency_key,
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise api_error_detail(
                "start_solution_change_intent_claim_unavailable",
                status_code=503,
                zone_id=zone_id,
            )

        try:
            creation = await create_task_from_intent_fn(
                zone_id=zone_id,
                source=req.source,
                idempotency_key=req.idempotency_key,
                intent_row=intent_row,
                now=now,
                allow_create=decision != "terminal",
            )
        except Exception as exc:
            raw_code = str(getattr(exc, "code", "ae3_task_create_failed")).strip() or "ae3_task_create_failed"
            details = getattr(exc, "details", {})
            code = raw_code
            if raw_code == "start_cycle_zone_busy":
                code = "start_solution_change_zone_busy"
            elif raw_code == "start_cycle_intent_terminal":
                code = "start_solution_change_intent_terminal"

            if raw_code == "start_cycle_zone_busy":
                await _mark_current_intent_terminal(
                    intent_row=intent_row,
                    error_code=code,
                    error_message=str(exc),
                )
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id),
                ) from exc
            if raw_code == "start_cycle_intent_terminal":
                raise api_error_detail(
                    code,
                    status_code=409,
                    **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc
            status_code = 409 if code.startswith(("start_solution_change_", "solution_change_")) else 503
            logger.error(
                "AE3 compat start-solution-change: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                zone_id,
                code,
                get_trace_id(),
                exc,
                exc_info=True,
            )
            raise api_error_detail(
                code,
                status_code=status_code,
                **_error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
            ) from exc
        task = creation.task
        _log_route_info(
            logger,
            "AE3 compat start-solution-change dispatch accepted",
            zone_id=zone_id,
            task_id=int(task.id),
            idempotency_key=str(req.idempotency_key or "").strip() or None,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            kick_worker_fn()

        accepted = task.status not in {"completed", "failed", "cancelled"}
        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=(decision != "claimed") or (not creation.created),
            task_id=str(task.id),
            accepted=accepted,
            runner_state="active" if accepted else "terminal",
            task_status=task.status if not accepted else None,
            reason="start_solution_change_intent_terminal" if decision == "terminal" else None,
        )

    return zone_start_solution_change
