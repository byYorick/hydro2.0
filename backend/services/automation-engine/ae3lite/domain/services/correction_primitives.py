"""Correction domain policy: primitives."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Mapping, Optional


def _resolve_target_tolerance_bounds(
    *,
    target: float,
    tolerance_pct: float,
) -> tuple[float, float]:
    tol = abs(float(target)) * (float(tolerance_pct) / 100.0)
    return float(target) - tol, float(target) + tol


def _phase_mapping(raw: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return raw if isinstance(raw, Mapping) else {}


def _pid_entry(pid_state: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    entry = pid_state.get(kind)
    return entry if isinstance(entry, Mapping) else {}


def _controller_cfg(correction_config: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    controllers = correction_config.get("controllers")
    controller = controllers.get(kind) if isinstance(controllers, Mapping) else None
    if isinstance(controller, Mapping):
        return controller
    return {}


def _strip_last_dose_at(pid_updates: dict[str, Any], key: str) -> None:
    """Drop last_dose_at from a pending pid_state update for the given PID kind.

    Kept for backwards compatibility with tests and legacy call sites. Planning
    no longer stamps ``last_dose_at``; the correction handler writes it only
    after a terminal ``DONE`` dose command.
    """
    entry = pid_updates.get(key)
    if not isinstance(entry, Mapping) or "last_dose_at" not in entry:
        return
    pid_updates[key] = {k: v for k, v in entry.items() if k != "last_dose_at"}


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _positive_float(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_int(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _non_negative_float(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _min_positive(*values: Optional[int]) -> Optional[int]:
    candidates = [int(value) for value in values if value is not None and int(value) > 0]
    return min(candidates) if candidates else None


def _coerce_ratio(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return max(0.0, min(1.0, value))
