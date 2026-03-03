"""Result builders for two-tank workflow responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def two_tank_error(
    *,
    mode: str,
    workflow: str,
    reason_code: str,
    reason: str,
    error_code: str,
    error: Optional[str] = None,
    commands_total: int = 0,
    commands_failed: int = 0,
    command_statuses: Optional[List[Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": False,
        "task_type": "diagnostics",
        "mode": mode,
        "workflow": workflow,
        "commands_total": commands_total,
        "commands_failed": commands_failed,
        "command_statuses": command_statuses or [],
        "action_required": True,
        "decision": "run",
        "reason_code": reason_code,
        "reason": reason,
        "error": error or error_code,
        "error_code": error_code,
    }
    result.update(extra)
    return result


def two_tank_success(
    *,
    mode: str,
    workflow: str,
    reason_code: str,
    reason: str,
    action_required: bool,
    decision: str,
    commands_total: int = 0,
    commands_failed: int = 0,
    command_statuses: Optional[List[Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": True,
        "task_type": "diagnostics",
        "mode": mode,
        "workflow": workflow,
        "commands_total": commands_total,
        "commands_failed": commands_failed,
        "command_statuses": command_statuses or [],
        "action_required": action_required,
        "decision": decision,
        "reason_code": reason_code,
        "reason": reason,
    }
    result.update(extra)
    return result


__all__ = ["two_tank_error", "two_tank_success"]
