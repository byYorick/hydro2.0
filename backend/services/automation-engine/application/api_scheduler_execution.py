"""Scheduler task execution helper for API layer decomposition."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import INFRA_UNKNOWN_ERROR


async def execute_scheduler_task(
    task_id: str,
    req: Any,
    trace_id: Optional[str],
    *,
    command_bus: Any,
    command_bus_loop_id: Optional[int],
    zone_service: Any,
    zone_service_loop_id: Optional[int],
    is_loop_affinity_mismatch_fn: Callable[[Optional[int]], bool],
    update_scheduler_task_fn: Callable[..., Awaitable[None]],
    update_command_effect_confirm_rate_fn: Callable[[str, Dict[str, Any]], None],
    normalize_failed_execution_result_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_execution_terminal_result_fn: Callable[..., Dict[str, Any]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    scheduler_task_executor_factory: Callable[..., Any],
    set_trace_id_fn: Callable[[Optional[str]], Any],
    logger: logging.Logger,
    err_command_bus_unavailable: str,
    err_command_bus_loop_mismatch: str,
    err_zone_service_loop_mismatch: str,
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

    await update_scheduler_task_fn(task_id=task_id, status="running")

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
            mode="execution_exception",
            extra={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
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
            component="api:/scheduler/task",
            error_type=type(exc).__name__,
            details={"task_id": task_id, "task_type": req.task_type},
        )


__all__ = ["execute_scheduler_task"]
