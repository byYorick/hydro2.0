"""Bounded intent status synchronization, separate from task/lease orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.infrastructure.metrics import INTENT_SYNC_FAILED


async def notify_sync_exhausted(
    *,
    operation: str,
    intent_id: int,
    task_id: int | None = None,
    zone_id: int | None = None,
    success: bool | None = None,
    error_code: Any = None,
    error_message: Any = None,
    owner: str,
    logger: Any,
    send_alert: Callable[..., Awaitable[Any]],
) -> None:
    normalized_zone_id = int(zone_id or 0)
    normalized_task_id = int(task_id or 0)
    try:
        await send_alert(
            code="ae3_intent_sync_failed",
            alert_type="AE3 Intent Sync Failed",
            message=(f"Не удалось синхронизировать intent ({operation}) после исчерпания retry."),
            severity="error",
            zone_id=normalized_zone_id if normalized_zone_id > 0 else None,
            service="automation-engine",
            component="worker:intent_sync",
            intent_id=intent_id,
            details={
                "operation": operation,
                "intent_id": intent_id,
                "task_id": normalized_task_id if normalized_task_id > 0 else None,
                "zone_id": normalized_zone_id if normalized_zone_id > 0 else None,
                "success": success,
                "error_code": error_code,
                "error_message": error_message,
                "owner": owner,
                "message": (
                    "Task и intent рассинхронизированы. Фоновые recovery и orphan-intent janitor продолжат обработку."
                ),
            },
        )
    except Exception:
        logger.warning(
            "AE3 не смог отправить alert intent_sync_failed intent_id=%s operation=%s",
            intent_id,
            operation,
            exc_info=True,
        )


async def resolve_sync_failed_alert(
    *,
    intent_id: int,
    task_id: int | None = None,
    zone_id: int | None = None,
    owner: str,
    logger: Any,
    send_resolved_alert: Callable[..., Awaitable[Any]],
) -> None:
    normalized_zone_id = int(zone_id or 0)
    normalized_task_id = int(task_id or 0)
    try:
        await send_resolved_alert(
            code="ae3_intent_sync_failed",
            alert_type="AE3 Intent Sync Failed",
            message="Intent успешно синхронизирован в terminal после retry/janitor.",
            zone_id=normalized_zone_id if normalized_zone_id > 0 else None,
            service="automation-engine",
            component="worker:intent_sync",
            intent_id=intent_id,
            details={
                "intent_id": intent_id,
                "task_id": normalized_task_id if normalized_task_id > 0 else None,
                "zone_id": normalized_zone_id if normalized_zone_id > 0 else None,
                "owner": owner,
                "message": "Intent успешно синхронизирован в terminal после retry/janitor.",
            },
        )
    except Exception:
        logger.warning(
            "AE3 не смог отправить alert intent_sync_resolved intent_id=%s",
            intent_id,
            exc_info=True,
        )


async def mark_intent_running(
    *,
    intent_id: int,
    task_id: int | None = None,
    zone_id: int | None = None,
    intent_repository: Any,
    now_fn: Callable[[], datetime],
    max_retries: int,
    logger: Any,
    notify_exhausted: Callable[..., Awaitable[None]],
) -> bool:
    max_attempts = 1 + max_retries
    for attempt in range(max_attempts):
        try:
            updated = await intent_repository.mark_running(intent_id=intent_id, now=now_fn())
            if updated is False:
                raise RuntimeError(f"intent mark_running CAS rejected: intent_id={intent_id}")
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt + 1 >= max_attempts:
                INTENT_SYNC_FAILED.labels(operation="mark_running").inc()
                logger.warning(
                    "AE3 runtime не смог перевести intent в running: intent_id=%s",
                    intent_id,
                    exc_info=True,
                )
                await notify_exhausted(
                    operation="mark_running",
                    intent_id=intent_id,
                    task_id=task_id,
                    zone_id=zone_id,
                )
                return False
    return False


async def mark_intent_terminal(
    *,
    intent_id: int,
    now: datetime,
    success: bool,
    error_code: Any,
    error_message: Any,
    task_id: int | None = None,
    zone_id: int | None = None,
    intent_repository: Any,
    max_retries: int,
    logger: Any,
    notify_exhausted: Callable[..., Awaitable[None]],
) -> bool:
    max_attempts = 1 + max_retries
    for attempt in range(max_attempts):
        try:
            updated = await intent_repository.mark_terminal(
                intent_id=intent_id,
                now=now,
                success=success,
                error_code=error_code,
                error_message=error_message,
            )
            if updated is False:
                raise RuntimeError(f"intent mark_terminal CAS rejected: intent_id={intent_id}")
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt + 1 >= max_attempts:
                INTENT_SYNC_FAILED.labels(operation="mark_terminal").inc()
                logger.warning(
                    "AE3 runtime не смог перевести intent в terminal: intent_id=%s task_id=%s zone_id=%s",
                    intent_id,
                    task_id,
                    zone_id,
                    exc_info=True,
                )
                await notify_exhausted(
                    operation="mark_terminal",
                    intent_id=intent_id,
                    task_id=task_id,
                    zone_id=zone_id,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
                return False
    return False
