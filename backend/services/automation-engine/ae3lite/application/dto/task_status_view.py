"""Каноническое представление статуса задачи AE3-Lite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TaskStatusView:
    """Минимальный канонический payload статуса задачи для AE3-зон."""

    task_id: int
    zone_id: int
    task_type: str
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
