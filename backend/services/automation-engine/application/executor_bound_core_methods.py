"""Bound core methods for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert
from application.diagnostics_task_execution import execute_diagnostics_task as policy_execute_diagnostics_task
from application.executor_constants import (
    CYCLE_START_WORKFLOWS,
    ERR_INVALID_PAYLOAD_CONTRACT_VERSION,
    REASON_OUTSIDE_TEMP_BLOCKED,
    REASON_WIND_BLOCKED,
)
from application.executor_event_delegates import emit_task_event as policy_delegate_emit_task_event
from application.executor_method_delegates import (
    sync_zone_workflow_phase_core as policy_delegate_sync_zone_workflow_phase_core,
)
from application.executor_small_delegates import (
    publish_batch as policy_delegate_publish_batch,
    update_zone_workflow_phase as policy_delegate_update_zone_workflow_phase,
)
from application.task_events_persistence import persist_zone_event_safe as policy_persist_zone_event_safe
from application.workflow_phase_policy import WORKFLOW_PHASE_EVENT_TYPE
from domain.policies.outcome_enrichment_policy import ensure_extended_outcome as policy_ensure_extended_outcome
from scheduler_internal_enqueue import enqueue_internal_scheduler_task
from application.decision_retry_enqueue import enqueue_decision_retry as policy_enqueue_decision_retry

logger = logging.getLogger(__name__)


async def bound_create_zone_event_safe(
    self,
    *,
    zone_id: int,
    event_type: str,
    payload: Dict[str, Any],
    task_type: str,
    context: Dict[str, Any],
) -> bool:
    return await policy_persist_zone_event_safe(
        zone_id=zone_id,
        event_type=event_type,
        payload=payload,
        task_type=task_type,
        context=context,
        create_zone_event_fn=create_zone_event,
        send_infra_alert_fn=send_infra_alert,
        log_warning=logger.warning,
    )


async def bound_sync_zone_workflow_phase_core(
    self,
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    context: Dict[str, Any],
) -> None:
    await policy_delegate_sync_zone_workflow_phase_core(
        executor=self,
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        result=result,
        context=context,
        logger_obj=logger,
        send_infra_alert_fn=send_infra_alert,
    )


async def bound_emit_task_event(
    self,
    *,
    zone_id: int,
    task_type: str,
    context: Dict[str, Any],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    await policy_delegate_emit_task_event(
        executor=self,
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type=event_type,
        payload=payload,
        event_id_factory=lambda: f"evt-{uuid4().hex}",
    )


async def bound_update_zone_workflow_phase(
    self,
    *,
    zone_id: int,
    workflow_phase: str,
    context: Dict[str, Any],
    workflow_stage: Optional[str] = None,
    reason_code: Optional[str] = None,
    source: str = "scheduler_task_executor",
) -> str:
    return await policy_delegate_update_zone_workflow_phase(
        executor=self,
        zone_id=zone_id,
        workflow_phase=workflow_phase,
        context=context,
        workflow_phase_event_type=WORKFLOW_PHASE_EVENT_TYPE,
        log_warning=logger.warning,
        workflow_stage=workflow_stage,
        reason_code=reason_code,
        source=source,
    )


async def bound_publish_batch(
    self,
    *,
    zone_id: int,
    task_type: str,
    nodes: Sequence[Dict[str, Any]],
    cmd: str,
    params: Optional[Dict[str, Any]] = None,
    context: Dict[str, Any],
    decision: Any,
    accepted_terminal_statuses: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    return await policy_delegate_publish_batch(
        executor=self,
        zone_id=zone_id,
        task_type=task_type,
        nodes=nodes,
        cmd=cmd,
        params=params,
        context=context,
        decision=decision,
        accepted_terminal_statuses=accepted_terminal_statuses,
        terminal_status_to_error_code_fn=self._terminal_status_to_error_code,
        emit_task_event_fn=self._emit_task_event,
    )


async def bound_enqueue_decision_retry(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    return await policy_enqueue_decision_retry(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        result=result,
        enqueue_task_fn=enqueue_internal_scheduler_task,
        extract_retry_attempt_fn=self._extract_retry_attempt,
        build_correlation_id_fn=self._build_decision_retry_correlation_id,
    )


def bound_ensure_extended_outcome(
    self,
    *,
    task_type: str,
    payload: Dict[str, Any],
    decision: Any,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    return policy_ensure_extended_outcome(
        task_type=task_type,
        payload=payload,
        decision=decision,
        result=result,
        extract_next_due_at=lambda d, r: self._extract_next_due_at(decision=d, result=r),
        safe_int=self._safe_int,
        extract_topology=self._extract_topology,
        extract_two_tank_chemistry_orchestration=self._extract_two_tank_chemistry_orchestration,
        wind_blocked_reason=REASON_WIND_BLOCKED,
        outside_temp_blocked_reason=REASON_OUTSIDE_TEMP_BLOCKED,
    )


async def bound_execute_diagnostics_task(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
) -> Dict[str, Any]:
    return await policy_execute_diagnostics_task(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        workflow_validator=self.workflow_validator,
        dispatch_diagnostics_workflow_fn=self._dispatch_diagnostics_workflow,
        execute_diagnostics_fn=self._execute_diagnostics,
        build_invalid_payload_result_fn=self._build_diagnostics_invalid_payload_result,
        cycle_start_workflows=CYCLE_START_WORKFLOWS,
        err_invalid_payload_contract_version=ERR_INVALID_PAYLOAD_CONTRACT_VERSION,
    )


async def bound_dispatch_diagnostics_workflow(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: Any,
    workflow: str,
    topology: str,
) -> Dict[str, Any]:
    return await self.workflow_router.route_diagnostics(
        zone_id=zone_id,
        payload=payload,
        context=context,
        decision=decision,
        workflow=workflow,
        topology=topology,
        task_type="diagnostics",
    )


__all__ = [
    "bound_create_zone_event_safe",
    "bound_dispatch_diagnostics_workflow",
    "bound_emit_task_event",
    "bound_enqueue_decision_retry",
    "bound_ensure_extended_outcome",
    "bound_execute_diagnostics_task",
    "bound_publish_batch",
    "bound_sync_zone_workflow_phase_core",
    "bound_update_zone_workflow_phase",
]
