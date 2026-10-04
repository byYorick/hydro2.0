"""Persisted overall deadline helpers for AE3 zone tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def overall_deadline_exceeded(*, task: Any, now: datetime) -> bool:
    deadline = getattr(task, "overall_deadline_at", None)
    if not isinstance(deadline, datetime):
        return False
    return _utc_naive(now) >= _utc_naive(deadline)


def overall_deadline_remaining_sec(*, task: Any, now: datetime) -> float | None:
    deadline = getattr(task, "overall_deadline_at", None)
    if not isinstance(deadline, datetime):
        return None
    return (_utc_naive(deadline) - _utc_naive(now)).total_seconds()


def ensure_overall_deadline_active(*, task: Any, now: datetime) -> None:
    if not overall_deadline_exceeded(task=task, now=now):
        return
    deadline = getattr(task, "overall_deadline_at", None)
    task_id = int(getattr(task, "id", 0) or 0)
    raise TaskExecutionError(
        ErrorCodes.AE3_TASK_OVERALL_DEADLINE_EXCEEDED,
        f"Общий deadline задачи {task_id} истёк: overall_deadline_at={deadline!s}",
    )


__all__ = [
    "ensure_overall_deadline_active",
    "overall_deadline_exceeded",
    "overall_deadline_remaining_sec",
]
