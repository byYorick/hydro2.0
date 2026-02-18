"""Runtime signal helpers for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict


CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
SendInfraAlertFn = Callable[..., Awaitable[bool]]
SendInfraResolvedAlertFn = Callable[..., Awaitable[bool]]


async def emit_zone_data_unavailable_signal(
    *,
    zone_id: int,
    error_streak: int,
    next_allowed_run_at: Any,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_alert_fn: SendInfraAlertFn,
    logger: Any,
) -> None:
    logger.warning(
        "Zone %s: Zone data unavailable, scheduling retry with backoff",
        zone_id,
        extra={
            "zone_id": zone_id,
            "error_streak": error_streak,
            "next_allowed_run_at": next_allowed_run_at.isoformat() if next_allowed_run_at else None,
        },
    )
    await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="ZONE_DATA_UNAVAILABLE",
        details={
            "reason": "db_circuit_breaker_open",
            "error_streak": error_streak,
            "next_allowed_run_at": next_allowed_run_at.isoformat() if next_allowed_run_at else None,
        },
        signal_name="zone_data_unavailable",
    )
    await send_infra_alert_fn(
        code="infra_zone_data_unavailable",
        alert_type="Zone Data Unavailable",
        message=f"Zone {zone_id} data unavailable: DB circuit breaker open",
        severity="error",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_data_loading",
        error_type="CircuitBreakerOpenError",
        details={
            "error_streak": error_streak,
            "next_allowed_run_at": next_allowed_run_at.isoformat() if next_allowed_run_at else None,
        },
    )


async def emit_degraded_mode_signal(
    *,
    zone_id: int,
    zone_state: Dict[str, Any],
    degraded_mode_threshold: int,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_alert_fn: SendInfraAlertFn,
    logger: Any,
) -> None:
    if zone_state.get("degraded_alert_active"):
        return
    error_streak = int(zone_state.get("error_streak", 0))
    logger.warning(
        "Zone %s: Entered DEGRADED mode (error_streak=%s, threshold=%s)",
        zone_id,
        error_streak,
        degraded_mode_threshold,
        extra={"zone_id": zone_id, "error_streak": error_streak},
    )
    event_created = await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="ZONE_DEGRADED_MODE",
        details={
            "error_streak": error_streak,
            "threshold": degraded_mode_threshold,
        },
        signal_name="zone_degraded_mode",
    )

    alert_sent = await send_infra_alert_fn(
        code="infra_zone_degraded_mode",
        alert_type="Zone Degraded Mode",
        message=f"Zone {zone_id} switched to degraded mode",
        severity="error",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_processing",
        error_type="DegradedMode",
        details={
            "error_streak": error_streak,
            "threshold": degraded_mode_threshold,
        },
    )
    if event_created or alert_sent:
        zone_state["degraded_alert_active"] = True
    else:
        logger.warning(
            "Zone %s: Degraded-mode signal not persisted (event+alert failed), will retry",
            zone_id,
            extra={"zone_id": zone_id, "error_streak": error_streak},
        )


async def emit_zone_recovered_signal(
    *,
    zone_id: int,
    previous_error_streak: int,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_resolved_alert_fn: SendInfraResolvedAlertFn,
    logger: Any,
) -> None:
    logger.info(
        "Zone %s: Recovered after %s consecutive errors",
        zone_id,
        previous_error_streak,
        extra={"zone_id": zone_id, "previous_error_streak": previous_error_streak},
    )
    await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="ZONE_RECOVERED",
        details={
            "previous_error_streak": previous_error_streak,
        },
        signal_name="zone_recovered",
    )
    for resolved_code in (
        "infra_zone_degraded_mode",
        "infra_zone_data_unavailable",
        "infra_zone_backoff_skip",
        "infra_zone_targets_missing",
    ):
        await send_infra_resolved_alert_fn(
            code=resolved_code,
            alert_type="Zone Recovered",
            message=f"Zone {zone_id} recovered after {previous_error_streak} consecutive errors",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_processing",
            details={"previous_error_streak": previous_error_streak},
        )


__all__ = [
    "emit_degraded_mode_signal",
    "emit_zone_data_unavailable_signal",
    "emit_zone_recovered_signal",
]
