"""Helpers for scheduler task execution context."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_task_context(task_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    payload = task_context if isinstance(task_context, dict) else {}
    return {
        "task_id": str(payload.get("task_id") or ""),
        "correlation_id": str(payload.get("correlation_id") or ""),
        "scheduled_for": payload.get("scheduled_for"),
        "event_seq": 0,
    }


__all__ = ["build_task_context"]
