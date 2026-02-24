"""Async helpers for no-action scheduler decision branch."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from domain.models.decision_models import DecisionOutcome

BuildNoActionResultFn = Callable[[str, DecisionOutcome, Optional[Dict[str, Any]]], Dict[str, Any]]
ExtractNextDueAtFn = Callable[[DecisionOutcome, Dict[str, Any]], Optional[str]]
EnqueueDecisionRetryFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]
ShouldEmitDecisionAlertFn = Callable[[str], bool]
EmitDecisionAlertFn = Callable[..., Awaitable[None]]


async def execute_no_action_branch(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    build_no_action_result_fn: BuildNoActionResultFn,
    extract_next_due_at_fn: ExtractNextDueAtFn,
    enqueue_decision_retry_fn: EnqueueDecisionRetryFn,
    should_emit_decision_alert_fn: ShouldEmitDecisionAlertFn,
    emit_decision_alert_fn: EmitDecisionAlertFn,
) -> Dict[str, Any]:
    retry_enqueue: Optional[Dict[str, Any]] = None
    if decision.decision == "retry":
        retry_enqueue = await enqueue_decision_retry_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            decision=decision,
            context=context,
        )

    result = build_no_action_result_fn(task_type, decision, retry_enqueue)
    next_due_at = extract_next_due_at_fn(decision, result)
    if isinstance(next_due_at, str) and next_due_at:
        result["next_due_at"] = next_due_at

    if should_emit_decision_alert_fn(decision.reason_code):
        await emit_decision_alert_fn(
            zone_id=zone_id,
            task_type=task_type,
            decision=decision,
            result=result,
        )
    return result


__all__ = ["execute_no_action_branch"]
