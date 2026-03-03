"""Small delegates for medium-sized SchedulerTaskExecutor wrappers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from executor.command_publish_batch import publish_batch as policy_publish_batch
from executor.device_task_core import execute_device_task_core as policy_execute_device_task_core
from executor.workflow_phase_update import update_zone_workflow_phase as policy_update_zone_workflow_phase
from executor.executor_constants import (
    ERR_COMMAND_EFFECT_NOT_CONFIRMED,
    ERR_COMMAND_SEND_FAILED,
    ERR_COMMAND_TRACKER_UNAVAILABLE,
    ERR_MAPPING_NOT_FOUND,
    ERR_NO_ONLINE_NODES,
    TASK_EXECUTE_CLOSED_LOOP_ENFORCE,
    TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC,
)
from domain.models.decision_models import DecisionOutcome


async def update_zone_workflow_phase(
    *,
    executor: Any,
    zone_id: int,
    workflow_phase: str,
    context: Dict[str, Any],
    workflow_phase_event_type: str,
    log_warning: Callable[..., Any],
    workflow_stage: Optional[str] = None,
    reason_code: Optional[str] = None,
    source: str = "scheduler_task_executor",
) -> str:
    return await policy_update_zone_workflow_phase(
        zone_id=zone_id,
        workflow_phase=workflow_phase,
        context=context,
        workflow_stage=workflow_stage,
        reason_code=reason_code,
        source=source,
        zone_service=executor.zone_service,
        workflow_phase_event_type=workflow_phase_event_type,
        normalize_workflow_phase_fn=executor._normalize_workflow_phase,
        normalize_workflow_stage_fn=executor._normalize_workflow_stage,
        validate_phase_transition_fn=executor._validate_phase_transition,
        create_zone_event_safe_fn=executor._create_zone_event_safe,
        log_warning=log_warning,
    )


async def publish_batch(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    nodes: Sequence[Dict[str, Any]],
    cmd: str,
    context: Dict[str, Any],
    decision: DecisionOutcome,
    terminal_status_to_error_code_fn: Callable[[str], str],
    emit_task_event_fn: Callable[..., Awaitable[None]],
    params: Optional[Dict[str, Any]] = None,
    accepted_terminal_statuses: Optional[Sequence[str]] = None,
    dedupe_bypass: bool = False,
) -> Dict[str, Any]:
    return await policy_publish_batch(
        zone_id=zone_id,
        task_type=task_type,
        nodes=nodes,
        cmd=cmd,
        params=params,
        context=context,
        decision=decision,
        accepted_terminal_statuses=accepted_terminal_statuses,
        dedupe_bypass=dedupe_bypass,
        command_gateway=getattr(executor, "command_gateway", None),
        command_bus=executor.command_bus,
        task_execute_closed_loop_enforce=TASK_EXECUTE_CLOSED_LOOP_ENFORCE,
        task_execute_closed_loop_timeout_sec=TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC,
        err_command_send_failed=ERR_COMMAND_SEND_FAILED,
        err_command_tracker_unavailable=ERR_COMMAND_TRACKER_UNAVAILABLE,
        err_command_effect_not_confirmed=ERR_COMMAND_EFFECT_NOT_CONFIRMED,
        terminal_status_to_error_code_fn=terminal_status_to_error_code_fn,
        emit_task_event_fn=emit_task_event_fn,
    )


async def execute_device_task_core(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    mapping: Any,
    context: Dict[str, Any],
    decision: DecisionOutcome,
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
) -> Dict[str, Any]:
    return await policy_execute_device_task_core(
        zone_id=zone_id,
        payload=payload,
        mapping=mapping,
        context=context,
        decision=decision,
        get_zone_nodes_fn=executor._get_zone_nodes,
        resolve_command_name_fn=executor._resolve_command_name,
        resolve_command_params_fn=executor._resolve_command_params,
        publish_batch_fn=executor._publish_batch,
        send_infra_alert_fn=send_infra_alert_fn,
        err_mapping_not_found=ERR_MAPPING_NOT_FOUND,
        err_no_online_nodes=ERR_NO_ONLINE_NODES,
    )


def build_two_tank_runtime_payload(
    *,
    payload: Dict[str, Any],
    merge_dict_recursive_fn: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
    diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
    diagnostics_execution = (
        diagnostics_targets.get("execution")
        if isinstance(diagnostics_targets.get("execution"), dict)
        else {}
    )
    merged_execution = merge_dict_recursive_fn(diagnostics_execution, execution)
    topology = str(merged_execution.get("topology") or "").strip().lower()
    if topology != "two_tank_drip_substrate_trays":
        return None
    runtime_payload = dict(payload)
    runtime_config = dict(config)
    runtime_config["execution"] = merged_execution
    runtime_payload["config"] = runtime_config
    return runtime_payload


__all__ = [
    "build_two_tank_runtime_payload",
    "execute_device_task_core",
    "publish_batch",
    "update_zone_workflow_phase",
]
