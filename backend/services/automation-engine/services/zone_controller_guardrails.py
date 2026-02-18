"""Controller guardrail helpers for ZoneAutomationService."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import (
    INFRA_CONTROLLER_COMMAND_SKIPPED_CIRCUIT_OPEN,
    INFRA_CONTROLLER_COOLDOWN_SKIP,
    INFRA_CONTROLLER_FAILED,
)

UtcNowFn = Callable[[], datetime]
SendInfraAlertFn = Callable[..., Awaitable[bool]]
SendInfraExceptionAlertFn = Callable[..., Awaitable[Any]]
CreateZoneEventFn = Callable[[int, str, Dict[str, Any]], Awaitable[Any]]
CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]
IsControllerInCooldownFn = Callable[[int, str], bool]
RecordControllerFailureFn = Callable[[int, str], None]
EmitControllerCooldownSkipSignalFn = Callable[[int, str], Awaitable[None]]


async def emit_controller_circuit_open_signal(
    *,
    zone_id: int,
    controller_name: str,
    controller_circuit_open_reported_at: Dict[tuple[int, str], datetime],
    throttle_seconds: int,
    utcnow_fn: UtcNowFn,
    send_infra_alert_fn: SendInfraAlertFn,
    channel: Optional[str] = None,
    cmd: Optional[str] = None,
) -> None:
    key = (zone_id, controller_name)
    now = utcnow_fn()
    last_reported = controller_circuit_open_reported_at.get(key)
    if last_reported and (now - last_reported).total_seconds() < throttle_seconds:
        return

    alert_sent = await send_infra_alert_fn(
        code=INFRA_CONTROLLER_COMMAND_SKIPPED_CIRCUIT_OPEN,
        alert_type="Controller Command Skipped (Circuit Open)",
        message=f"Zone {zone_id} controller '{controller_name}' skipped command due to open API circuit breaker",
        severity="error",
        zone_id=zone_id,
        service="automation-engine",
        component=f"controller:{controller_name}",
        channel=channel,
        cmd=cmd,
        error_type="CircuitBreakerOpenError",
        details={
            "controller": controller_name,
            "throttle_seconds": throttle_seconds,
        },
    )
    if alert_sent:
        controller_circuit_open_reported_at[key] = now


def is_controller_in_cooldown(
    *,
    zone_id: int,
    controller_name: str,
    controller_failures: Dict[tuple[int, str], datetime],
    cooldown_seconds: int,
    utcnow_fn: UtcNowFn,
) -> bool:
    key = (zone_id, controller_name)
    last_failure = controller_failures.get(key)
    if last_failure is None:
        return False
    cooldown_end = last_failure + timedelta(seconds=cooldown_seconds)
    return utcnow_fn() < cooldown_end


def record_controller_failure(
    *,
    zone_id: int,
    controller_name: str,
    controller_failures: Dict[tuple[int, str], datetime],
    controller_cooldown_reported_at: Dict[tuple[int, str], datetime],
    utcnow_fn: UtcNowFn,
) -> None:
    key = (zone_id, controller_name)
    controller_failures[key] = utcnow_fn()
    controller_cooldown_reported_at.pop(key, None)


async def safe_process_controller(
    *,
    zone_id: int,
    controller_name: str,
    controller_coro: Any,
    is_controller_in_cooldown_fn: IsControllerInCooldownFn,
    emit_controller_cooldown_skip_signal_fn: EmitControllerCooldownSkipSignalFn,
    record_controller_failure_fn: RecordControllerFailureFn,
    controller_failures: Dict[tuple[int, str], datetime],
    controller_cooldown_reported_at: Dict[tuple[int, str], datetime],
    create_zone_event_fn: CreateZoneEventFn,
    send_infra_exception_alert_fn: SendInfraExceptionAlertFn,
    controller_cooldown_seconds: int,
    logger: Any,
) -> None:
    try:
        from api import get_test_hook_for_zone

        test_hook = get_test_hook_for_zone(zone_id, controller_name)
        if test_hook and test_hook.get("active"):
            error_type = test_hook.get("error_type", "ControllerError")
            logger.warning(
                "[TEST_HOOK] Injecting error for zone %s, controller %s: %s",
                zone_id,
                controller_name,
                error_type,
                extra={"zone_id": zone_id, "controller": controller_name, "error_type": error_type},
            )
            await create_zone_event_fn(
                zone_id,
                "CONTROLLER_FAILED",
                {
                    "controller": controller_name,
                    "error_type": error_type,
                    "test_hook": True,
                },
            )
            if error_type == "ControllerError":
                raise RuntimeError(f"[TEST_HOOK] Forced controller error: {controller_name}")
            if error_type == "TimeoutError":
                raise TimeoutError(f"[TEST_HOOK] Forced timeout: {controller_name}")
            raise Exception(f"[TEST_HOOK] Forced error ({error_type}): {controller_name}")
    except ImportError:
        pass
    except Exception:
        raise

    if is_controller_in_cooldown_fn(zone_id, controller_name):
        if inspect.iscoroutine(controller_coro):
            controller_coro.close()
        await emit_controller_cooldown_skip_signal_fn(zone_id, controller_name)
        return

    try:
        await controller_coro
        key = (zone_id, controller_name)
        controller_failures.pop(key, None)
        controller_cooldown_reported_at.pop(key, None)
    except Exception as error:
        record_controller_failure_fn(zone_id, controller_name)
        logger.error(
            "Zone %s: Controller '%s' failed: %s",
            zone_id,
            controller_name,
            error,
            exc_info=True,
            extra={"zone_id": zone_id, "controller": controller_name, "error": str(error)},
        )
        try:
            await create_zone_event_fn(
                zone_id,
                "CONTROLLER_FAILED",
                {
                    "controller": controller_name,
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "cooldown_seconds": controller_cooldown_seconds,
                },
            )
        except Exception as event_error:
            logger.error(
                "Zone %s: Failed to create CONTROLLER_FAILED event: %s",
                zone_id,
                event_error,
                exc_info=True,
            )

        await send_infra_exception_alert_fn(
            error=error,
            code=INFRA_CONTROLLER_FAILED,
            alert_type="Controller Failed",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component=f"controller:{controller_name}",
            details={
                "controller": controller_name,
                "cooldown_seconds": controller_cooldown_seconds,
            },
        )


async def emit_controller_cooldown_skip_signal(
    *,
    zone_id: int,
    controller_name: str,
    controller_failures: Dict[tuple[int, str], datetime],
    controller_cooldown_reported_at: Dict[tuple[int, str], datetime],
    cooldown_seconds: int,
    cooldown_skip_report_throttle_seconds: int,
    utcnow_fn: UtcNowFn,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    send_infra_alert_fn: SendInfraAlertFn,
    logger: Any,
) -> None:
    key = (zone_id, controller_name)
    now = utcnow_fn()
    last_reported = controller_cooldown_reported_at.get(key)
    if last_reported and (now - last_reported).total_seconds() < cooldown_skip_report_throttle_seconds:
        logger.debug(
            "Zone %s: Controller '%s' cooldown skip (throttled report)",
            zone_id,
            controller_name,
            extra={"zone_id": zone_id, "controller": controller_name},
        )
        return

    last_failure = controller_failures.get(key)
    cooldown_end = last_failure + timedelta(seconds=cooldown_seconds) if last_failure else None
    remaining_seconds = (
        max(0, int((cooldown_end - now).total_seconds()))
        if cooldown_end
        else cooldown_seconds
    )

    logger.warning(
        "Zone %s: Controller '%s' skipped due to cooldown, remaining=%ss",
        zone_id,
        controller_name,
        remaining_seconds,
        extra={
            "zone_id": zone_id,
            "controller": controller_name,
            "remaining_seconds": remaining_seconds,
        },
    )

    event_created = await create_zone_event_safe_fn(
        zone_id=zone_id,
        event_type="CONTROLLER_COOLDOWN_SKIP",
        details={
            "controller": controller_name,
            "cooldown_seconds": cooldown_seconds,
            "remaining_seconds": remaining_seconds,
        },
        signal_name="controller_cooldown_skip",
    )

    alert_sent = await send_infra_alert_fn(
        code=INFRA_CONTROLLER_COOLDOWN_SKIP,
        alert_type="Controller Cooldown Skip",
        message=f"Zone {zone_id} controller '{controller_name}' skipped due to cooldown",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component=f"controller:{controller_name}",
        error_type="ControllerCooldown",
        details={
            "controller": controller_name,
            "cooldown_seconds": cooldown_seconds,
            "remaining_seconds": remaining_seconds,
        },
    )
    if event_created or alert_sent:
        controller_cooldown_reported_at[key] = now
    else:
        logger.warning(
            "Zone %s: Cooldown skip signal for controller '%s' not persisted, will retry",
            zone_id,
            controller_name,
            extra={"zone_id": zone_id, "controller": controller_name},
        )


__all__ = [
    "emit_controller_circuit_open_signal",
    "emit_controller_cooldown_skip_signal",
    "is_controller_in_cooldown",
    "record_controller_failure",
    "safe_process_controller",
]
