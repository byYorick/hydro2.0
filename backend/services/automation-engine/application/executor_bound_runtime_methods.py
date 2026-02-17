"""Bound runtime helpers for SchedulerTaskExecutor."""

from __future__ import annotations

from typing import Any, Dict, Optional

from application.executor_constants import REASON_OUTSIDE_TEMP_BLOCKED, REASON_WIND_BLOCKED
from application.executor_small_delegates import (
    build_two_tank_runtime_payload as policy_delegate_build_two_tank_runtime_payload,
    execute_device_task_core as policy_delegate_execute_device_task_core,
)
from application.ventilation_climate_guards import (
    apply_ventilation_climate_guards as policy_apply_ventilation_climate_guards,
)
from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome


async def bound_execute_device_task(
    self,
    zone_id: int,
    payload: Dict[str, Any],
    mapping: SchedulerTaskMapping,
    *,
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    return await self.command_dispatch.execute_device_task(
        zone_id=zone_id,
        payload=payload,
        mapping=mapping,
        context=context,
        decision=decision,
        task_type=mapping.task_type,
    )


async def bound_execute_device_task_core(
    self,
    zone_id: int,
    payload: Dict[str, Any],
    mapping: SchedulerTaskMapping,
    *,
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    return await policy_delegate_execute_device_task_core(
        executor=self,
        zone_id=zone_id,
        payload=payload,
        mapping=mapping,
        context=context,
        decision=decision,
        send_infra_alert_fn=self.send_infra_alert_fn,
    )


async def bound_apply_ventilation_climate_guards(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    decision: DecisionOutcome,
) -> DecisionOutcome:
    return await policy_apply_ventilation_climate_guards(
        zone_id=zone_id,
        payload=payload,
        decision=decision,
        read_latest_metric_fn=self._read_latest_metric,
        to_optional_float_fn=self._to_optional_float,
        with_decision_details_fn=self._with_decision_details,
        wind_blocked_reason=REASON_WIND_BLOCKED,
        outside_temp_blocked_reason=REASON_OUTSIDE_TEMP_BLOCKED,
    )


def bound_build_two_tank_runtime_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return policy_delegate_build_two_tank_runtime_payload(
        payload=payload,
        merge_dict_recursive_fn=self._merge_dict_recursive,
    )


__all__ = [
    "bound_apply_ventilation_climate_guards",
    "bound_build_two_tank_runtime_payload",
    "bound_execute_device_task",
    "bound_execute_device_task_core",
]
