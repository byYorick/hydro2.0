"""Outcome shaping helpers for scheduler task execution."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def build_decision_retry_correlation_id(
    *,
    zone_id: int,
    task_type: str,
    parent_correlation_id: Optional[str],
    retry_attempt: Optional[int],
    unique_suffix_factory: Callable[[], str],
) -> str:
    retry_marker = f"retry{max(0, int(retry_attempt))}" if retry_attempt is not None else "retry"
    unique_suffix = unique_suffix_factory()
    parent = str(parent_correlation_id or "").strip()
    if parent:
        return f"{parent}:{retry_marker}:{unique_suffix}"
    return f"ae:retry:{zone_id}:{task_type}:{retry_marker}:{unique_suffix}"


def extract_two_tank_chemistry_orchestration(payload: Dict[str, Any]) -> Dict[str, Any]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    raw = execution.get("chemistry_orchestration")
    if isinstance(raw, dict) and raw:
        return raw
    return {
        "irrigation_online_sequence": ["ec", "ph"],
        "prepare_sequence": ["npk", "ph"],
        "irrigation_recovery_sequence": ["calcium", "magnesium", "micro", "ph"],
    }


__all__ = [
    "build_decision_retry_correlation_id",
    "extract_two_tank_chemistry_orchestration",
]
