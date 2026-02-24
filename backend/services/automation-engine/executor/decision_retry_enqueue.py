"""Helpers for scheduler decision retry enqueue flow."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from prometheus_client import Counter

from domain.models.decision_models import DecisionOutcome
from services.resilience_contract import (
    SCHEDULER_RETRY_REASON_PAYLOAD_KEY,
    SCHEDULER_RETRY_SOURCE,
    SCHEDULER_RETRY_STATUS_FAILED,
)

SafeIntFn = Callable[[Any], Optional[int]]
ExtractNextDueAtFn = Callable[[DecisionOutcome, Dict[str, Any]], Optional[str]]
BuildCorrelationIdFn = Callable[..., str]
EnqueueTaskFn = Callable[..., Awaitable[Dict[str, Any]]]
LogWarningFn = Callable[..., Any]

DECISION_RETRY_ENQUEUE_TOTAL = Counter(
    "decision_retry_enqueue_total",
    "Decision retry enqueue outcomes",
    ["outcome"],
)


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
        DECISION_RETRY_ENQUEUE_TOTAL.labels(outcome="not_retry").inc()
        return None
    if not isinstance(decision.details, dict):
        DECISION_RETRY_ENQUEUE_TOTAL.labels(outcome="missing_details").inc()
        return None

    next_due_at = extract_next_due_at_fn(decision, {})
    if not next_due_at:
        DECISION_RETRY_ENQUEUE_TOTAL.labels(outcome="missing_next_due_at").inc()
        return None

    retry_attempt = safe_int_fn(decision.details.get("retry_attempt"))
    retry_payload = dict(payload)
    if retry_attempt is not None:
        retry_payload["retry_attempt"] = max(0, retry_attempt)
    retry_payload[SCHEDULER_RETRY_REASON_PAYLOAD_KEY] = decision.reason_code
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
        result = await enqueue_task_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=retry_payload,
            scheduled_for=next_due_at,
            correlation_id=retry_correlation_id,
            source=SCHEDULER_RETRY_SOURCE,
        )
        DECISION_RETRY_ENQUEUE_TOTAL.labels(outcome="queued").inc()
        return result
    except ValueError as exc:
        DECISION_RETRY_ENQUEUE_TOTAL.labels(outcome="enqueue_failed").inc()
        log_warning(
            "Не удалось поставить retry-задачу scheduler: zone=%s task=%s reason=%s error=%s",
            zone_id,
            task_type,
            decision.reason_code,
            exc,
        )
        return {
            "status": SCHEDULER_RETRY_STATUS_FAILED,
            "error": str(exc),
            "scheduled_for": next_due_at,
        }


__all__ = ["enqueue_decision_retry"]
