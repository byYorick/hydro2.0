"""Helpers for scheduler task execution finalization."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from domain.models.decision_models import DecisionOutcome

EnsureExtendedOutcomeFn = Callable[..., Dict[str, Any]]
WorkflowStateSyncFn = Callable[..., Awaitable[Any]]
EmitTaskEventFn = Callable[..., Awaitable[None]]
CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
BuildTaskFinishedPayloadFn = Callable[[Dict[str, Any]], Dict[str, Any]]
BuildExecutionFinishedZoneEventPayloadFn = Callable[..., Dict[str, Any]]
LogExecutionFinishedFn = Callable[..., None]


async def finalize_execution(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    result: Dict[str, Any],
    execute_started_at: datetime,
    auto_logic_extended_outcome_v1: bool,
    ensure_extended_outcome_fn: EnsureExtendedOutcomeFn,
    workflow_state_sync_fn: WorkflowStateSyncFn,
    emit_task_event_fn: EmitTaskEventFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    build_task_finished_payload_fn: BuildTaskFinishedPayloadFn,
    build_execution_finished_zone_event_payload_fn: BuildExecutionFinishedZoneEventPayloadFn,
    log_execution_finished_fn: LogExecutionFinishedFn,
) -> Dict[str, Any]:
    finalized_result = result
    if auto_logic_extended_outcome_v1:
        finalized_result = ensure_extended_outcome_fn(
            task_type=task_type,
            payload=payload,
            decision=decision,
            result=finalized_result,
        )

    await workflow_state_sync_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        result=finalized_result,
        context=context,
    )

    await emit_task_event_fn(
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type="TASK_FINISHED",
        payload=build_task_finished_payload_fn(finalized_result),
    )
    await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="SCHEDULE_TASK_EXECUTION_FINISHED",
        payload=build_execution_finished_zone_event_payload_fn(
            task_type=task_type,
            result=finalized_result,
            context=context,
        ),
        task_type=task_type,
        context=context,
    )

    log_execution_finished_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        context=context,
        result=finalized_result,
        decision=decision,
        execute_started_at=execute_started_at,
    )
    return finalized_result


__all__ = ["finalize_execution"]
