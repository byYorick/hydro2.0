"""Correction loop state-machine helpers for observability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from common.db import create_zone_event

_ALLOWED_TRANSITIONS = {
    "sense": {"gate", "cooldown"},
    "gate": {"plan", "cooldown"},
    "plan": {"act", "cooldown"},
    "act": {"verify", "cooldown"},
    "verify": {"cooldown"},
    "cooldown": {"sense"},
}


@dataclass
class CorrectionStateMachine:
    zone_id: int
    metric: str
    state: str = "sense"
    correlation_id: Optional[str] = None

    async def transition(self, to_state: str, reason_code: str, details: Optional[Dict[str, Any]] = None) -> None:
        from_state = self.state
        normalized_to = str(to_state or "").strip().lower() or from_state
        payload: Dict[str, Any] = {
            "metric": self.metric,
            "from_state": from_state,
            "to_state": normalized_to,
            "reason_code": str(reason_code or "unspecified"),
        }
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        if isinstance(details, dict) and details:
            payload["details"] = details

        valid_next = _ALLOWED_TRANSITIONS.get(from_state, set())
        if normalized_to != from_state and normalized_to not in valid_next:
            payload["transition_policy"] = "out_of_order"
        else:
            payload["transition_policy"] = "normal"

        await create_zone_event(self.zone_id, "CORRECTION_STATE_TRANSITION", payload)
        self.state = normalized_to
