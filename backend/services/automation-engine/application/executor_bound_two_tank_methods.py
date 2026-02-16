"""Bound two-tank methods for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from application.executor_constants import REASON_CYCLE_REFILL_COMMAND_FAILED
from application.executor_method_delegates import (
    start_two_tank_clean_fill as policy_delegate_start_two_tank_clean_fill,
    start_two_tank_irrigation_recovery as policy_delegate_start_two_tank_irrigation_recovery,
    start_two_tank_prepare_recirculation as policy_delegate_start_two_tank_prepare_recirculation,
    start_two_tank_solution_fill as policy_delegate_start_two_tank_solution_fill,
    try_start_two_tank_irrigation_recovery_from_irrigation_failure as policy_delegate_try_start_two_tank_irrigation_recovery_from_irrigation_failure,
)
from application.executor_event_delegates import (
    merge_with_sensor_mode_deactivate as policy_delegate_merge_with_sensor_mode_deactivate,
)
from application.two_tank_compensation import (
    compensate_two_tank_start_enqueue_failure as policy_compensate_two_tank_start_enqueue_failure,
)
from application.two_tank_enqueue import enqueue_two_tank_check as policy_enqueue_two_tank_check


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


async def bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    return await policy_delegate_try_start_two_tank_irrigation_recovery_from_irrigation_failure(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        result=result,
    )


async def bound_start_two_tank_clean_fill(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    cycle: int,
) -> Dict[str, Any]:
    return await policy_delegate_start_two_tank_clean_fill(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        cycle=cycle,
    )


async def bound_start_two_tank_solution_fill(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return await policy_delegate_start_two_tank_solution_fill(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
    )


async def bound_start_two_tank_prepare_recirculation(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    return await policy_delegate_start_two_tank_prepare_recirculation(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
    )


async def bound_start_two_tank_irrigation_recovery(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    attempt: int,
) -> Dict[str, Any]:
    return await policy_delegate_start_two_tank_irrigation_recovery(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        attempt=attempt,
    )


__all__ = [
    "bound_compensate_two_tank_start_enqueue_failure",
    "bound_enqueue_two_tank_check",
    "bound_merge_with_sensor_mode_deactivate",
    "bound_start_two_tank_clean_fill",
    "bound_start_two_tank_irrigation_recovery",
    "bound_start_two_tank_prepare_recirculation",
    "bound_start_two_tank_solution_fill",
    "bound_try_start_two_tank_irrigation_recovery_from_irrigation_failure",
]
