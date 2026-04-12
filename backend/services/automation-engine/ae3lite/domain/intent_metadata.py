"""Канонические метаданные intent для создания задачи AE3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class IntentMetadata:
    """Извлечённые метаданные intent для создания задачи."""

    task_type: str
    current_stage: str
    workflow_phase: str
    topology: str
    intent_source: str
    intent_trigger: str
    intent_id: Optional[int]
    intent_meta: dict[str, Any]
    irrigation_mode: Optional[str] = None
    irrigation_requested_duration_sec: Optional[int] = None
