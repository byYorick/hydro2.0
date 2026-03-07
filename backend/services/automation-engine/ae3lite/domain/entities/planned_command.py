"""Planned command entity for AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class PlannedCommand:
    """Resolved command step ready for execution/persistence."""

    step_no: int
    node_uid: str
    channel: str
    payload: Mapping[str, Any]
    external_id: Optional[str] = None
    terminal_status: Optional[str] = None
