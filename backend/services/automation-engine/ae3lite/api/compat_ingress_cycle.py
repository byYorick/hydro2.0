"""compat ingress cycle: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any, Awaitable, Callable, Mapping

from fastapi import Body, FastAPI, Path, Request

from ae3lite.api.contracts import (
    StartCycleRequest,
)
from ae3lite.api.http_errors import api_error_detail


@dataclass(frozen=True)
class CompatIngressCyclePorts:
    error_extra: Callable[..., Any]
    log_route_info: Callable[..., Any]
    normalized_status: Callable[..., Any]
    optional_int: Callable[..., Any]
    utcnow: Callable[..., Any]
    get_trace_id: Callable[..., Any]


class CompatIngressCycle:
    def __init__(self, ports: CompatIngressCyclePorts) -> None:
        self._ports = ports

    def bind_start_cycle_route(
        self,
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
                    now=self._ports.utcnow(),
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
                        self._ports.get_trace_id(),
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

            now = self._ports.utcnow()
            intent_claim = await claim_start_cycle_intent_fn(
                zone_id=zone_id,
                req=req,
                now=now,
            )
            decision = str(intent_claim.get("decision") or "").strip().lower()
            intent = intent_claim.get("intent")
            intent_row = dict(intent) if isinstance(intent, Mapping) else {}

            if decision in {"zone_busy", "claim_race"}:
                # Laravel treats 409 busy as retryable; keep requested intent pending
                # so the same idempotency_key can be reclaimed after the zone frees.
                # claim_race is concurrent SKIP LOCKED — same retryable busy, not 503.
                active_status = self._ports.normalized_status(intent_row.get("status"))
                raise api_error_detail(
                    "start_cycle_zone_busy",
                    status_code=409,
                    zone_id=zone_id,
                    active_intent_id=self._ports.optional_int(intent_row.get("id")),
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
                    # Keep requested intent pending/claimed so Laravel retries the same key.
                    raise api_error_detail(
                        code,
                        status_code=409,
                        **self._ports.error_extra(details, zone_id=zone_id),
                    ) from exc
                if code == "start_cycle_intent_terminal":
                    raise api_error_detail(
                        code,
                        status_code=409,
                        **self._ports.error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                    ) from exc
                logger.error(
                    "AE3 compat start-cycle: create task failed zone_id=%s code=%s trace_id=%s error=%s",
                    zone_id,
                    code,
                    self._ports.get_trace_id(),
                    exc,
                    exc_info=True,
                )
                raise api_error_detail(
                    code,
                    status_code=503,
                    **self._ports.error_extra(details, zone_id=zone_id, idempotency_key=req.idempotency_key),
                ) from exc

            task = creation.task
            self._ports.log_route_info(
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
