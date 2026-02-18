"""Housekeeping helpers for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from services.resilience_contract import (
    INFRA_PID_CONFIG_UPDATE_CHECK_FAILED,
    INFRA_ZONE_DELETION_CHECK_FAILED,
)


async def update_zone_health(
    *,
    zone_id: int,
    calculate_zone_health_fn: Callable[[int], Awaitable[Any]],
    update_zone_health_in_db_fn: Callable[[int, Any], Awaitable[Any]],
) -> None:
    health_data = await calculate_zone_health_fn(zone_id)
    await update_zone_health_in_db_fn(zone_id, health_data)


async def check_zone_deletion(
    *,
    zone_id: int,
    fetch_fn: Callable[..., Awaitable[Any]],
    invalidate_cache_fn: Callable[..., Any],
    ph_controller: Any,
    ec_controller: Any,
    logger: Any,
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
) -> None:
    try:
        rows = await fetch_fn(
            """
            SELECT id
            FROM zones
            WHERE id = $1
            """,
            zone_id,
        )

        if not rows:
            if zone_id in ph_controller._pid_by_zone:
                del ph_controller._pid_by_zone[zone_id]
                ph_controller._last_pid_tick.pop(zone_id, None)
                logger.info("Cleared PH PID instance for deleted zone %s", zone_id)
            if zone_id in ec_controller._pid_by_zone:
                del ec_controller._pid_by_zone[zone_id]
                ec_controller._last_pid_tick.pop(zone_id, None)
                logger.info("Cleared EC PID instance for deleted zone %s", zone_id)
            invalidate_cache_fn(zone_id)
            logger.info("Cleared PID cache for deleted zone %s", zone_id)
    except Exception as e:
        logger.warning("Failed to check zone deletion for zone %s: %s", zone_id, e, exc_info=True)
        await send_infra_exception_alert_fn(
            error=e,
            code=INFRA_ZONE_DELETION_CHECK_FAILED,
            alert_type="Zone Deletion Check Failed",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_housekeeping",
            details={"check": "zone_deletion"},
        )


async def check_pid_config_updates(
    *,
    zone_id: int,
    fetch_fn: Callable[..., Awaitable[Any]],
    invalidate_cache_fn: Callable[..., Any],
    ph_controller: Any,
    ec_controller: Any,
    logger: Any,
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
) -> None:
    try:
        rows = await fetch_fn(
            """
            SELECT details
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'PID_CONFIG_UPDATED'
              AND created_at > NOW() - INTERVAL '2 minutes'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            zone_id,
        )

        if rows:
            details = rows[0]["details"]
            if isinstance(details, dict):
                pid_type = details.get("type")
                if pid_type:
                    invalidate_cache_fn(zone_id, pid_type)
                    logger.info("Invalidated PID config cache for zone %s, type %s", zone_id, pid_type)

                    if pid_type == "ph" and zone_id in ph_controller._pid_by_zone:
                        del ph_controller._pid_by_zone[zone_id]
                        ph_controller._last_pid_tick.pop(zone_id, None)
                    elif pid_type == "ec" and zone_id in ec_controller._pid_by_zone:
                        del ec_controller._pid_by_zone[zone_id]
                        ec_controller._last_pid_tick.pop(zone_id, None)
    except Exception as e:
        logger.warning("Failed to check PID config updates for zone %s: %s", zone_id, e, exc_info=True)
        await send_infra_exception_alert_fn(
            error=e,
            code=INFRA_PID_CONFIG_UPDATE_CHECK_FAILED,
            alert_type="PID Config Update Check Failed",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_housekeeping",
            details={"check": "pid_config_updates"},
        )


__all__ = [
    "check_pid_config_updates",
    "check_zone_deletion",
    "update_zone_health",
]
