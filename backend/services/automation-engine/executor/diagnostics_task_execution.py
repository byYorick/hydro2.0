"""Helpers for diagnostics task execution routing."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Set

from domain.models.decision_models import DecisionOutcome

DispatchDiagnosticsWorkflowFn = Callable[..., Awaitable[Dict[str, Any]]]
ExecuteDiagnosticsFn = Callable[..., Awaitable[Dict[str, Any]]]
BuildInvalidPayloadResultFn = Callable[..., Dict[str, Any]]
PostWorkflowDiagnosticsFn = Callable[..., Awaitable[Dict[str, Any]]]


def _normalize_workflow_phase(raw: Any) -> str:
    return str(raw or "").strip().lower()


async def _run_post_workflow_diagnostics_if_needed(
    *,
    result: Dict[str, Any],
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    post_workflow_diagnostics_fn: Optional[PostWorkflowDiagnosticsFn],
    post_workflow_phases: Set[str],
) -> Dict[str, Any]:
    if post_workflow_diagnostics_fn is None:
        return result
    if not bool(result.get("success")):
        return result

    workflow_phase = _normalize_workflow_phase(result.get("workflow_phase") or payload.get("workflow_phase"))
    if workflow_phase not in post_workflow_phases:
        return result

    post_result = await post_workflow_diagnostics_fn(
        zone_id,
        payload,
        context=context,
        decision=decision,
    )
    merged = dict(result)
    merged["post_correction_cycle_triggered"] = True
    merged["post_correction_cycle_success"] = bool(post_result.get("success"))
    merged["post_correction_cycle_mode"] = post_result.get("mode")
    return merged


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
    post_workflow_diagnostics_fn: Optional[PostWorkflowDiagnosticsFn] = None,
    post_workflow_phases: Optional[Set[str]] = None,
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
    normalized_post_workflow_phases = {_normalize_workflow_phase(item) for item in (post_workflow_phases or set())}

    if not requires_explicit_workflow and workflow in cycle_start_workflows:
        routed_result = await dispatch_diagnostics_workflow_fn(
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
            workflow=workflow,
            topology=topology,
        )
        return await _run_post_workflow_diagnostics_if_needed(
            result=routed_result,
            zone_id=zone_id,
            payload=payload,
            context=context,
            decision=decision,
            post_workflow_diagnostics_fn=post_workflow_diagnostics_fn,
            post_workflow_phases=normalized_post_workflow_phases,
        )
    if not requires_explicit_workflow:
        return await execute_diagnostics_fn(
            zone_id,
            payload,
            context=context,
            decision=decision,
        )

    routed_result = await dispatch_diagnostics_workflow_fn(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        workflow=workflow,
        topology=topology,
    )
    return await _run_post_workflow_diagnostics_if_needed(
        result=routed_result,
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        post_workflow_diagnostics_fn=post_workflow_diagnostics_fn,
        post_workflow_phases=normalized_post_workflow_phases,
    )


__all__ = ["execute_diagnostics_task"]
