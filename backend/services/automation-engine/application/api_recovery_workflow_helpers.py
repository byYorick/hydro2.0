"""Helpers for workflow-state recovery."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple


def normalize_recovery_phase(raw_phase: Any) -> str:
    value = str(raw_phase or "").strip().lower()
    if value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}:
        return value
    return "idle"


def is_valid_recovery_phase(raw_phase: Any) -> bool:
    value = str(raw_phase or "").strip().lower()
    return value in {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}


def extract_recovery_execution_workflow(payload: Dict[str, Any]) -> str:
    targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
    diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
    execution = diagnostics_targets.get("execution") if isinstance(diagnostics_targets.get("execution"), dict) else {}
    return str(execution.get("workflow") or "").strip().lower()


def extract_payload_workflow_stage(payload: Dict[str, Any]) -> Tuple[str, str]:
    candidates = [
        ("workflow_stage", payload.get("workflow_stage")),
        ("workflow", payload.get("workflow")),
        ("diagnostics_workflow", payload.get("diagnostics_workflow")),
        ("targets.diagnostics.execution.workflow", extract_recovery_execution_workflow(payload)),
    ]
    for source, raw_value in candidates:
        value = str(raw_value or "").strip().lower()
        if value:
            return value, f"zone_workflow_state.payload.{source}"
    return "", "zone_workflow_state.payload.workflow_stage"


def resolve_recovery_phase(
    row: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[str, str, Optional[str]]:
    raw_column_phase = row.get("workflow_phase_raw", row.get("workflow_phase"))
    raw_payload_phase = payload.get("workflow_phase")
    if is_valid_recovery_phase(raw_column_phase):
        return normalize_recovery_phase(raw_column_phase), "zone_workflow_state.workflow_phase", None
    if is_valid_recovery_phase(raw_payload_phase):
        return normalize_recovery_phase(raw_payload_phase), "zone_workflow_state.payload.workflow_phase", None
    if str(raw_column_phase or "").strip() or str(raw_payload_phase or "").strip():
        return "idle", "zone_workflow_state.workflow_phase", "invalid_phase"
    return "idle", "zone_workflow_state.workflow_phase", None


def resolve_workflow_for_recovery(
    phase: str,
    payload: Dict[str, Any],
    *,
    zone_id: Optional[int],
    logger: logging.Logger,
) -> Dict[str, Any]:
    payload_workflow, workflow_source = extract_payload_workflow_stage(payload)
    has_clean_timestamps = bool(
        str(payload.get("clean_fill_started_at") or "").strip()
        or str(payload.get("clean_fill_timeout_at") or "").strip()
    )
    has_solution_timestamps = bool(
        str(payload.get("solution_fill_started_at") or "").strip()
        or str(payload.get("solution_fill_timeout_at") or "").strip()
    )

    tank_filling_fallback = "solution_fill_check"
    if has_clean_timestamps and not has_solution_timestamps:
        tank_filling_fallback = "clean_fill_check"
    elif has_solution_timestamps:
        tank_filling_fallback = "solution_fill_check"

    fallback = {
        "tank_filling": tank_filling_fallback,
        "tank_recirc": "prepare_recirculation_check",
        "irrig_recirc": "irrigation_recovery_check",
    }
    allowed_workflows = {
        "tank_filling": {"clean_fill_check", "solution_fill_check"},
        "tank_recirc": {"prepare_recirculation_check"},
        "irrig_recirc": {"irrigation_recovery_check"},
    }

    mapped = payload_workflow
    if payload_workflow in {"startup", "cycle_start", "refill_check"}:
        mapped = fallback.get(phase, "")
    elif payload_workflow == "prepare_recirculation":
        mapped = "prepare_recirculation_check"
    elif payload_workflow == "irrigation_recovery":
        mapped = "irrigation_recovery_check"

    if mapped:
        allowed = allowed_workflows.get(phase)
        if allowed and mapped in allowed:
            if payload_workflow and payload_workflow != mapped:
                logger.info(
                    "Recovery workflow canonicalized from coarse stage: zone_id=%s phase=%s raw_workflow=%s canonical_workflow=%s",
                    zone_id,
                    phase,
                    payload_workflow,
                    mapped,
                )
                return {
                    "workflow": mapped,
                    "workflow_source": workflow_source,
                    "reason_code": "workflow_stage_canonicalized",
                    "fallback_from": payload_workflow,
                    "fallback_to": mapped,
                }
            return {
                "workflow": mapped,
                "workflow_source": workflow_source,
                "reason_code": "workflow_from_payload",
                "fallback_from": None,
                "fallback_to": None,
            }

        logger.warning(
            "Recovery workflow incompatible with phase, fallback will be used: zone_id=%s phase=%s payload_workflow=%s mapped_workflow=%s",
            zone_id,
            phase,
            payload_workflow or None,
            mapped,
        )

    phase_fallback = fallback.get(phase)
    if phase_fallback:
        if payload_workflow:
            logger.info(
                "Recovery workflow resolved via phase fallback: zone_id=%s phase=%s payload_workflow=%s fallback_workflow=%s",
                zone_id,
                phase,
                payload_workflow,
                phase_fallback,
            )
            return {
                "workflow": phase_fallback,
                "workflow_source": workflow_source,
                "reason_code": "workflow_phase_fallback",
                "fallback_from": mapped or payload_workflow,
                "fallback_to": phase_fallback,
            }
        return {
            "workflow": phase_fallback,
            "workflow_source": workflow_source,
            "reason_code": "workflow_missing_phase_fallback",
            "fallback_from": "missing_workflow",
            "fallback_to": phase_fallback,
        }

    if payload_workflow:
        logger.warning(
            "Recovery workflow unresolved for active phase: zone_id=%s phase=%s payload_workflow=%s",
            zone_id,
            phase,
            payload_workflow,
        )
    return {
        "workflow": None,
        "workflow_source": workflow_source,
        "reason_code": "workflow_unresolved",
        "fallback_from": None,
        "fallback_to": None,
    }


def extract_recovery_correlation_id(payload: Dict[str, Any]) -> Optional[str]:
    if isinstance(payload.get("recovery"), dict):
        nested = str(payload.get("recovery", {}).get("correlation_id") or "").strip()
        if nested:
            return nested
    correlation_id = str(payload.get("correlation_id") or "").strip()
    return correlation_id or None


def log_workflow_recovery_action(
    *,
    zone_id: Optional[int],
    workflow_phase_source: str,
    workflow_phase_normalized: str,
    workflow_selected: Optional[str],
    scheduler_task_id_previous: Optional[str],
    recovery_action: str,
    reason_code: str,
    state_age_sec: int,
    correlation_id: Optional[str],
    enqueue_id: Optional[str],
    level: int,
    error_type: Optional[str],
    error_message: Optional[str],
    logger: logging.Logger,
    get_trace_id_fn: Callable[[], Optional[str]],
) -> None:
    details: Dict[str, Any] = {
        "component": "workflow_state_recovery",
        "zone_id": zone_id,
        "workflow_phase_source": workflow_phase_source,
        "workflow_phase_normalized": workflow_phase_normalized,
        "workflow_selected": workflow_selected,
        "scheduler_task_id_previous": scheduler_task_id_previous,
        "recovery_action": recovery_action,
        "reason_code": reason_code,
        "state_age_sec": state_age_sec,
        "correlation_id": correlation_id,
        "enqueue_id": enqueue_id,
    }
    if error_type:
        details["error_type"] = error_type
    if error_message:
        details["error_message"] = error_message
    if level >= logging.ERROR:
        details["trace_id"] = get_trace_id_fn()
    logger.log(level, "Workflow state recovery action", extra=details)


async def send_workflow_recovery_alert_safe(
    *,
    error: Exception,
    code: str,
    alert_type: str,
    zone_id: Optional[int],
    details: Dict[str, Any],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> None:
    if zone_id is None:
        return
    try:
        await send_infra_exception_alert_fn(
            error=error,
            code=code,
            alert_type=alert_type,
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="workflow_state_recovery",
            error_type=type(error).__name__,
            details=details,
        )
    except Exception as alert_exc:
        logger.warning(
            "Failed to send workflow recovery infra alert: zone_id=%s code=%s error=%s",
            zone_id,
            code,
            alert_exc,
            exc_info=True,
        )


def coerce_utc_naive(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


__all__ = [
    "coerce_utc_naive",
    "extract_recovery_correlation_id",
    "log_workflow_recovery_action",
    "resolve_recovery_phase",
    "resolve_workflow_for_recovery",
    "send_workflow_recovery_alert_safe",
]
