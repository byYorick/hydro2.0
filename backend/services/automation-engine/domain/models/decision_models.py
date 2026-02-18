"""Decision models for scheduler task execution policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DecisionOutcome:
    action_required: bool
    decision: str
    reason_code: str
    reason: str
    details: Optional[Dict[str, Any]] = None
