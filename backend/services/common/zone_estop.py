"""Operator zone latch shared by command admission; no physical-state guesses."""
from collections.abc import Awaitable, Callable
from typing import Any

from common.db import fetch


async def operator_estop_active(zone_id: int, *, fetch_fn: Callable[..., Awaitable[Any]] | None = None) -> bool:
    rows = await (fetch_fn or fetch)(
        """SELECT type FROM zone_events
        WHERE zone_id=$1
          AND type IN ('EMERGENCY_STOP_ACTIVATED','EMERGENCY_STOP_RELEASED')
          AND COALESCE(payload_json->>'source', details->>'source')='operator'
        ORDER BY created_at DESC, id DESC LIMIT 1""",
        int(zone_id),
    )
    return bool(rows and rows[0].get('type') == 'EMERGENCY_STOP_ACTIVATED')
