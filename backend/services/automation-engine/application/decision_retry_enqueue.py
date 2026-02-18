"""Helpers for scheduler decision retry enqueue flow."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from domain.models.decision_models import DecisionOutcome

SafeIntFn = Callable[[Any], Optional[int]]
ExtractNextDueAtFn = Callable[[DecisionOutcome, Dict[str, Any]], Optional[str]]
BuildCorrelationIdFn = Callable[..., str]
EnqueueTaskFn = Callable[..., Awaitable[Dict[str, Any]]]
LogWarningFn = Callable[..., Any]


async def enqueue_decision_retry(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    decision: DecisionOutcome,
    context: Dict[str, Any],
    safe_int_fn: SafeIntFn,
    extract_next_due_at_fn: ExtractNextDueAtFn,
    build_correlation_id_fn: BuildCorrelationIdFn,
    enqueue_task_fn: EnqueueTaskFn,
    log_warning: LogWarningFn,
) -> Optional[Dict[str, Any]]:
    if decision.decision != "retry":
        return None
    if not isinstance(decision.details, dict):
        return None

    next_due_at = extract_next_due_at_fn(decision, {})
    if not next_due_at:
        return None

    retry_attempt = safe_int_fn(decision.details.get("retry_attempt"))
    retry_payload = dict(payload)
    if retry_attempt is not None:
        retry_payload["retry_attempt"] = max(0, retry_attempt)
    retry_payload["decision_retry_reason_code"] = decision.reason_code
    context_correlation_id = str(context.get("correlation_id") or "").strip() or None
    root_parent_correlation_id = str(retry_payload.get("parent_correlation_id") or "").strip() or None
    parent_correlation_id = root_parent_correlation_id or context_correlation_id
    if parent_correlation_id:
        retry_payload["parent_correlation_id"] = parent_correlation_id
    if context_correlation_id and context_correlation_id != parent_correlation_id:
        retry_payload["previous_correlation_id"] = context_correlation_id
    retry_correlation_id = build_correlation_id_fn(
        zone_id=zone_id,
        task_type=task_type,
        parent_correlation_id=parent_correlation_id,
        retry_attempt=retry_attempt,
    )

    try:
        return await enqueue_task_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=retry_payload,
            scheduled_for=next_due_at,
            correlation_id=retry_correlation_id,
            source="automation-engine:decision-retry",
        )
    except ValueError as exc:
        log_warning(
            "Не удалось поставить retry-задачу scheduler: zone=%s task=%s reason=%s error=%s",
            zone_id,
            task_type,
            decision.reason_code,
            exc,
        )
        return {
            "status": "failed",
            "error": str(exc),
            "scheduled_for": next_due_at,
        }


__all__ = ["enqueue_decision_retry"]
