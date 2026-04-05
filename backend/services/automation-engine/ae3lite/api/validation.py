"""Вспомогательные проверки scheduler API для AE3-Lite."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import HTTPException


async def validate_scheduler_zone(
    zone_id: int,
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: Any,
) -> None:
    try:
        rows = await fetch_fn(
            """
            SELECT id
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
        raise HTTPException(status_code=503, detail="Проверка зоны временно недоступна") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"Зона '{zone_id}' не найдена")


__all__ = ["validate_scheduler_zone"]
