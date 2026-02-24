"""Bound workflow phase/runtime helper methods for SchedulerTaskExecutor."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from executor.executor_constants import (
    AUTO_LOGIC_TANK_STATE_MACHINE_V1,
    TELEMETRY_FRESHNESS_ENFORCE,
    TELEMETRY_FRESHNESS_MAX_AGE_SEC,
    THREE_TANK_TOPOLOGIES,
    TWO_TANK_TOPOLOGIES,
    _runtime_scheduler_constant,
)
from executor.workflow_phase_policy import (
    build_workflow_state_payload as policy_build_workflow_state_payload,
    derive_workflow_phase as policy_derive_workflow_phase,
    extract_workflow_hint as policy_extract_workflow_hint,
    resolve_workflow_stage_for_state_sync as policy_resolve_workflow_stage_for_state_sync,
)
from domain.policies.workflow_input_policy import extract_topology as policy_extract_topology

logger = logging.getLogger(__name__)


def bound_requires_explicit_workflow(payload: Dict[str, Any]) -> bool:
    topology = policy_extract_topology(payload)
    return topology in (TWO_TANK_TOPOLOGIES | THREE_TANK_TOPOLOGIES)


def bound_tank_state_machine_enabled() -> bool:
    return bool(_runtime_scheduler_constant("AUTO_LOGIC_TANK_STATE_MACHINE_V1", AUTO_LOGIC_TANK_STATE_MACHINE_V1))


def bound_telemetry_freshness_enforce() -> bool:
    return bool(_runtime_scheduler_constant("TELEMETRY_FRESHNESS_ENFORCE", TELEMETRY_FRESHNESS_ENFORCE))


def bound_telemetry_freshness_max_age_sec() -> int:
    raw = _runtime_scheduler_constant("TELEMETRY_FRESHNESS_MAX_AGE_SEC", TELEMETRY_FRESHNESS_MAX_AGE_SEC)
    try:
        return max(30, int(raw))
    except Exception:
        return TELEMETRY_FRESHNESS_MAX_AGE_SEC


def bound_extract_workflow_hint(payload: Dict[str, Any], result: Dict[str, Any]) -> str:
    return policy_extract_workflow_hint(payload, result)


def bound_derive_workflow_phase(
    *,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[str]:
    return policy_derive_workflow_phase(
        task_type=task_type,
        payload=payload,
        result=result,
        logger=logger,
    )


def bound_build_workflow_state_payload(
    *,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    workflow_phase: str,
    workflow_stage: str,
) -> Dict[str, Any]:
    return policy_build_workflow_state_payload(
        payload=payload,
        result=result,
        workflow_phase=workflow_phase,
        workflow_stage=workflow_stage,
    )


def bound_resolve_workflow_stage_for_state_sync(
    *,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    workflow_phase: str,
) -> str:
    return policy_resolve_workflow_stage_for_state_sync(
        payload=payload,
        result=result,
        workflow_phase=workflow_phase,
    )


async def bound_sync_zone_workflow_phase(
    self,
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    context: Dict[str, Any],
) -> None:
    await self.workflow_state_sync.sync(
        zone_id=zone_id,
        task_type=task_type,
        payload=payload,
        result=result,
        context=context,
    )


__all__ = [
    "bound_build_workflow_state_payload",
    "bound_derive_workflow_phase",
    "bound_extract_workflow_hint",
    "bound_requires_explicit_workflow",
    "bound_resolve_workflow_stage_for_state_sync",
    "bound_sync_zone_workflow_phase",
    "bound_tank_state_machine_enabled",
    "bound_telemetry_freshness_enforce",
    "bound_telemetry_freshness_max_age_sec",
]
