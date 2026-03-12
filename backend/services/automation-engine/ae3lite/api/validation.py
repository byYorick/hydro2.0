"""AE3-Lite scheduler API validation helpers."""

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
            "Failed to validate scheduler zone: zone_id=%s error=%s",
            zone_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="Zone validation unavailable") from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")


__all__ = ["validate_scheduler_zone"]
