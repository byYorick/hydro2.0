"""Runtime backoff/degraded-state helpers for ZoneAutomationService."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Optional


def should_process_zone(
    *,
    zone_id: int,
    next_allowed_run_at: Optional[Any],
    utcnow_fn: Callable[[], Any],
    logger: Any,
) -> bool:
    if next_allowed_run_at is None:
        return True

    now = utcnow_fn()
    if now < next_allowed_run_at:
        logger.debug(
            "Zone %s: Skipping due to backoff (next allowed at %s, now %s)",
            zone_id,
            next_allowed_run_at,
            now,
            extra={"zone_id": zone_id, "next_allowed_run_at": next_allowed_run_at.isoformat()},
        )
        return False

    return True


def is_degraded_mode(*, error_streak: int, degraded_mode_threshold: int) -> bool:
    return int(error_streak) >= int(degraded_mode_threshold)


def calculate_backoff_seconds(
    *,
    error_streak: int,
    initial_backoff_seconds: int,
    backoff_multiplier: int,
    max_backoff_seconds: int,
) -> int:
    if error_streak <= 0:
        return 0

    backoff = initial_backoff_seconds * (backoff_multiplier ** (error_streak - 1))
    return min(int(backoff), max_backoff_seconds)


def record_zone_error(
    *,
    zone_id: int,
    get_zone_state_fn: Callable[[int], dict],
    calculate_backoff_seconds_fn: Callable[[int], int],
    utcnow_fn: Callable[[], Any],
    logger: Any,
) -> None:
    state = get_zone_state_fn(zone_id)
    state["error_streak"] += 1

    backoff_seconds = calculate_backoff_seconds_fn(state["error_streak"])
    state["next_allowed_run_at"] = utcnow_fn() + timedelta(seconds=backoff_seconds)

    logger.warning(
        "Zone %s: Error recorded. error_streak=%s, backoff=%ss, next_allowed_run_at=%s",
        zone_id,
        state["error_streak"],
        backoff_seconds,
        state["next_allowed_run_at"],
        extra={
            "zone_id": zone_id,
            "error_streak": state["error_streak"],
            "backoff_seconds": backoff_seconds,
            "next_allowed_run_at": state["next_allowed_run_at"].isoformat(),
        },
    )


def reset_zone_error_streak(
    *,
    zone_id: int,
    get_zone_state_fn: Callable[[int], dict],
    logger: Any,
) -> int:
    state = get_zone_state_fn(zone_id)
    previous_error_streak = int(state["error_streak"])
    if state["error_streak"] > 0:
        logger.info(
            "Zone %s: Resetting error_streak (was %s) after successful cycle",
            zone_id,
            state["error_streak"],
            extra={"zone_id": zone_id, "previous_error_streak": state["error_streak"]},
        )

    state["error_streak"] = 0
    state["next_allowed_run_at"] = None
    state["last_backoff_reported_until"] = None
    state["degraded_alert_active"] = False
    return previous_error_streak


__all__ = [
    "calculate_backoff_seconds",
    "is_degraded_mode",
    "record_zone_error",
    "reset_zone_error_streak",
    "should_process_zone",
]
