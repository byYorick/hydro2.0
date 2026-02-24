"""Helpers for two-tank enqueue failure compensation flow."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Sequence

from domain.models.decision_models import DecisionOutcome

DispatchCommandPlanFn = Callable[..., Awaitable[Dict[str, Any]]]
MergeSensorModeDeactivateFn = Callable[..., Awaitable[Dict[str, Any]]]
LogSafetyGuardFn = Callable[..., Any]


async def compensate_two_tank_start_enqueue_failure(
    *,
    zone_id: int,
    context: Dict[str, Any],
    workflow: str,
    phase: str,
    stop_command_plan: Sequence[Dict[str, Any]],
    reason_code_cycle_refill_command_failed: str,
    dispatch_two_tank_command_plan_fn: DispatchCommandPlanFn,
    merge_with_sensor_mode_deactivate_fn: MergeSensorModeDeactivateFn,
    log_two_tank_safety_guard_fn: LogSafetyGuardFn,
) -> Dict[str, Any]:
    stop_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=stop_command_plan,
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_code_cycle_refill_command_failed,
            reason=f"Compensating stop для {phase} после ошибки enqueue",
        ),
    )
    stop_result = await merge_with_sensor_mode_deactivate_fn(
        zone_id=zone_id,
        context=context,
        stop_result=stop_result,
        reason_code=reason_code_cycle_refill_command_failed,
    )
    log_two_tank_safety_guard_fn(
        zone_id=zone_id,
        context=context,
        phase=f"{phase}_enqueue_failed_compensating_stop",
        stop_result=stop_result,
        level=logging.INFO if stop_result.get("success") else logging.WARNING,
    )
    return stop_result


__all__ = ["compensate_two_tank_start_enqueue_failure"]
