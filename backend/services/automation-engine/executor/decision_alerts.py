"""Helpers for automation decision retry/fail infra alerts."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from domain.models.decision_models import DecisionOutcome
from services.resilience_contract import build_decision_alert_code

SendInfraAlertFn = Callable[..., Awaitable[Any]]

_ALERT_REASON_CODES = {"low_water", "nodes_unavailable"}


def should_emit_decision_alert(reason_code: str) -> bool:
    return str(reason_code or "").strip() in _ALERT_REASON_CODES


async def emit_decision_alert(
    *,
    zone_id: int,
    task_type: str,
    decision: DecisionOutcome,
    result: Dict[str, Any],
    send_infra_alert_fn: SendInfraAlertFn,
) -> None:
    await send_infra_alert_fn(
        code=build_decision_alert_code(task_type, decision.reason_code),
        alert_type="Automation Decision Retry",
        message=(
            f"Задача {task_type} для зоны {zone_id} отложена: "
            f"{decision.reason_code} ({decision.decision})"
        ),
        severity="warning" if decision.decision == "retry" else "error",
        zone_id=zone_id,
        service="automation-engine",
        component="scheduler_task_executor",
        error_type=decision.reason_code,
        details={
            "task_type": task_type,
            "decision": decision.decision,
            "reason_code": decision.reason_code,
            "next_due_at": result.get("next_due_at"),
            "retry_attempt": result.get("retry_attempt"),
            "retry_max_attempts": result.get("retry_max_attempts"),
        },
    )


__all__ = ["emit_decision_alert", "should_emit_decision_alert"]
