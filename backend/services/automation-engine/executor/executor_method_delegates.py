"""Delegates for verbose SchedulerTaskExecutor method wiring."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from executor.workflow_phase_sync_core import (
    sync_zone_workflow_phase_core as policy_sync_zone_workflow_phase_core,
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


__all__ = ["sync_zone_workflow_phase_core"]
