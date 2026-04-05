"""Сущность planned-команды для AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class PlannedCommand:
    """Разрешённый шаг команды, готовый к выполнению и сохранению."""

    step_no: int
    node_uid: str
    channel: str
    payload: Mapping[str, Any]
    external_id: Optional[str] = None
    terminal_status: Optional[str] = None
