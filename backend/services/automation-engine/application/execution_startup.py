"""Helpers for scheduler task execution startup events."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

EmitTaskEventFn = Callable[..., Awaitable[None]]
CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
BuildTaskReceivedPayloadFn = Callable[..., Dict[str, Any]]
BuildExecutionStartedZoneEventPayloadFn = Callable[..., Dict[str, Any]]


async def emit_execution_started_events(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    emit_task_event_fn: EmitTaskEventFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    build_task_received_payload_fn: BuildTaskReceivedPayloadFn,
    build_execution_started_zone_event_payload_fn: BuildExecutionStartedZoneEventPayloadFn,
) -> None:
    await emit_task_event_fn(
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type="TASK_RECEIVED",
        payload=build_task_received_payload_fn(payload=payload, context=context),
    )
    await emit_task_event_fn(
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type="TASK_STARTED",
        payload={"payload": payload},
    )
    await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="SCHEDULE_TASK_EXECUTION_STARTED",
        payload=build_execution_started_zone_event_payload_fn(
            task_type=task_type,
            payload=payload,
            context=context,
        ),
        task_type=task_type,
        context=context,
    )


__all__ = ["emit_execution_started_events"]
