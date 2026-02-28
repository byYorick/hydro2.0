"""Helpers for safe scheduler task event persistence."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import INFRA_SCHEDULER_TASK_EVENT_PERSIST_FAILED

CreateZoneEventFn = Callable[[int, str, Dict[str, Any]], Awaitable[Any]]
SendInfraAlertFn = Callable[..., Awaitable[Any]]
LogWarningFn = Callable[..., Any]


def _is_zone_fk_missing_violation(exc: Exception) -> bool:
    sqlstate = str(getattr(exc, "sqlstate", "") or "").strip()
    if sqlstate != "23503":
        return False
    text = str(exc).lower()
    return "zone_events_zone_id_foreign" in text or (
        "zone_events" in text and "zone_id" in text and "foreign key" in text
    )


async def persist_zone_event_safe(
    *,
    zone_id: int,
    event_type: str,
    payload: Dict[str, Any],
    task_type: str,
    context: Dict[str, Any],
    create_zone_event_fn: CreateZoneEventFn,
    send_infra_alert_fn: SendInfraAlertFn,
    log_warning: LogWarningFn,
) -> bool:
    try:
        await create_zone_event_fn(zone_id, event_type, payload)
        return True
    except Exception as exc:
        task_id = str(context.get("task_id") or "") or None
        correlation_id = str(context.get("correlation_id") or "") or None
        if _is_zone_fk_missing_violation(exc):
            log_warning(
                "Skip scheduler task zone event persist for deleted zone: zone_id=%s task_type=%s task_id=%s event_type=%s",
                zone_id,
                task_type,
                task_id,
                event_type,
            )
            return False
        log_warning(
            "Failed to persist scheduler task zone event: zone_id=%s task_type=%s task_id=%s event_type=%s error=%s",
            zone_id,
            task_type,
            task_id,
            event_type,
            exc,
            exc_info=True,
        )
        await send_infra_alert_fn(
            code=INFRA_SCHEDULER_TASK_EVENT_PERSIST_FAILED,
            alert_type="Scheduler Task Event Persist Failed",
            message=f"Не удалось сохранить zone_event {event_type} для scheduler-task",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=type(exc).__name__,
            details={
                "task_id": task_id,
                "task_type": task_type,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "error": str(exc),
            },
        )
        return False


__all__ = ["persist_zone_event_safe"]
