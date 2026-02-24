"""Bound workflow methods for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

import logging
from typing import Any, Dict

from application.diagnostics_execution import execute_diagnostics as policy_execute_diagnostics
from application.executor_constants import (
    ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
    REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
)

logger = logging.getLogger(__name__)


async def bound_execute_two_tank_startup_workflow(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    return await self.two_tank_workflow.execute(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_two_tank_startup_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    from domain.workflows.two_tank_core import execute_two_tank_startup_workflow_core

    return await execute_two_tank_startup_workflow_core(
        self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_three_tank_startup_workflow(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    return await self.three_tank_workflow.execute(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_three_tank_startup_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    from domain.workflows.three_tank_core import execute_three_tank_startup_workflow_core

    return await execute_three_tank_startup_workflow_core(
        self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_cycle_start_workflow(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    return await self.cycle_start_workflow.execute(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_cycle_start_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    from domain.workflows.cycle_start_core import execute_cycle_start_workflow_core

    return await execute_cycle_start_workflow_core(
        self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
    )


async def bound_execute_diagnostics(
    self,
    zone_id: int,
    payload: Dict[str, Any],
    *,
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    return await policy_execute_diagnostics(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        zone_service=self.zone_service,
        logger_obj=logger,
        reason_diagnostics_service_unavailable=REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
        err_diagnostics_service_unavailable=ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
        emit_task_event_fn=self._emit_task_event,
        send_infra_alert_fn=self.send_infra_alert_fn,
    )


__all__ = [
    "bound_execute_cycle_start_workflow",
    "bound_execute_cycle_start_workflow_core",
    "bound_execute_diagnostics",
    "bound_execute_three_tank_startup_workflow",
    "bound_execute_three_tank_startup_workflow_core",
    "bound_execute_two_tank_startup_workflow",
    "bound_execute_two_tank_startup_workflow_core",
]
