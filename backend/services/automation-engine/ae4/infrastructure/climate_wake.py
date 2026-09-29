"""Пробуждение форточек: один POST на greenhouse_id, без импорта ae3lite."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Optional

import httpx

logger = logging.getLogger(__name__)


async def wake_greenhouse_climate_ticks(
    *,
    greenhouse_ids: Iterable[int],
    now: datetime,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> list[int]:
    """POST /greenhouses/{id}/start-climate-tick для каждой теплицы с зонами ae4."""
    root = str(
        base_url
        or os.getenv("AE4_CLIMATE_TICK_BASE_URL")
        or os.getenv("AUTOMATION_ENGINE_INTERNAL_URL")
        or "http://127.0.0.1:9405"
    ).rstrip("/")
    auth = str(
        token
        or os.getenv("AUTOMATION_LARAVEL_SCHEDULER_API_TOKEN")
        or os.getenv("PY_INGEST_TOKEN")
        or ""
    ).strip()
    woken: list[int] = []
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
    for greenhouse_id in sorted({int(item) for item in greenhouse_ids}):
        if greenhouse_id <= 0:
            continue
        url = f"{root}/greenhouses/{greenhouse_id}/start-climate-tick"
        payload = {
            "source": "ae4_zone_tick",
            "idempotency_key": f"ae4-climate-{greenhouse_id}-{stamp}",
        }
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {auth}"
        try:
            if client is not None:
                response = await client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=5.0) as owned:
                    response = await owned.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "AE4: climate-tick HTTP %s для greenhouse_id=%s",
                    response.status_code,
                    greenhouse_id,
                )
                continue
            woken.append(greenhouse_id)
        except Exception:
            logger.exception(
                "AE4: не удалось разбудить climate-tick greenhouse_id=%s",
                greenhouse_id,
            )
    return woken


__all__ = ["wake_greenhouse_climate_ticks"]
