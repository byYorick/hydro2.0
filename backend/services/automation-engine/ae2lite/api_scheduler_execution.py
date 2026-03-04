"""Scheduler task execution helper for API layer decomposition."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import INFRA_UNKNOWN_ERROR, SCHEDULER_MODE_EXECUTION_EXCEPTION


async def _sync_workflow_state_on_execution_exception(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    task_id: str,
    correlation_id: Optional[str],
    scheduled_for: Optional[str],
    failure_result: Dict[str, Any],
    logger: logging.Logger,
) -> None:
    workflow_state_sync = getattr(executor, "workflow_state_sync", None)
    sync_fn = getattr(workflow_state_sync, "sync", None)
    if not callable(sync_fn):
        return
    try:
        await sync_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            result=failure_result,
            context={
                "task_id": task_id,
                "correlation_id": correlation_id,
                "scheduled_for": scheduled_for,
            },
        )
    except Exception as sync_exc:
        logger.warning(
            "Failed to sync workflow state after scheduler execution exception: task_id=%s zone_id=%s error=%s",
            task_id,
            zone_id,
            sync_exc,
            exc_info=True,
        )


async def execute_scheduler_task(
    task_id: str,
    req: Any,
    trace_id: Optional[str],
    *,
    command_bus: Any,
    command_bus_loop_id: Optional[int],
    zone_service: Any,
    zone_service_loop_id: Optional[int],
    validate_zone_exists_fn: Callable[[int], Awaitable[bool]],
    is_loop_affinity_mismatch_fn: Callable[[Optional[int]], bool],
    update_scheduler_task_fn: Callable[..., Awaitable[None]],
    update_command_effect_confirm_rate_fn: Callable[[str, Dict[str, Any]], None],
    normalize_failed_execution_result_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_execution_terminal_result_fn: Callable[..., Dict[str, Any]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    send_infra_resolved_alert_fn: Optional[Callable[..., Awaitable[Any]]],
    scheduler_task_executor_factory: Callable[..., Any],
    set_trace_id_fn: Callable[[Optional[str]], Any],
    logger: logging.Logger,
    err_command_bus_unavailable: str,
    err_command_bus_loop_mismatch: str,
    err_zone_service_loop_mismatch: str,
    err_zone_not_found: str,
    err_execution_exception: str,
) -> None:
    if trace_id:
        set_trace_id_fn(trace_id)

    if command_bus is None:
        failure_result = build_execution_terminal_result_fn(
            error_code=err_command_bus_unavailable,
            reason="CommandBus недоступен, задача не может быть исполнена",
            mode="dispatch_unavailable",
        )
        await update_scheduler_task_fn(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
        )
        return

    if is_loop_affinity_mismatch_fn(command_bus_loop_id):
        failure_result = build_execution_terminal_result_fn(
            error_code=err_command_bus_loop_mismatch,
            reason="CommandBus создан в другом event loop, выполнение задачи отклонено",
            mode="dispatch_unavailable",
        )
        await update_scheduler_task_fn(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
        )
        return

    zone_exists = True
    try:
        zone_exists = bool(await validate_zone_exists_fn(int(req.zone_id)))
    except Exception as exc:
        logger.warning(
            "Scheduler task zone existence check failed, continue execution: task_id=%s zone_id=%s error=%s",
            task_id,
            req.zone_id,
            exc,
            exc_info=True,
        )

    if not zone_exists:
        failure_result = build_execution_terminal_result_fn(
            error_code=err_zone_not_found,
            reason="Зона удалена или отсутствует, выполнение scheduler-task пропущено",
            mode="execution_skipped",
            action_required=False,
            decision="skip",
            reason_code=err_zone_not_found,
        )
        await update_scheduler_task_fn(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
        )
        return

    await update_scheduler_task_fn(task_id=task_id, status="running")

    executor: Any = None
    try:
        selected_zone_service = zone_service
        if is_loop_affinity_mismatch_fn(zone_service_loop_id):
            if req.task_type == "diagnostics":
                failure_result = build_execution_terminal_result_fn(
                    error_code=err_zone_service_loop_mismatch,
                    reason="ZoneAutomationService создан в другом event loop, diagnostics отклонен",
                    mode="execution_unavailable",
                )
                await update_scheduler_task_fn(
                    task_id=task_id,
                    status="failed",
                    result=failure_result,
                    error=str(failure_result["error"]),
                    error_code=str(failure_result["error_code"]),
                )
                return
            selected_zone_service = None

        executor = scheduler_task_executor_factory(
            command_bus=command_bus,
            zone_service=selected_zone_service,
        )
        result = await executor.execute(
            zone_id=req.zone_id,
            task_type=req.task_type,
            payload=req.payload or {},
            task_context={
                "task_id": task_id,
                "correlation_id": req.correlation_id,
                "scheduled_for": req.scheduled_for,
            },
        )
        result = result if isinstance(result, dict) else {}
        update_command_effect_confirm_rate_fn(req.task_type, result)
        success = bool(result.get("success"))
        failed_result = normalize_failed_execution_result_fn(result)
        await update_scheduler_task_fn(
            task_id=task_id,
            status="completed" if success else "failed",
            result=result if success else failed_result,
            error=None if success else str(failed_result["error"]),
            error_code=None if success else str(failed_result["error_code"]),
        )
        if callable(send_infra_resolved_alert_fn):
            try:
                await send_infra_resolved_alert_fn(
                    code=INFRA_UNKNOWN_ERROR,
                    alert_type="Automation Scheduler Task Execution Error",
                    message=f"Zone {req.zone_id}: scheduler-task execution path recovered",
                    zone_id=req.zone_id,
                    service="automation-engine",
                    component="api:/zones/{id}/start-cycle",
                    details={
                        "task_id": task_id,
                        "task_type": req.task_type,
                        "result_status": "success" if success else "failed",
                        "reason": "execution_without_unhandled_exception",
                    },
                )
            except Exception as resolve_exc:
                logger.warning(
                    "Scheduler task unknown-error resolve publish failed: task_id=%s zone_id=%s error=%s",
                    task_id,
                    req.zone_id,
                    resolve_exc,
                    exc_info=True,
                )
    except Exception as exc:
        logger.error(
            "Scheduler task execution failed: task_id=%s zone_id=%s task_type=%s error=%s",
            task_id,
            req.zone_id,
            req.task_type,
            exc,
            exc_info=True,
        )
        failure_result = build_execution_terminal_result_fn(
            error_code=err_execution_exception,
            reason="Во время исполнения scheduler-task произошло необработанное исключение",
            mode=SCHEDULER_MODE_EXECUTION_EXCEPTION,
            extra={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        if executor is not None:
            await _sync_workflow_state_on_execution_exception(
                executor=executor,
                zone_id=int(req.zone_id),
                task_type=str(req.task_type or ""),
                payload=req.payload if isinstance(req.payload, dict) else {},
                task_id=task_id,
                correlation_id=str(req.correlation_id or "") or None,
                scheduled_for=str(req.scheduled_for or "") or None,
                failure_result=failure_result,
                logger=logger,
            )
        await update_scheduler_task_fn(
            task_id=task_id,
            status="failed",
            result=failure_result,
            error=str(failure_result["error"]),
            error_code=str(failure_result["error_code"]),
        )
        await send_infra_exception_alert_fn(
            error=exc,
            code=INFRA_UNKNOWN_ERROR,
            alert_type="Automation Scheduler Task Execution Error",
            severity="error",
            zone_id=req.zone_id,
            service="automation-engine",
            component="api:/zones/{id}/start-cycle",
            error_type=type(exc).__name__,
            details={"task_id": task_id, "task_type": req.task_type},
        )


__all__ = ["execute_scheduler_task"]
