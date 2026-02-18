"""Two-tank helper policy for workflow payload/result shaping."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


def build_two_tank_check_payload(
    *,
    payload: Dict[str, Any],
    workflow: str,
    phase_started_at: datetime,
    phase_timeout_at: datetime,
    phase_cycle: Optional[int] = None,
) -> Dict[str, Any]:
    next_payload = dict(payload)
    next_payload["workflow"] = workflow
    if workflow == "clean_fill_check":
        next_payload["clean_fill_started_at"] = phase_started_at.isoformat()
        next_payload["clean_fill_timeout_at"] = phase_timeout_at.isoformat()
        if phase_cycle is not None:
            next_payload["clean_fill_cycle"] = max(1, int(phase_cycle))
    elif workflow == "solution_fill_check":
        next_payload["solution_fill_started_at"] = phase_started_at.isoformat()
        next_payload["solution_fill_timeout_at"] = phase_timeout_at.isoformat()
    elif workflow == "prepare_recirculation_check":
        next_payload["prepare_recirculation_started_at"] = phase_started_at.isoformat()
        next_payload["prepare_recirculation_timeout_at"] = phase_timeout_at.isoformat()
    elif workflow == "irrigation_recovery_check":
        next_payload["irrigation_recovery_started_at"] = phase_started_at.isoformat()
        next_payload["irrigation_recovery_timeout_at"] = phase_timeout_at.isoformat()
        if phase_cycle is not None:
            next_payload["irrigation_recovery_attempt"] = max(1, int(phase_cycle))
    return next_payload


def build_two_tank_stop_not_confirmed_result(
    *,
    workflow: str,
    mode: str,
    reason: str,
    stop_result: Dict[str, Any],
    reason_code: str,
    feature_flag_state: bool,
    fallback_error_code: str,
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": mode,
        "workflow": workflow,
        "commands_total": stop_result.get("commands_total", 0),
        "commands_failed": stop_result.get("commands_failed", 1),
        "command_statuses": stop_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_code,
        "reason": reason,
        "error": str(stop_result.get("error") or fallback_error_code),
        "error_code": str(stop_result.get("error_code") or fallback_error_code),
        "stop_result": stop_result,
        "feature_flag_state": feature_flag_state,
    }


__all__ = [
    "build_two_tank_check_payload",
    "build_two_tank_stop_not_confirmed_result",
]
