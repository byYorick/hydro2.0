"""Bound two-tank methods for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from domain.policies.two_tank_safety_config import TwoTankSafetyConfig
from domain.workflows.two_tank_deps import TwoTankDeps
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
from executor.executor_event_delegates import (
    merge_with_sensor_mode_deactivate as policy_delegate_merge_with_sensor_mode_deactivate,
)
from executor.two_tank_compensation import (
    compensate_two_tank_start_enqueue_failure as policy_compensate_two_tank_start_enqueue_failure,
)
from executor.two_tank_enqueue import enqueue_two_tank_check as policy_enqueue_two_tank_check
from executor.two_tank_phase_starters_prepare import (
    start_two_tank_prepare_recirculation as policy_start_two_tank_prepare_recirculation,
)
from executor.two_tank_phase_starters_recovery import (
    start_two_tank_irrigation_recovery as policy_start_two_tank_irrigation_recovery,
)
from executor.two_tank_phase_starters_startup import (
    start_two_tank_clean_fill as policy_start_two_tank_clean_fill,
    start_two_tank_solution_fill as policy_start_two_tank_solution_fill,
)
from executor.two_tank_recovery_transition import (
    try_start_two_tank_irrigation_recovery_from_irrigation_failure as policy_try_start_two_tank_irrigation_recovery_from_irrigation_failure,
)
from executor.workflow_phase_policy import (
    WORKFLOW_PHASE_IRRIG_RECIRC,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
)


async def bound_enqueue_two_tank_check(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    workflow: str,
    phase_started_at: datetime,
    phase_timeout_at: datetime,
    poll_interval_sec: int,
    phase_cycle: Optional[int] = None,
) -> Dict[str, Any]:
    return await policy_enqueue_two_tank_check(
        zone_id=zone_id,
        payload=payload,
        workflow=workflow,
        phase_started_at=phase_started_at,
        phase_timeout_at=phase_timeout_at,
        poll_interval_sec=poll_interval_sec,
        phase_cycle=phase_cycle,
        build_two_tank_check_payload_fn=self._build_two_tank_check_payload,
        enqueue_task_fn=self.enqueue_internal_scheduler_task_fn,
    )


async def bound_compensate_two_tank_start_enqueue_failure(
    self,
    *,
    zone_id: int,
    context: Dict[str, Any],
    workflow: str,
    phase: str,
    stop_command_plan: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    return await policy_compensate_two_tank_start_enqueue_failure(
        zone_id=zone_id,
        context=context,
        workflow=workflow,
        phase=phase,
        stop_command_plan=stop_command_plan,
        reason_code_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
        dispatch_two_tank_command_plan_fn=self._dispatch_two_tank_command_plan,
        merge_with_sensor_mode_deactivate_fn=self._merge_with_sensor_mode_deactivate,
        log_two_tank_safety_guard_fn=self._log_two_tank_safety_guard,
    )


async def bound_merge_with_sensor_mode_deactivate(
    self,
    *,
    zone_id: int,
    context: Dict[str, Any],
    stop_result: Dict[str, Any],
    reason_code: str,
) -> Dict[str, Any]:
    return await policy_delegate_merge_with_sensor_mode_deactivate(
        executor=self,
        zone_id=zone_id,
        context=context,
        stop_result=stop_result,
        reason_code=reason_code,
    )


def bound_build_two_tank_deps(self, zone_id: int) -> TwoTankDeps:
    guards_enabled = bool(self._two_tank_safety_guards_enabled())
    safety_config = TwoTankSafetyConfig(
        pump_interlock=True,
        stop_confirmation_required=guards_enabled,
        irr_state_validation=guards_enabled,
    )

    async def _start_two_tank_clean_fill(**kwargs: Any) -> Dict[str, Any]:
        return await policy_start_two_tank_clean_fill(
            **kwargs,
            dispatch_two_tank_command_plan_fn=self._dispatch_two_tank_command_plan,
            enqueue_two_tank_check_fn=self._enqueue_two_tank_check,
            compensate_two_tank_start_enqueue_failure_fn=self._compensate_two_tank_start_enqueue_failure,
            emit_task_event_fn=self._emit_task_event,
            two_tank_safety_guards_enabled_fn=lambda: safety_config.stop_confirmation_required,
            reason_clean_fill_started=REASON_CLEAN_FILL_STARTED,
            reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
            reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
            err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
        )

    async def _start_two_tank_solution_fill(**kwargs: Any) -> Dict[str, Any]:
        return await policy_start_two_tank_solution_fill(
            **kwargs,
            dispatch_two_tank_command_plan_fn=self._dispatch_two_tank_command_plan,
            dispatch_sensor_mode_command_for_nodes_fn=self._dispatch_sensor_mode_command_for_nodes,
            merge_command_dispatch_results_fn=self._merge_command_dispatch_results,
            update_zone_workflow_phase_fn=self._update_zone_workflow_phase,
            enqueue_two_tank_check_fn=self._enqueue_two_tank_check,
            compensate_two_tank_start_enqueue_failure_fn=self._compensate_two_tank_start_enqueue_failure,
            emit_task_event_fn=self._emit_task_event,
            two_tank_safety_guards_enabled_fn=lambda: safety_config.stop_confirmation_required,
            workflow_phase_tank_filling=WORKFLOW_PHASE_TANK_FILLING,
            reason_solution_fill_started=REASON_SOLUTION_FILL_STARTED,
            reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
            reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
            err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
        )

    async def _start_two_tank_prepare_recirculation(**kwargs: Any) -> Dict[str, Any]:
        return await policy_start_two_tank_prepare_recirculation(
            **kwargs,
            dispatch_two_tank_command_plan_fn=self._dispatch_two_tank_command_plan,
            dispatch_sensor_mode_command_for_nodes_fn=self._dispatch_sensor_mode_command_for_nodes,
            merge_command_dispatch_results_fn=self._merge_command_dispatch_results,
            update_zone_workflow_phase_fn=self._update_zone_workflow_phase,
            enqueue_two_tank_check_fn=self._enqueue_two_tank_check,
            compensate_two_tank_start_enqueue_failure_fn=self._compensate_two_tank_start_enqueue_failure,
            two_tank_safety_guards_enabled_fn=lambda: safety_config.stop_confirmation_required,
            workflow_phase_tank_recirc=WORKFLOW_PHASE_TANK_RECIRC,
            reason_prepare_recirculation_started=REASON_PREPARE_RECIRCULATION_STARTED,
            reason_cycle_refill_command_failed=REASON_CYCLE_REFILL_COMMAND_FAILED,
            reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
            err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
        )

    async def _start_two_tank_irrigation_recovery(**kwargs: Any) -> Dict[str, Any]:
        return await policy_start_two_tank_irrigation_recovery(
            **kwargs,
            dispatch_two_tank_command_plan_fn=self._dispatch_two_tank_command_plan,
            dispatch_sensor_mode_command_for_nodes_fn=self._dispatch_sensor_mode_command_for_nodes,
            merge_command_dispatch_results_fn=self._merge_command_dispatch_results,
            update_zone_workflow_phase_fn=self._update_zone_workflow_phase,
            enqueue_two_tank_check_fn=self._enqueue_two_tank_check,
            compensate_two_tank_start_enqueue_failure_fn=self._compensate_two_tank_start_enqueue_failure,
            two_tank_safety_guards_enabled_fn=lambda: safety_config.stop_confirmation_required,
            workflow_phase_irrig_recirc=WORKFLOW_PHASE_IRRIG_RECIRC,
            reason_irrigation_recovery_started=REASON_IRRIGATION_RECOVERY_STARTED,
            reason_irrigation_recovery_failed=REASON_IRRIGATION_RECOVERY_FAILED,
            reason_cycle_self_task_enqueue_failed=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            err_two_tank_command_failed=ERR_TWO_TANK_COMMAND_FAILED,
            err_two_tank_enqueue_failed=ERR_TWO_TANK_ENQUEUE_FAILED,
        )

    return TwoTankDeps(
        zone_id=zone_id,
        fetch_fn=self.fetch_fn,
        command_gateway=self.command_gateway,
        dispatch_two_tank_command_plan=self._dispatch_two_tank_command_plan,
        emit_task_event=self._emit_task_event,
        update_zone_workflow_phase=self._update_zone_workflow_phase,
        find_zone_event_since=self._find_zone_event_since,
        check_required_nodes_online=self._check_required_nodes_online,
        get_zone_nodes=self._get_zone_nodes,
        read_level_switch=self._read_level_switch,
        evaluate_ph_ec_targets=self._evaluate_ph_ec_targets,
        start_two_tank_clean_fill=_start_two_tank_clean_fill,
        start_two_tank_solution_fill=_start_two_tank_solution_fill,
        start_two_tank_prepare_recirculation=_start_two_tank_prepare_recirculation,
        start_two_tank_irrigation_recovery=_start_two_tank_irrigation_recovery,
        merge_with_sensor_mode_deactivate=self._merge_with_sensor_mode_deactivate,
        enqueue_two_tank_check=self._enqueue_two_tank_check,
        resolve_int=self._resolve_int,
        normalize_two_tank_workflow=self._normalize_two_tank_workflow,
        resolve_two_tank_runtime_config=self._resolve_two_tank_runtime_config,
        extract_topology=self._extract_topology,
        telemetry_freshness_enforce=self._telemetry_freshness_enforce,
        safety_config=safety_config,
        log_two_tank_safety_guard=self._log_two_tank_safety_guard,
        build_two_tank_stop_not_confirmed_result=self._build_two_tank_stop_not_confirmed_result,
    )


async def bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    deps = self._build_two_tank_deps(zone_id)
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
        build_two_tank_runtime_payload_fn=self._build_two_tank_runtime_payload,
        resolve_two_tank_runtime_config_fn=self._resolve_two_tank_runtime_config,
        emit_task_event_fn=self._emit_task_event,
        start_two_tank_irrigation_recovery_fn=deps.start_two_tank_irrigation_recovery,
    )


__all__ = [
    "bound_build_two_tank_deps",
    "bound_compensate_two_tank_start_enqueue_failure",
    "bound_enqueue_two_tank_check",
    "bound_merge_with_sensor_mode_deactivate",
    "bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure",
]
