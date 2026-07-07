"""Вспомогательные проверки scheduler API для AE3-Lite."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ae3lite.api.http_errors import api_error_detail


async def validate_scheduler_zone(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> None:
    try:
        rows = await fetch_fn(
            """
            SELECT id, automation_runtime
            FROM zones
            WHERE id = $1
            LIMIT 1
            """,
            zone_id,
        )
    except Exception as exc:
        logger.error(
            "Не удалось провалидировать scheduler zone: zone_id=%s error=%s",
            zone_id,
            exc,
            exc_info=True,
        )
        raise api_error_detail(
            "ae3_task_create_failed",
            message="Проверка зоны временно недоступна",
            status_code=503,
            zone_id=zone_id,
        ) from exc

    if not rows:
        raise api_error_detail(
            "zone_not_found",
            status_code=404,
            zone_id=zone_id,
        )

    runtime = str((rows[0] or {}).get("automation_runtime") or "").strip().lower()
    if runtime != "ae3":
        raise api_error_detail(
            "start_cycle_unsupported_runtime",
            status_code=409,
            zone_id=zone_id,
            automation_runtime=runtime or None,
        )


__all__ = ["validate_scheduler_zone"]
