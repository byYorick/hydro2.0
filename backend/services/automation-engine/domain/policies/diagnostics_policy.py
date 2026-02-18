"""Diagnostics-specific result shaping helpers."""

from __future__ import annotations

from typing import Any, Dict


def build_diagnostics_invalid_payload_result(
    *,
    reason_code: str,
    reason: str,
    payload_contract_version: str,
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "diagnostics_invalid_payload",
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": False,
        "decision": "fail",
        "reason_code": reason_code,
        "reason": reason,
        "error": reason_code,
        "error_code": reason_code,
        "payload_contract_version": payload_contract_version,
    }


__all__ = ["build_diagnostics_invalid_payload_result"]
