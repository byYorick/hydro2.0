from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, Request

from ae2lite.api_contracts import SchedulerTaskRequest, StartCycleRequest


def bind_start_cycle_route(
    app: FastAPI,
    *,
    validate_scheduler_zone_fn: Callable[[int], Awaitable[None]],
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    is_start_cycle_rate_limit_enabled_fn: Callable[[], bool],
    start_cycle_rate_limit_check_fn: Callable[[int], bool],
    start_cycle_rate_limit_window_sec_fn: Callable[[], int],
    start_cycle_rate_limit_max_requests_fn: Callable[[], int],
    claim_start_cycle_intent_fn: Callable[..., Awaitable[Dict[str, Any]]],
    start_cycle_claim_stale_sec_fn: Callable[[], int],
    load_latest_zone_task_fn: Callable[[int], Awaitable[Optional[Dict[str, Any]]]],
    load_zone_workflow_state_fn: Callable[[int], Awaitable[Optional[Dict[str, Any]]]],
    build_scheduler_task_request_from_intent_fn: Callable[..., SchedulerTaskRequest],
    start_cycle_due_sec_fn: Callable[[], int],
    start_cycle_expires_sec_fn: Callable[[], int],
    default_topology: str,
    create_scheduler_task_fn: Callable[..., Awaitable[Any]],
    get_trace_id_fn: Callable[[], Optional[str]],
    build_scheduler_single_writer_lease_key_fn: Callable[..., str],
    set_scheduler_single_writer_lease_fn: Callable[..., Awaitable[None]],
    execute_scheduler_task_with_single_writer_lease_fn: Callable[..., Awaitable[None]],
    release_scheduler_single_writer_lease_fn: Callable[[str], Awaitable[None]],
    mark_intent_running_fn: Callable[..., Awaitable[None]],
    mark_intent_terminal_fn: Callable[..., Awaitable[None]],
    mark_intent_pending_fn: Callable[..., Awaitable[None]],
    execute_fn: Callable[..., Awaitable[Any]],
    scheduler_tasks_ref: Dict[str, Dict[str, Any]],
    build_execution_terminal_result_fn: Callable[..., Dict[str, Any]],
    update_scheduler_task_fn: Callable[..., Awaitable[None]],
    spawn_background_task_fn: Callable[..., Any],
    build_start_cycle_response_fn: Callable[..., Dict[str, Any]],
    scheduler_err_execution_exception: str,
    logger: Any,
) -> Callable[..., Awaitable[Dict[str, Any]]]:
    async def _mark_intent_terminal_zone_busy(zone_id: int, intent_id: int, error_message: str) -> None:
        if intent_id <= 0:
            return
        try:
            await mark_intent_terminal_fn(
                intent_id=intent_id,
                now=datetime.now(timezone.utc).replace(tzinfo=None),
                success=False,
                error_code="start_cycle_zone_busy",
                error_message=error_message,
                execute_fn=execute_fn,
            )
        except Exception:
            logger.error(
                "Failed to mark intent terminal on zone_busy: zone_id=%s intent_id=%s",
                zone_id,
                intent_id,
                exc_info=True,
            )

    async def _fail_requested_intent_on_zone_busy(zone_id: int, intent_claim: Dict[str, Any]) -> None:
        requested_intent = (
            intent_claim.get("requested_intent")
            if isinstance(intent_claim, dict) and isinstance(intent_claim.get("requested_intent"), dict)
            else {}
        )
        requested_intent_id = int(requested_intent.get("id") or 0)
        requested_intent_status = str(requested_intent.get("status") or "").strip().lower()
        if requested_intent_id <= 0 or requested_intent_status not in {"pending", "claimed", "failed"}:
            return
        await _mark_intent_terminal_zone_busy(
            zone_id=zone_id,
            intent_id=requested_intent_id,
            error_message="Intent skipped: zone busy",
        )

    @app.post("/zones/{zone_id}/start-cycle")
    async def zone_start_cycle(zone_id: int, request: Request, req: StartCycleRequest = Body(...)):
        await validate_scheduler_zone_fn(zone_id)
        await validate_scheduler_security_baseline_fn(request)
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

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        intent_claim = await claim_start_cycle_intent_fn(
            zone_id=zone_id,
            req=req,
            now=now,
            claimed_stale_after_sec=start_cycle_claim_stale_sec_fn(),
        )
        intent = intent_claim.get("intent") if isinstance(intent_claim, dict) and isinstance(intent_claim.get("intent"), dict) else {}
        decision = str(intent_claim.get("decision") if isinstance(intent_claim, dict) else "").strip().lower()
        if decision == "deduplicated":
            intent_id = int(intent.get("id") or 0)
            return build_start_cycle_response_fn(
                zone_id=zone_id,
                req=req,
                is_duplicate=True,
                task_id=f"intent-{intent_id}" if intent_id > 0 else "",
            )
        if decision == "terminal":
            intent_id = int(intent.get("id") or 0)
            intent_status = str(intent.get("status") or "").strip().lower()
            return build_start_cycle_response_fn(
                zone_id=zone_id,
                req=req,
                is_duplicate=True,
                task_id=f"intent-{intent_id}" if intent_id > 0 else "",
                accepted=False,
                runner_state="terminal",
                task_status=intent_status or "failed",
                reason="start_cycle_intent_terminal",
            )
        if decision == "zone_busy":
            await _fail_requested_intent_on_zone_busy(zone_id, intent_claim if isinstance(intent_claim, dict) else {})
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_zone_busy",
                    "zone_id": zone_id,
                    "active_intent_id": int(intent.get("id") or 0) or None,
                    "active_status": str(intent.get("status") or "").strip().lower() or "running",
                },
            )
        if decision == "conflict_cross_zone":
            conflict_zone_id = int(intent.get("zone_id") or 0)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_idempotency_key_conflict",
                    "zone_id": zone_id,
                    "conflict_zone_id": conflict_zone_id,
                    "idempotency_key": req.idempotency_key,
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
        if decision != "claimed":
            raise HTTPException(status_code=503, detail={"error": "start_cycle_intent_claim_unavailable", "zone_id": zone_id})

        intent_id = int(intent.get("id") or 0)
        workflow_state = await load_zone_workflow_state_fn(zone_id)
        workflow_phase = str(workflow_state.get("workflow_phase") or "").strip().lower() if isinstance(workflow_state, dict) else ""
        workflow_scheduler_task_id = str(workflow_state.get("scheduler_task_id") or "").strip() or None if isinstance(workflow_state, dict) else None
        if workflow_phase not in {"", "idle", "ready"}:
            await _mark_intent_terminal_zone_busy(
                zone_id=zone_id,
                intent_id=intent_id,
                error_message=f"Intent skipped: zone busy (active_workflow_phase={workflow_phase or 'unknown'})",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_zone_busy",
                    "zone_id": zone_id,
                    "active_workflow_phase": workflow_phase,
                    "active_workflow_scheduler_task_id": workflow_scheduler_task_id,
                },
            )

        latest_task = await load_latest_zone_task_fn(zone_id)
        latest_status = str(latest_task.get("status") or "").strip().lower() if isinstance(latest_task, dict) else ""
        if latest_status in {"accepted", "running"}:
            await _mark_intent_terminal_zone_busy(
                zone_id=zone_id,
                intent_id=intent_id,
                error_message=f"Intent skipped: zone busy (active_task_status={latest_status or 'unknown'})",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "start_cycle_zone_busy",
                    "zone_id": zone_id,
                    "active_task_id": str(latest_task.get("task_id") or "").strip() or None,
                    "active_task_status": latest_status,
                },
            )

        start_cycle_req = build_scheduler_task_request_from_intent_fn(
            zone_id=zone_id,
            req=req,
            intent_row=intent,
            now=now,
            due_in_sec=start_cycle_due_sec_fn(),
            expires_in_sec=start_cycle_expires_sec_fn(),
            default_topology=default_topology,
        )
        task, is_duplicate = await create_scheduler_task_fn(start_cycle_req)
        task_id = str(task.get("task_id") or "")
        if not is_duplicate and task_id:
            trace_id = get_trace_id_fn()

            async def _run_start_cycle_intent() -> None:
                success = False
                terminal_error_code: Optional[str] = None
                terminal_error_message: Optional[str] = None
                lease_key = build_scheduler_single_writer_lease_key_fn(
                    zone_id=zone_id,
                    intent_id=intent_id,
                    task_id=task_id,
                )
                try:
                    await set_scheduler_single_writer_lease_fn(
                        lease_key=lease_key,
                        zone_id=zone_id,
                        intent_id=intent_id,
                        task_id=task_id,
                    )
                    if intent_id > 0:
                        await mark_intent_running_fn(
                            intent_id=intent_id,
                            now=datetime.now(timezone.utc).replace(tzinfo=None),
                            execute_fn=execute_fn,
                        )
                        await set_scheduler_single_writer_lease_fn(
                            lease_key=lease_key,
                            zone_id=zone_id,
                            intent_id=intent_id,
                            task_id=task_id,
                        )
                    await execute_scheduler_task_with_single_writer_lease_fn(
                        task_id,
                        start_cycle_req,
                        trace_id,
                        lease_key=lease_key,
                        zone_id=zone_id,
                        intent_id=intent_id,
                    )
                    snapshot = scheduler_tasks_ref.get(task_id) if isinstance(scheduler_tasks_ref.get(task_id), dict) else {}
                    success = str(snapshot.get("status") or "").strip().lower() == "completed"
                    terminal_error_code = str(snapshot.get("error_code") or "") or None
                    terminal_error_message = str(snapshot.get("error") or "") or None
                except Exception as exc:
                    logger.error(
                        "Start-cycle intent runner failed: zone_id=%s intent_id=%s task_id=%s error=%s",
                        zone_id,
                        intent_id,
                        task_id,
                        exc,
                        exc_info=True,
                    )
                    failure_result = build_execution_terminal_result_fn(
                        error_code=scheduler_err_execution_exception,
                        reason="Во время выполнения start-cycle intent произошло необработанное исключение",
                        mode="execution_exception",
                    )
                    terminal_error_code = str(failure_result.get("error_code") or scheduler_err_execution_exception)
                    terminal_error_message = str(failure_result.get("error") or str(exc))
                    try:
                        await update_scheduler_task_fn(
                            task_id=task_id,
                            status="failed",
                            result=failure_result,
                            error=terminal_error_message,
                            error_code=terminal_error_code,
                        )
                    except Exception:
                        logger.error(
                            "Failed to mark scheduler task failed after intent runner error: task_id=%s",
                            task_id,
                            exc_info=True,
                        )
                finally:
                    if intent_id > 0:
                        try:
                            await mark_intent_terminal_fn(
                                intent_id=intent_id,
                                now=datetime.now(timezone.utc).replace(tzinfo=None),
                                success=success,
                                error_code=terminal_error_code,
                                error_message=terminal_error_message,
                                execute_fn=execute_fn,
                            )
                        except Exception:
                            logger.error(
                                "Failed to mark intent terminal: zone_id=%s intent_id=%s",
                                zone_id,
                                intent_id,
                                exc_info=True,
                            )
                    await release_scheduler_single_writer_lease_fn(lease_key)

            spawn_background_task_fn(
                _run_start_cycle_intent(),
                task_name=f"start_cycle_intent_{intent_id or task_id}",
                zone_id=zone_id,
            )

        return build_start_cycle_response_fn(
            zone_id=zone_id,
            req=req,
            is_duplicate=bool(is_duplicate),
            task_id=f"intent-{intent_id}" if intent_id > 0 else task_id,
        )

    return zone_start_cycle


__all__ = ["bind_start_cycle_route"]
