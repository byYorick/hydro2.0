"""Async branch dispatch helpers for scheduler task execution."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from domain.models.decision_models import DecisionOutcome

ExecuteDiagnosticsFn = Callable[..., Awaitable[Dict[str, Any]]]
UpdateWorkflowPhaseFn = Callable[..., Awaitable[str]]
ExecuteDeviceTaskFn = Callable[..., Awaitable[Dict[str, Any]]]
TryRecoveryFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]


async def execute_action_required_branch(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    workflow_phase_irrigating: str,
    execute_diagnostics_fn: ExecuteDiagnosticsFn,
    update_zone_workflow_phase_fn: UpdateWorkflowPhaseFn,
    execute_device_task_fn: ExecuteDeviceTaskFn,
    try_start_recovery_fn: TryRecoveryFn,
) -> Dict[str, Any]:
    if task_type == "diagnostics":
        return await execute_diagnostics_fn(
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
        )

    if task_type == "irrigation" and decision.action_required and decision.decision == "run":
        await update_zone_workflow_phase_fn(
            zone_id=zone_id,
            workflow_phase=workflow_phase_irrigating,
            workflow_stage=None,
            reason_code=decision.reason_code,
            context=context,
        )
    result = await execute_device_task_fn(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        task_type=task_type,
    )
    if task_type == "irrigation":
        recovery_result = await try_start_recovery_fn(
            zone_id=zone_id,
            payload=payload,
            context=context,
            result=result,
        )
        if recovery_result is not None:
            return recovery_result
    return result


__all__ = ["execute_action_required_branch"]
