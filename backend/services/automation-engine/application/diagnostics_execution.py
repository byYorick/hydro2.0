"""Helpers for diagnostics execution branch."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from domain.models.decision_models import DecisionOutcome
from services.resilience_contract import INFRA_DIAGNOSTICS_SERVICE_UNAVAILABLE

EmitTaskEventFn = Callable[..., Awaitable[None]]
SendInfraAlertFn = Callable[..., Awaitable[Any]]
ProcessZoneFn = Callable[[int], Awaitable[None]]


def _diagnostics_unavailable_result(decision: DecisionOutcome, *, error_code: str, reason_code: str) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "diagnostics_unavailable",
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": decision.action_required,
        "decision": decision.decision,
        "reason_code": reason_code,
        "reason": "Diagnostics задача не может быть исполнена без ZoneAutomationService",
        "error": error_code,
        "error_code": error_code,
    }


def _diagnostics_failed_result(decision: DecisionOutcome, *, error_code: str, reason_code: str) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "diagnostics_failed",
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": decision.action_required,
        "decision": decision.decision,
        "reason_code": reason_code,
        "reason": "Diagnostics задача завершилась ошибкой ZoneAutomationService",
        "error": error_code,
        "error_code": error_code,
    }


async def execute_diagnostics(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    zone_service: Any,
    logger_obj: Any,
    reason_diagnostics_service_unavailable: str,
    err_diagnostics_service_unavailable: str,
    emit_task_event_fn: EmitTaskEventFn,
    send_infra_alert_fn: SendInfraAlertFn,
) -> Dict[str, Any]:
    if zone_service is None:
        await emit_task_event_fn(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="DIAGNOSTICS_SERVICE_UNAVAILABLE",
            payload={
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": reason_diagnostics_service_unavailable,
                "error_code": err_diagnostics_service_unavailable,
            },
        )
        await send_infra_alert_fn(
            code=INFRA_DIAGNOSTICS_SERVICE_UNAVAILABLE,
            alert_type="Diagnostics Service Unavailable",
            message="Diagnostics задача не выполнена: ZoneAutomationService недоступен",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=err_diagnostics_service_unavailable,
            details={"payload": payload},
        )
        return _diagnostics_unavailable_result(
            decision,
            error_code=err_diagnostics_service_unavailable,
            reason_code=reason_diagnostics_service_unavailable,
        )

    try:
        await zone_service.process_zone(zone_id)
        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "zone_service",
            "commands_total": 0,
            "commands_failed": 0,
        }
    except Exception as exc:
        logger_obj.warning(
            "Zone %s: diagnostics via zone_service failed: %s",
            zone_id,
            exc,
            exc_info=True,
        )
        await emit_task_event_fn(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="DIAGNOSTICS_SERVICE_UNAVAILABLE",
            payload={
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": reason_diagnostics_service_unavailable,
                "error_code": err_diagnostics_service_unavailable,
            },
        )
        await send_infra_alert_fn(
            code=INFRA_DIAGNOSTICS_SERVICE_UNAVAILABLE,
            alert_type="Diagnostics Service Unavailable",
            message=f"Diagnostics задача завершилась ошибкой zone_service: {exc}",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=type(exc).__name__,
            details={"payload": payload, "error": str(exc)},
        )
        return _diagnostics_failed_result(
            decision,
            error_code=err_diagnostics_service_unavailable,
            reason_code=reason_diagnostics_service_unavailable,
        )


__all__ = ["execute_diagnostics"]
