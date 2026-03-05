"""High-level orchestration helper for SchedulerTaskExecutor.execute()."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from executor.decision_alerts import (
    emit_decision_alert as policy_emit_decision_alert,
    should_emit_decision_alert as policy_should_emit_decision_alert,
)
from executor.execution_branches import execute_action_required_branch as policy_execute_action_required_branch
from executor.execution_decision import run_decision_phase as policy_run_decision_phase
from executor.execution_finalize import finalize_execution as policy_finalize_execution
from executor.execution_flow_policy import (
    apply_decision_defaults as policy_apply_decision_defaults,
    build_decision_payload as policy_build_decision_payload,
    build_execution_finished_zone_event_payload as policy_build_execution_finished_zone_event_payload,
    build_execution_started_zone_event_payload as policy_build_execution_started_zone_event_payload,
    build_no_action_result as policy_build_no_action_result,
    build_task_finished_payload as policy_build_task_finished_payload,
    build_task_received_payload as policy_build_task_received_payload,
)
from executor.execution_logging import (
    log_execution_finished as policy_log_execution_finished,
    log_execution_started as policy_log_execution_started,
)
from executor.execution_prepare import prepare_execution_inputs as policy_prepare_execution_inputs
from executor.execution_startup import emit_execution_started_events as policy_emit_execution_started_events
from executor.no_action_branch import execute_no_action_branch as policy_execute_no_action_branch
from executor.task_context import build_task_context as policy_build_task_context
from domain.models.decision_models import DecisionOutcome

PrepareExecutionInputsFn = Callable[..., tuple[str, Dict[str, Any], Any]]
BuildTaskContextFn = Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
LogExecutionStartedFn = Callable[..., None]
EmitExecutionStartedEventsFn = Callable[..., Awaitable[None]]
RunDecisionPhaseFn = Callable[..., Awaitable[DecisionOutcome]]
ExecuteNoActionBranchFn = Callable[..., Awaitable[Dict[str, Any]]]
ExecuteActionRequiredBranchFn = Callable[..., Awaitable[Dict[str, Any]]]
ApplyDecisionDefaultsFn = Callable[..., Dict[str, Any]]
FinalizeExecutionFn = Callable[..., Awaitable[Dict[str, Any]]]


def _extract_workflow_hint(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    workflow = (
        payload.get("workflow")
        or payload.get("diagnostics_workflow")
        or execution.get("workflow")
        or ""
    )
    return str(workflow).strip().lower()


async def _maybe_reset_correction_anomaly_state_for_cycle_start(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    logger_obj: Any,
) -> None:
    normalized_task_type = str(task_type or "").strip().lower()
    if normalized_task_type != "diagnostics":
        return

    workflow = _extract_workflow_hint(payload)
    if workflow not in {"cycle_start", "startup"}:
        return

    zone_service = getattr(executor, "zone_service", None)
    reset_fn = getattr(zone_service, "reset_zone_correction_anomaly_state", None)
    if not callable(reset_fn):
        return

    try:
        reset_result = reset_fn(zone_id)
        if inspect.isawaitable(reset_result):
            reset_result = await reset_result
        if isinstance(reset_result, dict) and bool(reset_result.get("changed")):
            logger_obj.info(
                "Zone %s: reset correction anomaly state before diagnostics workflow=%s",
                zone_id,
                workflow,
                extra={"zone_id": zone_id, "workflow": workflow, "reset_result": reset_result},
            )
    except Exception:
        logger_obj.warning(
            "Zone %s: failed to reset correction anomaly state before workflow=%s",
            zone_id,
            workflow,
            exc_info=True,
            extra={"zone_id": zone_id, "workflow": workflow},
        )


async def run_executor_execute_flow(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    task_context: Optional[Dict[str, Any]],
    prepare_execution_inputs_fn: PrepareExecutionInputsFn,
    build_task_context_fn: BuildTaskContextFn,
    log_execution_started_fn: LogExecutionStartedFn,
    emit_execution_started_events_fn: EmitExecutionStartedEventsFn,
    run_decision_phase_fn: RunDecisionPhaseFn,
    execute_no_action_branch_fn: ExecuteNoActionBranchFn,
    execute_action_required_branch_fn: ExecuteActionRequiredBranchFn,
    apply_decision_defaults_fn: ApplyDecisionDefaultsFn,
    finalize_execution_fn: FinalizeExecutionFn,
) -> Dict[str, Any]:
    task_type, payload, mapping = prepare_execution_inputs_fn(task_type=task_type, payload=payload)
    context = build_task_context_fn(task_context)
    execute_started_at = datetime.now(timezone.utc).replace(tzinfo=None)

    log_execution_started_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        context=context,
    )

    await emit_execution_started_events_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        context=context,
    )

    decision = await run_decision_phase_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        context=context,
    )

    if not decision.action_required:
        result = await execute_no_action_branch_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            context=context,
            decision=decision,
        )
    else:
        result = await execute_action_required_branch_fn(
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            context=context,
            decision=decision,
            mapping=mapping,
        )

    result = apply_decision_defaults_fn(result=result, decision=decision)
    return await finalize_execution_fn(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        context=context,
        decision=decision,
        result=result,
        execute_started_at=execute_started_at,
    )


async def run_scheduler_executor_execute(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    task_context: Optional[Dict[str, Any]],
    get_task_mapping_fn: Callable[..., Any],
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
    log_structured_fn: Callable[..., Any],
    logger_obj: Any,
    auto_logic_climate_guards_v1: bool,
    auto_logic_extended_outcome_v1: bool,
    workflow_phase_irrigating: str,
) -> Dict[str, Any]:
    await _maybe_reset_correction_anomaly_state_for_cycle_start(
        executor=executor,
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        logger_obj=logger_obj,
    )

    return await run_executor_execute_flow(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        task_context=task_context,
        prepare_execution_inputs_fn=lambda **kwargs: policy_prepare_execution_inputs(
            get_task_mapping_fn=get_task_mapping_fn,
            **kwargs,
        ),
        build_task_context_fn=policy_build_task_context,
        log_execution_started_fn=lambda **kwargs: policy_log_execution_started(
            log_structured_fn=log_structured_fn,
            logger_obj=logger_obj,
            **kwargs,
        ),
        emit_execution_started_events_fn=lambda **kwargs: policy_emit_execution_started_events(
            emit_task_event_fn=executor._emit_task_event,
            create_zone_event_safe_fn=executor._create_zone_event_safe,
            build_task_received_payload_fn=policy_build_task_received_payload,
            build_execution_started_zone_event_payload_fn=policy_build_execution_started_zone_event_payload,
            **kwargs,
        ),
        run_decision_phase_fn=lambda **kwargs: policy_run_decision_phase(
            auto_logic_climate_guards_v1=auto_logic_climate_guards_v1,
            decide_action_fn=lambda task_type_, payload_: executor._decide_action(task_type=task_type_, payload=payload_),
            apply_ventilation_climate_guards_fn=executor._apply_ventilation_climate_guards,
            emit_task_event_fn=executor._emit_task_event,
            build_decision_payload_fn=policy_build_decision_payload,
            **kwargs,
        ),
        execute_no_action_branch_fn=lambda **kwargs: policy_execute_no_action_branch(
            build_no_action_result_fn=lambda task_type_, decision_, retry_enqueue_: policy_build_no_action_result(
                task_type=task_type_,
                decision=decision_,
                retry_enqueue=retry_enqueue_,
            ),
            extract_next_due_at_fn=lambda decision_, result_: executor._extract_next_due_at(
                decision=decision_,
                result=result_,
            ),
            enqueue_decision_retry_fn=executor._enqueue_decision_retry,
            should_emit_decision_alert_fn=policy_should_emit_decision_alert,
            emit_decision_alert_fn=lambda **alert_kwargs: policy_emit_decision_alert(
                send_infra_alert_fn=send_infra_alert_fn,
                **alert_kwargs,
            ),
            **kwargs,
        ),
        execute_action_required_branch_fn=lambda **kwargs: policy_execute_action_required_branch(
            workflow_phase_irrigating=workflow_phase_irrigating,
            execute_diagnostics_fn=executor._execute_diagnostics_task,
            update_zone_workflow_phase_fn=executor._update_zone_workflow_phase,
            execute_device_task_fn=lambda **dispatch_kwargs: executor.command_dispatch.execute_device_task(
                mapping=kwargs["mapping"],
                **dispatch_kwargs,
            ),
            try_start_recovery_fn=executor._try_start_two_tank_irrigation_recovery_from_irrigation_failure,
            zone_id=kwargs["zone_id"],
            task_type=kwargs["task_type"],
            payload=kwargs["payload"],
            context=kwargs["context"],
            decision=kwargs["decision"],
        ),
        apply_decision_defaults_fn=policy_apply_decision_defaults,
        finalize_execution_fn=lambda **kwargs: policy_finalize_execution(
            auto_logic_extended_outcome_v1=auto_logic_extended_outcome_v1,
            ensure_extended_outcome_fn=executor._ensure_extended_outcome,
            workflow_state_sync_fn=executor.workflow_state_sync.sync,
            emit_task_event_fn=executor._emit_task_event,
            create_zone_event_safe_fn=executor._create_zone_event_safe,
            build_task_finished_payload_fn=policy_build_task_finished_payload,
            build_execution_finished_zone_event_payload_fn=policy_build_execution_finished_zone_event_payload,
            log_execution_finished_fn=lambda **log_kwargs: policy_log_execution_finished(
                log_structured_fn=log_structured_fn,
                logger_obj=logger_obj,
                **log_kwargs,
            ),
            **kwargs,
        ),
    )


__all__ = ["run_executor_execute_flow", "run_scheduler_executor_execute"]
