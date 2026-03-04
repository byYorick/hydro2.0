"""Workflow phase/stage mapping policy helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set


WORKFLOW_PHASE_IDLE = "idle"
WORKFLOW_PHASE_TANK_FILLING = "tank_filling"
WORKFLOW_PHASE_TANK_RECIRC = "tank_recirc"
WORKFLOW_PHASE_READY = "ready"
WORKFLOW_PHASE_IRRIGATING = "irrigating"
WORKFLOW_PHASE_IRRIG_RECIRC = "irrig_recirc"

WORKFLOW_PHASE_VALUES = {
    WORKFLOW_PHASE_IDLE,
    WORKFLOW_PHASE_TANK_FILLING,
    WORKFLOW_PHASE_TANK_RECIRC,
    WORKFLOW_PHASE_READY,
    WORKFLOW_PHASE_IRRIGATING,
    WORKFLOW_PHASE_IRRIG_RECIRC,
}

WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW = {
    "startup": WORKFLOW_PHASE_TANK_FILLING,
    "clean_fill_check": WORKFLOW_PHASE_TANK_FILLING,
    "solution_fill_check": WORKFLOW_PHASE_TANK_FILLING,
    "prepare_recirculation": WORKFLOW_PHASE_TANK_RECIRC,
    "prepare_recirculation_check": WORKFLOW_PHASE_TANK_RECIRC,
    "irrigation_recovery": WORKFLOW_PHASE_IRRIG_RECIRC,
    "irrigation_recovery_check": WORKFLOW_PHASE_IRRIG_RECIRC,
}

WORKFLOW_PHASE_READY_MODES = {
    "two_tank_startup_completed",
    "two_tank_prepare_recirculation_completed",
    "three_tank_startup_ready",
    "cycle_start_ready",
}

WORKFLOW_PHASE_ACTIVE_MODES = {
    "two_tank_clean_fill_in_progress": WORKFLOW_PHASE_TANK_FILLING,
    "two_tank_solution_fill_in_progress": WORKFLOW_PHASE_TANK_FILLING,
    "two_tank_prepare_recirculation_in_progress": WORKFLOW_PHASE_TANK_RECIRC,
    "two_tank_irrigation_recovery_in_progress": WORKFLOW_PHASE_IRRIG_RECIRC,
    "cycle_start_refill_in_progress": WORKFLOW_PHASE_TANK_FILLING,
}

WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS = {
    "irr_state_mismatch",
    "safety_blocked",
}

WORKFLOW_PHASE_IRRIGATING_MODES = {
    "two_tank_irrigation_recovery_completed",
    "two_tank_irrigation_recovery_degraded",
    "two_tank_irrigation_recovery_attempts_exhausted_continue_irrigation",
}

WORKFLOW_STAGE_BY_DIAGNOSTICS_MODE = {
    "two_tank_clean_fill_in_progress": "clean_fill_check",
    "two_tank_solution_fill_in_progress": "solution_fill_check",
    "two_tank_prepare_recirculation_in_progress": "prepare_recirculation_check",
    "two_tank_irrigation_recovery_in_progress": "irrigation_recovery_check",
}

WORKFLOW_STAGES_CANONICAL = {
    "startup",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation_check",
    "irrigation_recovery",
    "irrigation_recovery_check",
}

WORKFLOW_STAGE_TO_PHASE = {
    "startup": WORKFLOW_PHASE_TANK_FILLING,
    "clean_fill_check": WORKFLOW_PHASE_TANK_FILLING,
    "solution_fill_check": WORKFLOW_PHASE_TANK_FILLING,
    "prepare_recirculation_check": WORKFLOW_PHASE_TANK_RECIRC,
    "irrigation_recovery": WORKFLOW_PHASE_IRRIG_RECIRC,
    "irrigation_recovery_check": WORKFLOW_PHASE_IRRIG_RECIRC,
}

WORKFLOW_PHASE_EVENT_TYPE = "WORKFLOW_PHASE_UPDATED"

WORKFLOW_PHASE_VALID_TRANSITIONS: Dict[str, frozenset[str]] = {
    WORKFLOW_PHASE_IDLE: frozenset(
        {
            WORKFLOW_PHASE_TANK_FILLING,
        }
    ),
    WORKFLOW_PHASE_TANK_FILLING: frozenset(
        {
            WORKFLOW_PHASE_TANK_RECIRC,
            WORKFLOW_PHASE_READY,
            WORKFLOW_PHASE_IDLE,
        }
    ),
    WORKFLOW_PHASE_TANK_RECIRC: frozenset(
        {
            WORKFLOW_PHASE_READY,
            WORKFLOW_PHASE_IDLE,
        }
    ),
    WORKFLOW_PHASE_READY: frozenset(
        {
            WORKFLOW_PHASE_IRRIGATING,
            WORKFLOW_PHASE_IDLE,
        }
    ),
    WORKFLOW_PHASE_IRRIGATING: frozenset(
        {
            WORKFLOW_PHASE_IRRIG_RECIRC,
            WORKFLOW_PHASE_IDLE,
        }
    ),
    WORKFLOW_PHASE_IRRIG_RECIRC: frozenset(
        {
            WORKFLOW_PHASE_IRRIGATING,
            WORKFLOW_PHASE_IDLE,
        }
    ),
}


def is_valid_phase_transition(from_phase: str, to_phase: str) -> bool:
    """Return True when target phase is allowed from the source phase."""
    allowed = WORKFLOW_PHASE_VALID_TRANSITIONS.get(
        normalize_workflow_phase(from_phase),
        frozenset(),
    )
    return normalize_workflow_phase(to_phase) in allowed


def validate_phase_transition(
    from_phase: str,
    to_phase: str,
    *,
    zone_id: int,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """Soft FSM enforcement.

    Invalid transitions are logged as warnings and should be ignored by caller.
    """
    normalized_from = normalize_workflow_phase(from_phase)
    normalized_to = normalize_workflow_phase(to_phase)
    if is_valid_phase_transition(normalized_from, normalized_to):
        return True
    if logger is not None:
        logger.warning(
            "Zone %s: invalid workflow phase transition %s -> %s (ignored)",
            zone_id,
            normalized_from,
            normalized_to,
        )
    return False


def normalize_workflow_phase(raw_phase: Any, *, allowed_values: Optional[Set[str]] = None) -> str:
    allowed = allowed_values or WORKFLOW_PHASE_VALUES
    value = str(raw_phase or "").strip().lower()
    return value if value in allowed else WORKFLOW_PHASE_IDLE


def normalize_workflow_stage(raw_stage: Any, *, allowed_values: Optional[Set[str]] = None) -> str:
    allowed = allowed_values or WORKFLOW_STAGES_CANONICAL
    stage = str(raw_stage or "").strip().lower()
    return stage if stage in allowed else ""


def extract_workflow_hint(payload: Dict[str, Any], result: Dict[str, Any]) -> str:
    return str(result.get("workflow") or payload.get("workflow") or "").strip().lower()


def derive_workflow_phase(
    *,
    task_type: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    normalized_task_type = str(task_type or "").strip().lower()
    mode = str(result.get("mode") or "").strip().lower()
    workflow = extract_workflow_hint(payload, result)
    success = bool(result.get("success"))
    decision = str(result.get("decision") or "").strip().lower()
    action_required = bool(result.get("action_required"))
    reason_code = str(result.get("reason_code") or "").strip().lower()

    if normalized_task_type == "diagnostics":
        if not success:
            if bool(result.get("irr_state_retry")):
                if logger is not None:
                    logger.info(
                        "Diagnostics workflow phase unchanged: transient irr_state retry keeps active phase",
                        extra={
                            "task_type": normalized_task_type,
                            "mode": mode or None,
                            "workflow": workflow or None,
                            "decision": decision or None,
                            "reason_code": reason_code or None,
                            "action_required": action_required,
                            "success": success,
                        },
                )
                return None
            if reason_code == "safety_blocked" and workflow in {
                "irrigation_recovery",
                "irrigation_recovery_check",
            }:
                if logger is not None:
                    logger.info(
                        "Diagnostics recovery safety block resets workflow phase to idle",
                        extra={
                            "task_type": normalized_task_type,
                            "mode": mode or None,
                            "workflow": workflow or None,
                            "decision": decision or None,
                            "reason_code": reason_code or None,
                            "action_required": action_required,
                            "success": success,
                        },
                    )
                return WORKFLOW_PHASE_IDLE
            if reason_code in WORKFLOW_PHASE_BLOCKING_FAILURE_REASONS:
                blocked_phase = WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW.get(workflow)
                if blocked_phase:
                    if logger is not None:
                        logger.warning(
                            "Diagnostics workflow failure keeps blocking phase (manual intervention required)",
                            extra={
                                "task_type": normalized_task_type,
                                "mode": mode or None,
                                "workflow": workflow or None,
                                "decision": decision or None,
                                "reason_code": reason_code or None,
                                "action_required": action_required,
                                "success": success,
                                "blocked_phase": blocked_phase,
                            },
                        )
                    return blocked_phase
            if logger is not None:
                logger.info(
                    "Diagnostics workflow phase fallback to idle after terminal failure",
                    extra={
                        "task_type": normalized_task_type,
                        "mode": mode or None,
                        "workflow": workflow or None,
                        "decision": decision or None,
                        "reason_code": reason_code or None,
                        "action_required": action_required,
                        "success": success,
                    },
                )
            return WORKFLOW_PHASE_IDLE
        if mode in WORKFLOW_PHASE_READY_MODES:
            return WORKFLOW_PHASE_READY
        if mode in WORKFLOW_PHASE_IRRIGATING_MODES:
            return WORKFLOW_PHASE_IRRIGATING
        if mode in WORKFLOW_PHASE_ACTIVE_MODES:
            return WORKFLOW_PHASE_ACTIVE_MODES[mode]
        if workflow in WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW:
            return WORKFLOW_PHASE_BY_DIAGNOSTICS_WORKFLOW[workflow]
        if logger is not None:
            logger.info(
                "Diagnostics workflow phase unchanged: no explicit phase mapping for mode/workflow",
                extra={
                    "task_type": normalized_task_type,
                    "mode": mode or None,
                    "workflow": workflow or None,
                    "decision": decision or None,
                    "reason_code": reason_code or None,
                    "action_required": action_required,
                    "success": success,
                },
            )
        return None

    if normalized_task_type == "irrigation":
        if "irrigation_recovery" in workflow or "irrigation_recovery" in mode:
            return WORKFLOW_PHASE_IRRIG_RECIRC
        if success and action_required and decision == "run":
            return WORKFLOW_PHASE_IRRIGATING
        if success and (decision == "skip" or not action_required):
            if logger is not None:
                logger.info(
                    "Irrigation workflow phase unchanged: non-running successful outcome",
                    extra={
                        "task_type": normalized_task_type,
                        "mode": mode or None,
                        "workflow": workflow or None,
                        "decision": decision or None,
                        "reason_code": reason_code or None,
                        "action_required": action_required,
                        "success": success,
                    },
                )
            return None
        return WORKFLOW_PHASE_IDLE

    return None


def build_workflow_state_payload(
    *,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    workflow_phase: str,
    workflow_stage: str,
) -> Dict[str, Any]:
    next_check = result.get("next_check") if isinstance(result.get("next_check"), dict) else None
    continuation_payload: Dict[str, Any] = {}
    if next_check:
        details = next_check.get("details") if isinstance(next_check.get("details"), dict) else None
        if details and isinstance(details.get("payload"), dict):
            continuation_payload = dict(details.get("payload"))

    # Prefer continuation payload when next_check is already built.
    # This keeps attempt/timing markers consistent for workflow-state recovery.
    state_payload = continuation_payload or dict(payload)
    if workflow_stage:
        state_payload["workflow"] = workflow_stage
        state_payload["workflow_stage"] = workflow_stage
    else:
        state_payload.pop("workflow_stage", None)
    state_payload["workflow_phase"] = workflow_phase
    state_payload["workflow_mode"] = str(result.get("mode") or "")
    state_payload["workflow_reason_code"] = str(result.get("reason_code") or "")
    if next_check:
        state_payload["next_check"] = next_check

    carry_from_result = (
        "refill_attempt",
        "refill_started_at",
        "refill_timeout_at",
        "clean_fill_started_at",
        "clean_fill_timeout_at",
        "clean_fill_retry_cycle",
        "solution_fill_started_at",
        "solution_fill_timeout_at",
        "prepare_recirculation_started_at",
        "prepare_recirculation_timeout_at",
        "irrigation_recovery_attempt",
        "irrigation_recovery_started_at",
        "irrigation_recovery_timeout_at",
    )
    for key in carry_from_result:
        value = result.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        state_payload[key] = value
    return state_payload


def resolve_workflow_stage_for_state_sync(
    *,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    workflow_phase: str,
) -> str:
    mode = str(result.get("mode") or "").strip().lower()
    if mode in WORKFLOW_STAGE_BY_DIAGNOSTICS_MODE:
        return WORKFLOW_STAGE_BY_DIAGNOSTICS_MODE[mode]

    workflow_hint = extract_workflow_hint(payload, result)
    if workflow_hint == "prepare_recirculation":
        return "prepare_recirculation_check"
    if workflow_hint == "irrigation_recovery":
        return "irrigation_recovery_check"
    if workflow_hint == "startup":
        has_clean_timestamps = bool(
            str(payload.get("clean_fill_started_at") or result.get("clean_fill_started_at") or "").strip()
            or str(payload.get("clean_fill_timeout_at") or result.get("clean_fill_timeout_at") or "").strip()
        )
        has_solution_timestamps = bool(
            str(payload.get("solution_fill_started_at") or result.get("solution_fill_started_at") or "").strip()
            or str(payload.get("solution_fill_timeout_at") or result.get("solution_fill_timeout_at") or "").strip()
        )
        if has_clean_timestamps and not has_solution_timestamps:
            return "clean_fill_check"
        if has_solution_timestamps:
            return "solution_fill_check"
        if workflow_phase == WORKFLOW_PHASE_TANK_FILLING:
            return "solution_fill_check"

    if workflow_hint in WORKFLOW_STAGES_CANONICAL:
        return workflow_hint
    return ""


__all__ = [
    "WORKFLOW_PHASE_EVENT_TYPE",
    "WORKFLOW_PHASE_IDLE",
    "WORKFLOW_PHASE_IRRIGATING",
    "WORKFLOW_PHASE_IRRIG_RECIRC",
    "WORKFLOW_PHASE_READY",
    "WORKFLOW_PHASE_TANK_FILLING",
    "WORKFLOW_PHASE_TANK_RECIRC",
    "WORKFLOW_PHASE_VALID_TRANSITIONS",
    "WORKFLOW_PHASE_VALUES",
    "WORKFLOW_STAGE_TO_PHASE",
    "WORKFLOW_STAGES_CANONICAL",
    "build_workflow_state_payload",
    "derive_workflow_phase",
    "extract_workflow_hint",
    "is_valid_phase_transition",
    "normalize_workflow_phase",
    "normalize_workflow_stage",
    "resolve_workflow_stage_for_state_sync",
    "validate_phase_transition",
]
