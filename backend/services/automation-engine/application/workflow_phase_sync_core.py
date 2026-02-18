"""Core helper for workflow phase synchronization side effects."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from services.resilience_contract import INFRA_ZONE_WORKFLOW_STATE_PERSIST_FAILED

DeriveWorkflowPhaseFn = Callable[..., str | None]
ExtractWorkflowHintFn = Callable[[Dict[str, Any], Dict[str, Any]], str]
NormalizeWorkflowPhaseFn = Callable[[Any], str]
ResolveWorkflowStageFn = Callable[..., str]
BuildWorkflowStatePayloadFn = Callable[..., Dict[str, Any]]
StoreSetFn = Callable[..., Awaitable[None]]
SendInfraAlertFn = Callable[..., Awaitable[Any]]


async def sync_zone_workflow_phase_core(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    context: Dict[str, Any],
    logger_obj: Any,
    workflow_state_persist_enabled: bool,
    workflow_state_persist_failed: bool,
    derive_workflow_phase_fn: DeriveWorkflowPhaseFn,
    extract_workflow_hint_fn: ExtractWorkflowHintFn,
    normalize_workflow_phase_fn: NormalizeWorkflowPhaseFn,
    resolve_workflow_stage_for_state_sync_fn: ResolveWorkflowStageFn,
    build_workflow_state_payload_fn: BuildWorkflowStatePayloadFn,
    workflow_state_store_set_fn: StoreSetFn,
    zone_service: Any,
    send_infra_alert_fn: SendInfraAlertFn,
) -> bool:
    workflow_phase = derive_workflow_phase_fn(task_type=task_type, payload=payload, result=result)
    if workflow_phase is None:
        logger_obj.info(
            "Workflow phase sync skipped: no phase transition derived",
            extra={
                "zone_id": zone_id,
                "task_type": task_type,
                "decision": str(result.get("decision") or "") or None,
                "reason_code": str(result.get("reason_code") or "") or None,
                "mode": str(result.get("mode") or "") or None,
                "workflow": extract_workflow_hint_fn(payload, result) or None,
                "success": bool(result.get("success")),
                "action_required": bool(result.get("action_required")),
            },
        )
        return workflow_state_persist_failed

    normalized_phase = normalize_workflow_phase_fn(workflow_phase)
    logger_obj.info(
        "Workflow phase derived for sync",
        extra={
            "zone_id": zone_id,
            "task_type": task_type,
            "derived_phase": workflow_phase,
            "normalized_phase": normalized_phase,
            "decision": str(result.get("decision") or "") or None,
            "reason_code": str(result.get("reason_code") or "") or None,
            "mode": str(result.get("mode") or "") or None,
            "workflow": extract_workflow_hint_fn(payload, result) or None,
            "success": bool(result.get("success")),
            "action_required": bool(result.get("action_required")),
        },
    )
    workflow_stage = resolve_workflow_stage_for_state_sync_fn(
        payload=payload,
        result=result,
        workflow_phase=normalized_phase,
    )
    raw_workflow_hint = extract_workflow_hint_fn(payload, result)
    if raw_workflow_hint and workflow_stage and raw_workflow_hint != workflow_stage:
        logger_obj.info(
            "Workflow stage canonicalized for persistence",
            extra={
                "zone_id": zone_id,
                "task_type": task_type,
                "workflow_phase": normalized_phase,
                "workflow_mode": str(result.get("mode") or "") or None,
                "raw_workflow": raw_workflow_hint,
                "canonical_workflow": workflow_stage,
                "reason_code": str(result.get("reason_code") or "") or None,
            },
        )
    state_payload = build_workflow_state_payload_fn(
        payload=payload,
        result=result,
        workflow_phase=normalized_phase,
        workflow_stage=workflow_stage,
    )
    scheduler_task_id = str(context.get("task_id") or "").strip() or None

    persist_failed = workflow_state_persist_failed
    persist_to_store = workflow_state_persist_enabled and not persist_failed
    if persist_to_store:
        try:
            await workflow_state_store_set_fn(
                zone_id=zone_id,
                workflow_phase=normalized_phase,
                payload=state_payload,
                scheduler_task_id=scheduler_task_id,
            )
        except Exception as exc:
            logger_obj.warning(
                "Failed to persist zone_workflow_state: zone_id=%s phase=%s error=%s",
                zone_id,
                normalized_phase,
                exc,
                exc_info=True,
            )
            persist_failed = True
            try:
                await send_infra_alert_fn(
                    code=INFRA_ZONE_WORKFLOW_STATE_PERSIST_FAILED,
                    alert_type="Zone Workflow State Persist Failed",
                    message="Не удалось обновить zone_workflow_state",
                    severity="error",
                    zone_id=zone_id,
                    service="automation-engine",
                    component="scheduler_task_executor",
                    error_type=type(exc).__name__,
                    details={
                        "workflow_phase": normalized_phase,
                        "task_type": task_type,
                        "workflow_mode": result.get("mode"),
                        "workflow_hint": extract_workflow_hint_fn(payload, result),
                        "task_id": scheduler_task_id,
                        "error": str(exc),
                    },
                )
            except Exception:
                logger_obj.warning(
                    "Failed to send infra alert for workflow-state persistence error",
                    exc_info=True,
                    extra={"zone_id": zone_id, "workflow_phase": normalized_phase},
                )

    if zone_service is None:
        return persist_failed

    update_method = getattr(zone_service, "update_workflow_phase", None)
    if callable(update_method):
        try:
            await update_method(
                zone_id=zone_id,
                workflow_phase=normalized_phase,
                workflow_stage=workflow_stage or None,
                source="scheduler_task_executor",
                reason_code=str(result.get("reason_code") or "") or None,
            )
            return persist_failed
        except Exception:
            logger_obj.warning(
                "Failed to sync workflow phase with zone_service.update_workflow_phase",
                exc_info=True,
                extra={"zone_id": zone_id, "workflow_phase": normalized_phase},
            )

    set_method = getattr(zone_service, "set_zone_workflow_phase", None)
    if callable(set_method):
        try:
            set_method(zone_id, normalized_phase)
        except Exception:
            logger_obj.warning(
                "Failed to sync workflow phase with zone_service.set_zone_workflow_phase",
                exc_info=True,
                extra={"zone_id": zone_id, "workflow_phase": normalized_phase},
            )

    return persist_failed


__all__ = ["sync_zone_workflow_phase_core"]
