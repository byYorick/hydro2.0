"""Shared models for AE2-Lite runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ZoneIntent:
    id: int
    zone_id: int
    status: str
    intent_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    retry_count: int = 0
    max_retries: int = 3
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ZoneRuntimeState:
    zone_id: int
    workflow_phase: str = "idle"
    control_mode: str = "auto"
    payload: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[datetime] = None


__all__ = ["ZoneIntent", "ZoneRuntimeState"]
