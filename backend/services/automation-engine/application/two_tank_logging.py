"""Helpers for two-tank safety guard logging."""

from __future__ import annotations

import logging
from typing import Any, Dict


def log_two_tank_safety_guard(
    *,
    logger_obj: logging.Logger,
    zone_id: int,
    context: Dict[str, Any],
    phase: str,
    stop_result: Dict[str, Any],
    feature_flag_state: bool,
    level: int = logging.WARNING,
) -> None:
    logger_obj.log(
        level,
        "Two-tank safety guard decision",
        extra={
            "zone_id": zone_id,
            "task_id": str(context.get("task_id") or ""),
            "correlation_id": str(context.get("correlation_id") or ""),
            "phase": phase,
            "stop_result": stop_result,
            "feature_flag_state": feature_flag_state,
        },
    )


__all__ = ["log_two_tank_safety_guard"]
