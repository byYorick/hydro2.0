"""Helpers for decision detail shaping."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from domain.models.decision_models import DecisionOutcome


def to_optional_float(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def with_decision_details(decision: DecisionOutcome, patch: Dict[str, Any]) -> DecisionOutcome:
    merged: Dict[str, Any] = {}
    if isinstance(decision.details, dict):
        merged.update(decision.details)
    for key, value in patch.items():
        if key == "safety_flags":
            existing = merged.get("safety_flags")
            flags: List[str] = []
            if isinstance(existing, Sequence) and not isinstance(existing, (str, bytes, bytearray)):
                for item in existing:
                    normalized = str(item).strip()
                    if normalized and normalized not in flags:
                        flags.append(normalized)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                for item in value:
                    normalized = str(item).strip()
                    if normalized and normalized not in flags:
                        flags.append(normalized)
            merged["safety_flags"] = flags
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged.get(key) if isinstance(merged.get(key), dict) else {})
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return DecisionOutcome(
        action_required=decision.action_required,
        decision=decision.decision,
        reason_code=decision.reason_code,
        reason=decision.reason,
        details=merged or None,
    )


__all__ = ["to_optional_float", "with_decision_details"]
