"""Runtime helpers for API middleware/background execution."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from services.resilience_contract import (
    INFRA_AUTOMATION_API_HTTP_5XX,
    INFRA_AUTOMATION_API_UNHANDLED_EXCEPTION,
    INFRA_AUTOMATION_BACKGROUND_TASK_CRASHED,
)


async def process_trace_request(
    request: Any,
    call_next: Callable[[Any], Awaitable[Any]],
    *,
    extract_trace_id_from_headers_fn: Callable[[Any], Optional[str]],
    set_trace_id_fn: Callable[[Optional[str]], str],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    send_infra_alert_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
    verbose_http_logging: bool,
) -> Any:
    trace_id = extract_trace_id_from_headers_fn(request.headers)
    if trace_id:
        set_trace_id_fn(trace_id)
    else:
        trace_id = set_trace_id_fn(None)

    request_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = max(
            0.0,
            (datetime.now(timezone.utc).replace(tzinfo=None) - request_started_at).total_seconds() * 1000.0,
        )
        logger.error(
            "Unhandled API exception: method=%s path=%s duration_ms=%.2f error=%s",
            request.method,
            request.url.path,
            duration_ms,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )
        try:
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_AUTOMATION_API_UNHANDLED_EXCEPTION,
                alert_type="Automation API Unhandled Exception",
                severity="error",
                zone_id=None,
                service="automation-engine",
                component=f"api:{request.url.path}",
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "trace_id": trace_id,
                },
            )
        except Exception as alert_exc:
            logger.warning(
                "Failed to send infra alert for unhandled API exception: %s",
                alert_exc,
                exc_info=True,
            )
        raise

    duration_ms = max(
        0.0,
        (datetime.now(timezone.utc).replace(tzinfo=None) - request_started_at).total_seconds() * 1000.0,
    )
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id

    if verbose_http_logging or response.status_code >= 500:
        log_level = logging.ERROR if response.status_code >= 500 else logging.DEBUG
        logger.log(
            log_level,
            "API request completed: method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"trace_id": trace_id},
        )

    if response.status_code >= 500:
        try:
            await send_infra_alert_fn(
                code=INFRA_AUTOMATION_API_HTTP_5XX,
                alert_type="Automation API HTTP 5xx",
                message=(
                    f"Automation API вернул HTTP {response.status_code} "
                    f"для {request.method} {request.url.path}"
                ),
                severity="error",
                zone_id=None,
                service="automation-engine",
                component=f"api:{request.url.path}",
                error_type=f"http_{response.status_code}",
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "trace_id": trace_id,
                },
            )
        except Exception as alert_exc:
            logger.warning(
                "Failed to send infra alert for API HTTP 5xx: %s",
                alert_exc,
                exc_info=True,
            )

    return response


def spawn_background_task(
    coro: Awaitable[Any],
    *,
    task_name: str,
    zone_id: Optional[int],
    task_id: Optional[str],
    task_type: Optional[str],
    send_infra_exception_alert_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> asyncio.Task:
    task = asyncio.create_task(coro)

    def _on_done(done_task: asyncio.Task) -> None:
        if done_task.cancelled():
            return
        try:
            exc = done_task.exception()
        except Exception as callback_exc:
            logger.error(
                "Failed to inspect background task result: task_name=%s error=%s",
                task_name,
                callback_exc,
                exc_info=True,
            )
            return
        if exc is None:
            return
        logger.error(
            "Background task crashed: task_name=%s task_id=%s task_type=%s zone_id=%s error=%s",
            task_name,
            task_id,
            task_type,
            zone_id,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        async def _send_alert() -> None:
            await send_infra_exception_alert_fn(
                error=exc,
                code=INFRA_AUTOMATION_BACKGROUND_TASK_CRASHED,
                alert_type="Automation Background Task Crashed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component=f"background:{task_name}",
                details={
                    "task_id": task_id,
                    "task_type": task_type,
                    "zone_id": zone_id,
                },
            )

        try:
            asyncio.create_task(_send_alert())
        except Exception:
            logger.warning(
                "Failed to schedule infra alert for crashed background task: task_name=%s",
                task_name,
                exc_info=True,
            )

    task.add_done_callback(_on_done)
    return task


def update_command_effect_confirm_rate(
    task_type: str,
    result: Dict[str, Any],
    *,
    command_effect_totals: Dict[str, int],
    command_effect_confirmed_totals: Dict[str, int],
    command_effect_confirm_rate_metric: Any,
) -> None:
    normalized_task_type = str(task_type or "unknown")

    commands_total_raw = result.get("commands_total")
    commands_confirmed_raw = result.get("commands_effect_confirmed")
    bool_confirmed = result.get("command_effect_confirmed")

    try:
        commands_total = int(commands_total_raw) if commands_total_raw is not None else 0
    except (TypeError, ValueError):
        commands_total = 0

    if commands_total <= 0:
        return

    try:
        commands_confirmed = int(commands_confirmed_raw) if commands_confirmed_raw is not None else None
    except (TypeError, ValueError):
        commands_confirmed = None

    if commands_confirmed is None:
        if isinstance(bool_confirmed, bool):
            commands_confirmed = commands_total if bool_confirmed else 0
        else:
            commands_confirmed = 0

    total = command_effect_totals.get(normalized_task_type, 0) + commands_total
    confirmed = command_effect_confirmed_totals.get(normalized_task_type, 0) + max(
        0,
        min(commands_confirmed, commands_total),
    )
    command_effect_totals[normalized_task_type] = total
    command_effect_confirmed_totals[normalized_task_type] = confirmed
    command_effect_confirm_rate_metric.labels(task_type=normalized_task_type).set(confirmed / max(total, 1))


__all__ = [
    "process_trace_request",
    "spawn_background_task",
    "update_command_effect_confirm_rate",
]
