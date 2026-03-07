"""Canonical AE3-Lite task status view."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TaskStatusView:
    """Minimal canonical task status payload for AE3 zones."""

    task_id: int
    zone_id: int
    task_type: str
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
