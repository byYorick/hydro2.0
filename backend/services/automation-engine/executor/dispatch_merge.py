"""Helpers for merging multiple command-dispatch results."""

from __future__ import annotations

from typing import Any, Dict


def merge_command_dispatch_results(
    *results: Dict[str, Any],
    err_two_tank_command_failed: str,
) -> Dict[str, Any]:
    merged = {
        "success": True,
        "commands_total": 0,
        "commands_failed": 0,
        "commands_submitted": 0,
        "commands_effect_confirmed": 0,
        "command_statuses": [],
    }
    first_error_code = None
    first_error = None

    for item in results:
        if not isinstance(item, dict):
            continue
        merged["commands_total"] += int(item.get("commands_total") or 0)
        merged["commands_failed"] += int(item.get("commands_failed") or 0)
        merged["commands_submitted"] += int(item.get("commands_submitted") or 0)
        merged["commands_effect_confirmed"] += int(item.get("commands_effect_confirmed") or 0)
        merged["command_statuses"].extend(item.get("command_statuses") or [])
        if not item.get("success") and first_error_code is None:
            first_error_code = str(item.get("error_code") or err_two_tank_command_failed)
            first_error = str(item.get("error") or err_two_tank_command_failed)

    merged["success"] = merged["commands_failed"] == 0
    if not merged["success"]:
        merged["error_code"] = first_error_code or err_two_tank_command_failed
        merged["error"] = first_error or err_two_tank_command_failed
    return merged


__all__ = ["merge_command_dispatch_results"]
