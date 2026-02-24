"""Recovery logic for workflow-state continuation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from ae2lite.api_recovery_types import RecoverySummary
from ae2lite.api_recovery_workflow_helpers import (
    coerce_utc_naive,
    extract_recovery_correlation_id,
    log_workflow_recovery_action,
    resolve_recovery_phase,
    resolve_workflow_for_recovery,
    send_workflow_recovery_alert_safe,
)
from services.resilience_contract import (
    INFRA_WORKFLOW_STATE_RECOVERY_ENQUEUE_FAILED,
    INFRA_WORKFLOW_STATE_RECOVERY_ROW_FAILED,
    SCHEDULER_RECOVERY_SOURCE_STARTUP,
    SCHEDULER_SOURCE_WORKFLOW_STATE_RECOVERY,
)


async def _recover_zone_workflow_row(
    *,
    row: Dict[str, Any],
    now: datetime,
    stale_timeout_sec: int,
    workflow_state_store: Any,
    logger: logging.Logger,
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    enqueue_internal_scheduler_task_fn: Callable[..., Awaitable[Dict[str, Any]]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    get_trace_id_fn: Callable[[], Optional[str]],
) -> RecoverySummary:
    zone_id: Optional[int] = None
    phase_source = "zone_workflow_state.workflow_phase"
    phase = "idle"
    workflow: Optional[str] = None
    age_sec = 0
    enqueue_id: Optional[str] = None
    previous_task_id = str(row.get("scheduler_task_id") or "").strip() or None
    correlation_id: Optional[str] = None

    def _log(
        *,
        action: str,
        reason: str,
        level: int,
        selected_workflow: Optional[str] = None,
        error: Optional[Exception] = None,
    ) -> None:
        log_workflow_recovery_action(
            zone_id=zone_id,
            workflow_phase_source=phase_source,
            workflow_phase_normalized=phase,
            workflow_selected=selected_workflow,
            scheduler_task_id_previous=previous_task_id,
            recovery_action=action,
            reason_code=reason,
            state_age_sec=age_sec,
            correlation_id=correlation_id,
            enqueue_id=enqueue_id,
            level=level,
            error_type=type(error).__name__ if error is not None else None,
            error_message=str(error) if error is not None else None,
            logger=logger,
            get_trace_id_fn=get_trace_id_fn,
        )

    try:
        raw_zone_id = row.get("zone_id")
        try:
            zone_id = int(raw_zone_id)
        except (TypeError, ValueError):
            logger.warning("Workflow recovery skipped invalid row: invalid zone_id raw_zone_id=%r", raw_zone_id)
            _log(action="skip_invalid", reason="invalid_zone_id", level=logging.WARNING)
            return {"recovered": 0, "stale_stopped": 0, "skipped": 1, "failed": 0}

        raw_payload = row.get("payload")
        if not isinstance(raw_payload, dict):
            logger.warning(
                "Workflow recovery skipped invalid payload: zone_id=%s payload_type=%s",
                zone_id,
                type(raw_payload).__name__,
            )
            _log(action="skip_invalid", reason="invalid_payload", level=logging.WARNING)
            return {"recovered": 0, "stale_stopped": 0, "skipped": 1, "failed": 0}

        payload = dict(raw_payload)
        correlation_id = extract_recovery_correlation_id(payload)
        phase, phase_source, phase_error = resolve_recovery_phase(row, payload)
        if phase_error is not None:
            logger.warning(
                "Workflow recovery skipped invalid phase: zone_id=%s raw_phase=%r payload_phase=%r",
                zone_id,
                row.get("workflow_phase_raw", row.get("workflow_phase")),
                payload.get("workflow_phase"),
            )
            _log(action="skip_invalid", reason=phase_error, level=logging.WARNING)
            return {"recovered": 0, "stale_stopped": 0, "skipped": 1, "failed": 0}

        updated_at = coerce_utc_naive(row.get("updated_at")) or now
        age_sec = max(0, int((now - updated_at).total_seconds()))

        if phase in {"idle", "ready"}:
            _log(action="skip_idle_ready", reason=f"phase_{phase}", level=logging.INFO)
            return {"recovered": 0, "stale_stopped": 0, "skipped": 1, "failed": 0}

        if age_sec > stale_timeout_sec:
            try:
                await workflow_state_store.set(
                    zone_id=zone_id,
                    workflow_phase="idle",
                    payload={**payload, "recovery": {"action": "stale_safety_stop", "age_sec": age_sec}},
                    scheduler_task_id=None,
                )
                await create_zone_event_fn(
                    zone_id,
                    "WORKFLOW_RECOVERY_STALE_STOPPED",
                    {
                        "previous_workflow_phase": phase,
                        "age_sec": age_sec,
                        "stale_timeout_sec": stale_timeout_sec,
                    },
                )
                _log(action="stale_stop", reason="state_stale_timeout", level=logging.INFO)
                return {"recovered": 0, "stale_stopped": 1, "skipped": 0, "failed": 0}
            except Exception as exc:
                logger.error(
                    "Failed to stale-stop workflow state during recovery: zone_id=%s phase=%s error=%s",
                    zone_id,
                    phase,
                    exc,
                    exc_info=True,
                )
                _log(action="failed", reason="stale_stop_failed", level=logging.ERROR, error=exc)
                return {"recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 1}

        workflow_resolution = resolve_workflow_for_recovery(
            phase,
            payload,
            zone_id=zone_id,
            logger=logger,
        )
        workflow = str(workflow_resolution.get("workflow") or "").strip().lower() or None
        reason_code = str(workflow_resolution.get("reason_code") or "").strip().lower() or "workflow_unresolved"
        fallback_from = str(workflow_resolution.get("fallback_from") or "").strip().lower() or None
        fallback_to = str(workflow_resolution.get("fallback_to") or "").strip().lower() or None

        if not workflow:
            logger.warning(
                "Workflow recovery skipped: no continuation workflow resolved: zone_id=%s phase=%s workflow_source=%s",
                zone_id,
                phase,
                workflow_resolution.get("workflow_source"),
            )
            _log(action="skip_invalid", reason=reason_code, level=logging.WARNING)
            return {"recovered": 0, "stale_stopped": 0, "skipped": 1, "failed": 0}

        if fallback_from and fallback_to and fallback_from != fallback_to:
            logger.warning(
                "Workflow recovery fallback applied: zone_id=%s phase=%s fallback_from=%s fallback_to=%s reason=%s",
                zone_id,
                phase,
                fallback_from,
                fallback_to,
                reason_code,
            )
            try:
                await create_zone_event_fn(
                    zone_id,
                    "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK",
                    {
                        "workflow_phase": phase,
                        "fallback_from": fallback_from,
                        "fallback_to": fallback_to,
                        "reason_code": reason_code,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist workflow fallback event during recovery: zone_id=%s error=%s",
                    zone_id,
                    exc,
                    exc_info=True,
                )

        continuation_payload = dict(payload)
        continuation_payload["workflow"] = workflow
        continuation_payload["workflow_stage"] = workflow
        continuation_payload["workflow_phase"] = phase
        continuation_payload.setdefault("payload_contract_version", "v2")
        continuation_payload["recovery"] = {
            "source": SCHEDULER_RECOVERY_SOURCE_STARTUP,
            "workflow_phase": phase,
            "workflow_phase_source": phase_source,
            "state_age_sec": age_sec,
            "previous_scheduler_task_id": previous_task_id,
            "reason_code": reason_code,
        }

        try:
            enqueue_result = await enqueue_internal_scheduler_task_fn(
                zone_id=zone_id,
                task_type="diagnostics",
                payload=continuation_payload,
                scheduled_for=now.isoformat(),
                source=SCHEDULER_SOURCE_WORKFLOW_STATE_RECOVERY,
            )
            enqueue_id = str(enqueue_result.get("enqueue_id") or "").strip() or None
            correlation_id = correlation_id or (str(enqueue_result.get("correlation_id") or "").strip() or None)
            await workflow_state_store.set(
                zone_id=zone_id,
                workflow_phase=phase,
                payload=continuation_payload,
                scheduler_task_id=enqueue_id or "",
            )
            await create_zone_event_fn(
                zone_id,
                "WORKFLOW_RECOVERY_ENQUEUED",
                {
                    "workflow_phase": phase,
                    "workflow": workflow,
                    "enqueue_id": enqueue_id,
                    "correlation_id": correlation_id,
                    "state_age_sec": age_sec,
                },
            )
            _log(action="enqueue_continuation", reason=reason_code, level=logging.INFO, selected_workflow=workflow)
            return {"recovered": 1, "stale_stopped": 0, "skipped": 0, "failed": 0}
        except Exception as exc:
            logger.error(
                "Failed to enqueue workflow continuation during startup recovery: zone_id=%s phase=%s error=%s",
                zone_id,
                phase,
                exc,
                exc_info=True,
            )
            _log(action="failed", reason="enqueue_failed", level=logging.ERROR, selected_workflow=workflow, error=exc)
            await send_workflow_recovery_alert_safe(
                error=exc,
                code=INFRA_WORKFLOW_STATE_RECOVERY_ENQUEUE_FAILED,
                alert_type="Workflow State Recovery Enqueue Failed",
                zone_id=zone_id,
                details={"workflow_phase": phase, "workflow": workflow},
                send_infra_exception_alert_fn=send_infra_exception_alert_fn,
                logger=logger,
            )
            return {"recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 1}
    except Exception as exc:
        logger.error(
            "Unexpected workflow recovery failure for zone row: zone_id=%s error=%s",
            zone_id,
            exc,
            exc_info=True,
        )
        _log(action="failed", reason="recovery_exception", level=logging.ERROR, selected_workflow=workflow, error=exc)
        await send_workflow_recovery_alert_safe(
            error=exc,
            code=INFRA_WORKFLOW_STATE_RECOVERY_ROW_FAILED,
            alert_type="Workflow State Recovery Row Failed",
            zone_id=zone_id,
            details={"workflow_phase": phase, "scheduler_task_id_previous": previous_task_id},
            send_infra_exception_alert_fn=send_infra_exception_alert_fn,
            logger=logger,
        )
        return {"recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 1}


async def recover_zone_workflow_states(
    *,
    enabled: bool,
    stale_timeout_sec: int,
    workflow_state_store: Any,
    logger: logging.Logger,
    create_zone_event_fn: Callable[[int, str, Dict[str, Any]], Awaitable[Any]],
    enqueue_internal_scheduler_task_fn: Callable[..., Awaitable[Dict[str, Any]]],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    get_trace_id_fn: Callable[[], Optional[str]],
) -> RecoverySummary:
    if not enabled:
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovered = 0
    stale_stopped = 0
    skipped = 0
    failed = 0

    try:
        active_states = await workflow_state_store.list_active()
    except Exception:
        logger.warning("Zone workflow state recovery scan failed", exc_info=True)
        return {"active": 0, "recovered": 0, "stale_stopped": 0, "skipped": 0, "failed": 0}

    for row in active_states:
        row_summary = await _recover_zone_workflow_row(
            row=row,
            now=now,
            stale_timeout_sec=stale_timeout_sec,
            workflow_state_store=workflow_state_store,
            logger=logger,
            create_zone_event_fn=create_zone_event_fn,
            enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task_fn,
            send_infra_exception_alert_fn=send_infra_exception_alert_fn,
            get_trace_id_fn=get_trace_id_fn,
        )
        recovered += int(row_summary.get("recovered") or 0)
        stale_stopped += int(row_summary.get("stale_stopped") or 0)
        skipped += int(row_summary.get("skipped") or 0)
        failed += int(row_summary.get("failed") or 0)

    return {
        "active": len(active_states),
        "recovered": recovered,
        "stale_stopped": stale_stopped,
        "skipped": skipped,
        "failed": failed,
    }


__all__ = ["recover_zone_workflow_states"]
