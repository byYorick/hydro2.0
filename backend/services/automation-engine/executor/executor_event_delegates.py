"""Event-related delegates for SchedulerTaskExecutor wrappers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from executor.task_events import build_task_event_payload as policy_build_task_event_payload
from domain.models.decision_models import DecisionOutcome


async def emit_task_event(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    context: Dict[str, Any],
    event_type: str,
    event_id_factory: Callable[[], str],
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    event_payload = policy_build_task_event_payload(
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type=event_type,
        payload=payload,
        event_id_factory=event_id_factory,
    )
    await executor._create_zone_event_safe(
        zone_id=zone_id,
        event_type=event_type,
        payload=event_payload,
        task_type=task_type,
        context=context,
    )


async def merge_with_sensor_mode_deactivate(
    *,
    executor: Any,
    zone_id: int,
    context: Dict[str, Any],
    stop_result: Dict[str, Any],
    reason_code: str,
) -> Dict[str, Any]:
    if not stop_result.get("success"):
        return stop_result
    deactivate_result = await executor._dispatch_sensor_mode_command_for_nodes(
        zone_id=zone_id,
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_code,
            reason="Деактивация sensor mode для pH/EC после stop",
        ),
        activate=False,
        reason_code=reason_code,
    )
    return executor._merge_command_dispatch_results(stop_result, deactivate_result)


__all__ = ["emit_task_event", "merge_with_sensor_mode_deactivate"]
