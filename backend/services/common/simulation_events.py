import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .db import execute, fetch
from .utils.time import utcnow


logger = logging.getLogger(__name__)

_simulation_cache: Dict[int, Tuple[Optional[int], float]] = {}
_cache_ttl_seconds = float(os.getenv("SIMULATION_EVENTS_CACHE_TTL", "5"))


def _normalize_ts(value: Optional[datetime]) -> datetime:
    ts = value or utcnow()
    if getattr(ts, "tzinfo", None):
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.replace(tzinfo=None)


async def get_active_simulation_id(zone_id: int) -> Optional[int]:
    now = time.monotonic()
    cached = _simulation_cache.get(zone_id)
    if cached and now - cached[1] < _cache_ttl_seconds:
        return cached[0]

    try:
        rows = await fetch(
            """
            SELECT id
            FROM zone_simulations
            WHERE zone_id = $1 AND status = 'running'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            zone_id,
        )
    except Exception as e:
        logger.warning(
            "Failed to resolve active simulation id for zone %s: %s",
            zone_id,
            e,
            exc_info=True,
        )
        return None

    simulation_id = rows[0]["id"] if rows else None
    _simulation_cache[zone_id] = (simulation_id, now)
    return simulation_id


async def record_simulation_event(
    zone_id: int,
    service: str,
    stage: str,
    status: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    level: str = "info",
    occurred_at: Optional[datetime] = None,
) -> bool:
    simulation_id = await get_active_simulation_id(zone_id)
    if not simulation_id:
        return False

    ts_value = _normalize_ts(occurred_at)
    try:
        await execute(
            """
            INSERT INTO simulation_events (
                simulation_id,
                zone_id,
                service,
                stage,
                status,
                level,
                message,
                payload,
                occurred_at,
                created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            """,
            simulation_id,
            zone_id,
            service,
            stage,
            status,
            level,
            message,
            payload,
            ts_value,
        )
    except Exception as e:
        logger.warning(
            "Failed to record simulation event for zone %s: %s",
            zone_id,
            e,
            exc_info=True,
        )
        return False

    return True
