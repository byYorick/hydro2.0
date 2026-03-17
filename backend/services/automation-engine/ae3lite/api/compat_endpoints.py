"""AE3-Lite ingress for canonical `POST /zones/{id}/start-cycle`."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from fastapi import Body, FastAPI, HTTPException, Request

from ae3lite.api.contracts import StartCycleRequest
from common.utils.time import utcnow_naive as _utcnow


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
                "AE3 compat start-cycle failed to mark current intent terminal: intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _mark_requested_intent_terminal_zone_busy(intent_claim: Mapping[str, Any], zone_id: int) -> None:
        requested = intent_claim.get("requested_intent")
        requested_intent = requested if isinstance(requested, Mapping) else {}
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_status not in {"pending", "claimed", "failed"}:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=requested_intent_id,
                now=_utcnow(),
                success=False,
                error_code="start_cycle_zone_busy",
                error_message=f"Intent skipped: zone busy (zone_id={zone_id})",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "AE3 compat start-cycle failed to mark requested intent terminal: zone_id=%s intent_id=%s",
                zone_id,
                requested_intent_id,
                exc_info=True,
            )

    @app.post("/zones/{zone_id}/start-cycle")
    async def zone_start_cycle(zone_id: int, request: Request, req: StartCycleRequest = Body(...)) -> dict[str, Any]:
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
        if ensure_solution_tank_startup_reset_fn is not None:
            try:
                await ensure_solution_tank_startup_reset_fn(zone_id=zone_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "AE3 compat start-cycle solution tank guard failed: zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "start_cycle_solution_tank_guard_failed",
                        "zone_id": zone_id,
                        "message": str(exc) or "solution tank startup guard failed",
                    },
                ) from exc

        if is_start_cycle_rate_limit_enabled_fn() and not start_cycle_rate_limit_check_fn(zone_id):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "start_cycle_rate_limited",
                    "zone_id": zone_id,
                    "window_sec": start_cycle_rate_limit_window_sec_fn(),
                    "max_requests": start_cycle_rate_limit_max_requests_fn(),
                },
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
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_zone_busy",
                    "zone_id": zone_id,
                    "active_intent_id": (lambda v: int(v) if v is not None else None)(intent_row.get("id")),
                    "active_status": str(intent_row.get("status") or "").strip().lower() or "running",
                },
            )
        if decision == "missing":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_intent_not_found",
                    "zone_id": zone_id,
                    "idempotency_key": req.idempotency_key,
                },
            )
        if decision not in {"claimed", "deduplicated", "terminal"}:
            raise HTTPException(status_code=503, detail={"error": "start_cycle_intent_claim_unavailable", "zone_id": zone_id})

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
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": code,
                        "zone_id": zone_id,
                        **(details if isinstance(details, dict) else {}),
                    },
                ) from exc
            if code == "start_cycle_intent_terminal":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": code,
                        "zone_id": zone_id,
                        "idempotency_key": req.idempotency_key,
                        **(details if isinstance(details, dict) else {}),
                    },
                ) from exc
            raise

        task = creation.task
        _log_debug(
            "AE3 compat start-cycle created task: zone_id=%s task_id=%s status=%s created=%s decision=%s",
            zone_id,
            task.id,
            task.status,
            creation.created,
            decision,
        )
        if task.status in {"pending", "claimed", "running", "waiting_command"}:
            _log_debug("AE3 compat start-cycle kicking worker: zone_id=%s task_id=%s", zone_id, task.id)
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
