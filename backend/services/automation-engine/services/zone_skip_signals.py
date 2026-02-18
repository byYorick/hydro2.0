"""Zone-skip signal helpers for ZoneAutomationService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional


CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
SendInfraAlertFn = Callable[..., Awaitable[bool]]
UtcNowFn = Callable[[], datetime]
GetErrorStreakFn = Callable[[int], int]


async def emit_backoff_skip_signal(
    *,
    zone_id: int,
    zone_state: Dict[str, Any],
    utcnow_fn: UtcNowFn,
    get_error_streak_fn: GetErrorStreakFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_alert_fn: SendInfraAlertFn,
    skip_report_throttle_seconds: int,
    logger: Any,
) -> None:
    next_allowed = zone_state.get("next_allowed_run_at")
    if not next_allowed:
        return

    now = utcnow_fn()
    remaining_seconds = max(0, int((next_allowed - now).total_seconds()))
    last_reported_until = zone_state.get("last_backoff_reported_until")
    if (
        isinstance(last_reported_until, datetime)
        and last_reported_until == next_allowed
        and remaining_seconds > 0
        and remaining_seconds < skip_report_throttle_seconds
    ):
        logger.debug(
            "Zone %s: Backoff skip (throttled report), remaining=%ss",
            zone_id,
            remaining_seconds,
            extra={"zone_id": zone_id, "remaining_seconds": remaining_seconds},
        )
        return

    logger.warning(
        "Zone %s: Skipping due to backoff, remaining=%ss, next_allowed_run_at=%s",
        zone_id,
        remaining_seconds,
        next_allowed,
        extra={
            "zone_id": zone_id,
            "remaining_seconds": remaining_seconds,
            "next_allowed_run_at": next_allowed.isoformat(),
        },
    )

    event_created = await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="ZONE_SKIPPED_BACKOFF",
        details={
            "error_streak": get_error_streak_fn(zone_id),
            "next_allowed_run_at": next_allowed.isoformat(),
            "remaining_seconds": remaining_seconds,
        },
        signal_name="backoff_skip",
    )
    alert_sent = await send_infra_alert_fn(
        code="infra_zone_backoff_skip",
        alert_type="Zone Backoff Skip",
        message=f"Zone {zone_id} skipped due to backoff",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_processing",
        error_type="BackoffSkip",
        details={
            "error_streak": get_error_streak_fn(zone_id),
            "next_allowed_run_at": next_allowed.isoformat(),
            "remaining_seconds": remaining_seconds,
        },
    )
    if event_created or alert_sent:
        zone_state["last_backoff_reported_until"] = next_allowed
    else:
        logger.warning(
            "Zone %s: Backoff skip signal not persisted (event+alert failed), will retry",
            zone_id,
            extra={"zone_id": zone_id, "next_allowed_run_at": next_allowed.isoformat()},
        )


async def emit_missing_targets_signal(
    *,
    zone_id: int,
    grow_cycle: Optional[Dict[str, Any]],
    zone_state: Dict[str, Any],
    utcnow_fn: UtcNowFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_alert_fn: SendInfraAlertFn,
    skip_report_throttle_seconds: int,
    logger: Any,
) -> None:
    now = utcnow_fn()
    last_reported = zone_state.get("last_missing_targets_report_at")
    if isinstance(last_reported, datetime) and (now - last_reported).total_seconds() < skip_report_throttle_seconds:
        logger.debug(
            "Zone %s: Missing targets (throttled report)",
            zone_id,
            extra={"zone_id": zone_id},
        )
        return

    logger.warning(
        "Zone %s: Skipping processing because targets are missing or invalid",
        zone_id,
        extra={"zone_id": zone_id, "grow_cycle_present": bool(grow_cycle)},
    )

    event_created = await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="ZONE_SKIPPED_NO_TARGETS",
        details={
            "grow_cycle_present": bool(grow_cycle),
            "reason": "targets_missing_or_invalid",
        },
        signal_name="missing_targets",
    )
    alert_sent = await send_infra_alert_fn(
        code="infra_zone_targets_missing",
        alert_type="Zone Targets Missing",
        message=f"Zone {zone_id} skipped: targets are missing or invalid",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_processing",
        error_type="MissingTargets",
        details={"grow_cycle_present": bool(grow_cycle)},
    )
    if event_created or alert_sent:
        zone_state["last_missing_targets_report_at"] = now
    else:
        logger.warning(
            "Zone %s: Missing-targets signal not persisted (event+alert failed), will retry",
            zone_id,
            extra={"zone_id": zone_id},
        )


__all__ = [
    "emit_backoff_skip_signal",
    "emit_missing_targets_signal",
]
