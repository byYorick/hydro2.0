"""Helpers for scheduler task event payload assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


def build_task_event_payload(
    *,
    zone_id: int,
    task_type: str,
    context: Dict[str, Any],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    event_id_factory: Callable[[], str],
    occurred_at_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc).replace(tzinfo=None),
) -> Dict[str, Any]:
    context["event_seq"] = int(context.get("event_seq") or 0) + 1

    event_payload: Dict[str, Any] = {
        "event_id": event_id_factory(),
        "event_seq": context["event_seq"],
        "event_type": event_type,
        "occurred_at": occurred_at_factory().isoformat(),
        "zone_id": zone_id,
        "task_type": task_type,
        "task_id": context.get("task_id") or None,
        "correlation_id": context.get("correlation_id") or None,
    }
    if isinstance(payload, dict):
        event_payload.update(payload)
    return event_payload


__all__ = ["build_task_event_payload"]
