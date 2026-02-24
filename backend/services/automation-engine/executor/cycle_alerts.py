"""Helpers for scheduler cycle infra alerts."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

SendInfraAlertFn = Callable[..., Awaitable[Any]]


async def emit_cycle_alert(
    *,
    zone_id: int,
    code: str,
    message: str,
    severity: str,
    details: Dict[str, Any],
    send_infra_alert_fn: SendInfraAlertFn,
) -> None:
    await send_infra_alert_fn(
        code=code,
        alert_type="Automation Cycle Start",
        message=message,
        severity=severity,
        zone_id=zone_id,
        service="automation-engine",
        component="scheduler_task_executor",
        error_type=code,
        details=details,
    )


__all__ = ["emit_cycle_alert"]
