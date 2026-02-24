"""Delegates for verbose SchedulerTaskExecutor method wiring."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from executor.executor_constants import (
    ERR_COMMAND_BUSY,
    ERR_COMMAND_EFFECT_NOT_CONFIRMED,
    ERR_COMMAND_ERROR,
    ERR_COMMAND_INVALID,
    ERR_COMMAND_NO_EFFECT,
    ERR_COMMAND_TIMEOUT,
    ERR_COMMAND_TRACKER_UNAVAILABLE,
    ERR_TWO_TANK_COMMAND_FAILED,
    ERR_TWO_TANK_ENQUEUE_FAILED,
    REASON_CLEAN_FILL_STARTED,
    REASON_CYCLE_REFILL_COMMAND_FAILED,
    REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
    REASON_IRRIGATION_RECOVERY_FAILED,
    REASON_IRRIGATION_RECOVERY_STARTED,
    REASON_ONLINE_CORRECTION_FAILED,
    REASON_PREPARE_RECIRCULATION_STARTED,
    REASON_SOLUTION_FILL_STARTED,
    REASON_TANK_TO_TANK_CORRECTION_STARTED,
)
from executor.two_tank_phase_starters import (
    start_two_tank_clean_fill as policy_start_two_tank_clean_fill,
    start_two_tank_irrigation_recovery as policy_start_two_tank_irrigation_recovery,
    start_two_tank_prepare_recirculation as policy_start_two_tank_prepare_recirculation,
    start_two_tank_solution_fill as policy_start_two_tank_solution_fill,
)
from executor.two_tank_recovery_transition import (
    try_start_two_tank_irrigation_recovery_from_irrigation_failure as policy_try_start_two_tank_irrigation_recovery_from_irrigation_failure,
)
from executor.workflow_phase_sync_core import (
    sync_zone_workflow_phase_core as policy_sync_zone_workflow_phase_core,
)
from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
)


async def sync_zone_workflow_phase_core(
    *,
    executor: Any,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    context: Dict[str, Any],
    logger_obj: Any,
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
) -> None:
    executor._workflow_state_persist_failed = await policy_sync_zone_workflow_phase_core(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        result=result,
        context=context,
        logger_obj=logger_obj,
        workflow_state_persist_enabled=executor.workflow_state_persist_enabled,
        workflow_state_persist_failed=executor._workflow_state_persist_failed,
        derive_workflow_phase_fn=executor._derive_workflow_phase,
        extract_workflow_hint_fn=executor._extract_workflow_hint,
        normalize_workflow_phase_fn=executor._normalize_workflow_phase,
        resolve_workflow_stage_for_state_sync_fn=executor._resolve_workflow_stage_for_state_sync,
        build_workflow_state_payload_fn=executor._build_workflow_state_payload,
        workflow_state_store_set_fn=executor.workflow_state_store.set,
        zone_service=executor.zone_service,
        send_infra_alert_fn=send_infra_alert_fn,
    )


async def try_start_two_tank_irrigation_recovery_from_irrigation_failure(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    return await policy_try_start_two_tank_irrigation_recovery_from_irrigation_failure(
        zone_id=zone_id,
        payload=payload,
        context=context,
        result=result,
        allowed_error_codes=(
            ERR_COMMAND_TIMEOUT,
            ERR_COMMAND_ERROR,
            ERR_COMMAND_INVALID,
            ERR_COMMAND_BUSY,
            ERR_COMMAND_NO_EFFECT,
            ERR_COMMAND_EFFECT_NOT_CONFIRMED,
            ERR_COMMAND_TRACKER_UNAVAILABLE,
        ),
        reason_online_correction_failed=REASON_ONLINE_CORRECTION_FAILED,
        reason_tank_to_tank_correction_started=REASON_TANK_TO_TANK_CORRECTION_STARTED,
        build_two_tank_runtime_payload_fn=executor._build_two_tank_runtime_payload,
        resolve_two_tank_runtime_config_fn=executor._resolve_two_tank_runtime_config,
        emit_task_event_fn=executor._emit_task_event,
        start_two_tank_irrigation_recovery_fn=executor._start_two_tank_irrigation_recovery,
    )


async def start_two_tank_clean_fill(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    cycle: int,
) -> Dict[str, Any]:
    return await policy_start_two_tank_clean_fill(
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        cycle=cycle,
        dispatch_two_tank_command_plan_fn=executor._dispatch_two_tank_command_plan,
        enqueue_two_tank_check_fn=executor._enqueue_two_tank_check,
        compensate_two_tank_start_enqueue_failure_fn=executor._compensate_two_tank_start_enqueue_failure,
        emit_task_event_fn=executor._emit_task_event,
        two_tank_safety_guards_enabled_fn=executor._two_tank_safety_guards_enabled,
        reason_clean_fill_started=REASON_CLEAN_FILL_STARTED,
        reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
        reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
        err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
    )


async def start_two_tank_solution_fill(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return await policy_start_two_tank_solution_fill(
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        dispatch_two_tank_command_plan_fn=executor._dispatch_two_tank_command_plan,
        dispatch_sensor_mode_command_for_nodes_fn=executor._dispatch_sensor_mode_command_for_nodes,
        merge_command_dispatch_results_fn=executor._merge_command_dispatch_results,
        update_zone_workflow_phase_fn=executor._update_zone_workflow_phase,
        enqueue_two_tank_check_fn=executor._enqueue_two_tank_check,
        compensate_two_tank_start_enqueue_failure_fn=executor._compensate_two_tank_start_enqueue_failure,
        emit_task_event_fn=executor._emit_task_event,
        two_tank_safety_guards_enabled_fn=executor._two_tank_safety_guards_enabled,
        workflow_phase_tank_filling=WORKFLOW_PHASE_TANK_FILLING,
        reason_solution_fill_started=REASON_SOLUTION_FILL_STARTED,
        reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
        reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
        err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
    )


async def start_two_tank_prepare_recirculation(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return await policy_start_two_tank_prepare_recirculation(
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        dispatch_two_tank_command_plan_fn=executor._dispatch_two_tank_command_plan,
        dispatch_sensor_mode_command_for_nodes_fn=executor._dispatch_sensor_mode_command_for_nodes,
        merge_command_dispatch_results_fn=executor._merge_command_dispatch_results,
        update_zone_workflow_phase_fn=executor._update_zone_workflow_phase,
        enqueue_two_tank_check_fn=executor._enqueue_two_tank_check,
        compensate_two_tank_start_enqueue_failure_fn=executor._compensate_two_tank_start_enqueue_failure,
        two_tank_safety_guards_enabled_fn=executor._two_tank_safety_guards_enabled,
        workflow_phase_tank_recirc=WORKFLOW_PHASE_TANK_RECIRC,
        reason_prepare_recirculation_started=REASON_PREPARE_RECIRCULATION_STARTED,
        reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
        reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
        err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
    )


async def start_two_tank_irrigation_recovery(
    *,
    executor: Any,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    return await policy_start_two_tank_irrigation_recovery(
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        attempt=attempt,
        dispatch_two_tank_command_plan_fn=executor._dispatch_two_tank_command_plan,
        update_zone_workflow_phase_fn=executor._update_zone_workflow_phase,
        enqueue_two_tank_check_fn=executor._enqueue_two_tank_check,
        compensate_two_tank_start_enqueue_failure_fn=executor._compensate_two_tank_start_enqueue_failure,
        two_tank_safety_guards_enabled_fn=executor._two_tank_safety_guards_enabled,
        workflow_phase_irrig_recirc=WORKFLOW_PHASE_IRRIG_RECIRC,
        reason_irrigation_recovery_started=REASON_IRRIGATION_RECOVERY_STARTED,
        reason_irrigation_recovery_failed=REASON_IRRIGATION_RECOVERY_FAILED,
        reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
        err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
        err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
    )


__all__ = [
    "sync_zone_workflow_phase_core",
    "try_start_two_tank_irrigation_recovery_from_irrigation_failure",
    "start_two_tank_clean_fill",
    "start_two_tank_solution_fill",
    "start_two_tank_prepare_recirculation",
    "start_two_tank_irrigation_recovery",
]
