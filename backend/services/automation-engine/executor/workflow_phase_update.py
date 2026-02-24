"""Helpers for workflow phase update with fallback event persistence."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

NormalizeWorkflowPhaseFn = Callable[[Any], str]
NormalizeWorkflowStageFn = Callable[[Any], str]
CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
LogWarningFn = Callable[..., Any]


async def update_zone_workflow_phase(
    *,
    zone_id: int,
    workflow_phase: str,
    context: Dict[str, Any],
    workflow_stage: Optional[str],
    reason_code: Optional[str],
    source: str,
    zone_service: Any,
    workflow_phase_event_type: str,
    normalize_workflow_phase_fn: NormalizeWorkflowPhaseFn,
    normalize_workflow_stage_fn: NormalizeWorkflowStageFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    log_warning: LogWarningFn,
) -> str:
    normalized_phase = normalize_workflow_phase_fn(workflow_phase)
    normalized_stage = normalize_workflow_stage_fn(workflow_stage)
    if zone_service is not None and hasattr(zone_service, "update_workflow_phase"):
        try:
            await zone_service.update_workflow_phase(
                zone_id=zone_id,
                workflow_phase=normalized_phase,
                workflow_stage=normalized_stage or None,
                source=source,
                reason_code=reason_code,
            )
            return normalized_phase
        except Exception as exc:
            log_warning(
                "Zone %s: failed to sync workflow_phase to zone_service: %s",
                zone_id,
                exc,
                exc_info=True,
            )

    await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type=workflow_phase_event_type,
        payload={
            "workflow_phase": normalized_phase,
            "workflow_stage": normalized_stage or None,
            "source": source,
            "reason_code": reason_code,
            "task_id": context.get("task_id") or None,
            "correlation_id": context.get("correlation_id") or None,
        },
        task_type="diagnostics",
        context=context,
    )
    return normalized_phase


__all__ = ["update_zone_workflow_phase"]
