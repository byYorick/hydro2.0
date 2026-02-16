"""Helpers for diagnostics task execution routing."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from domain.models.decision_models import DecisionOutcome

DispatchDiagnosticsWorkflowFn = Callable[..., Awaitable[Dict[str, Any]]]
ExecuteDiagnosticsFn = Callable[..., Awaitable[Dict[str, Any]]]
BuildInvalidPayloadResultFn = Callable[..., Dict[str, Any]]


async def execute_diagnostics_task(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    workflow_validator: Any,
    dispatch_diagnostics_workflow_fn: DispatchDiagnosticsWorkflowFn,
    execute_diagnostics_fn: ExecuteDiagnosticsFn,
    build_invalid_payload_result_fn: BuildInvalidPayloadResultFn,
    cycle_start_workflows: set[str],
    err_invalid_payload_contract_version: str,
) -> Dict[str, Any]:
    validation = workflow_validator.validate_diagnostics(
        zone_id=zone_id,
        payload=payload,
        task_type="diagnostics",
        task_id=str(context.get("task_id") or "") or None,
        correlation_id=str(context.get("correlation_id") or "") or None,
    )
    if not validation.valid:
        return validation.error_result or build_invalid_payload_result_fn(
            reason_code=err_invalid_payload_contract_version,
            reason="Diagnostics payload не прошел валидацию",
            payload_contract_version=validation.payload_contract_version,
        )

    workflow = validation.workflow
    topology = validation.topology
    requires_explicit_workflow = validation.requires_explicit_workflow

    if not requires_explicit_workflow and workflow in cycle_start_workflows:
        return await dispatch_diagnostics_workflow_fn(
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
            workflow=workflow,
            topology=topology,
        )
    if not requires_explicit_workflow:
        return await execute_diagnostics_fn(
            zone_id,
            payload,
            context=context,
            decision=decision,
        )

    return await dispatch_diagnostics_workflow_fn(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        workflow=workflow,
        topology=topology,
    )


__all__ = ["execute_diagnostics_task"]
