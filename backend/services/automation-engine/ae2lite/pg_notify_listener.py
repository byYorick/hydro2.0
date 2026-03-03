"""PostgreSQL LISTEN/NOTIFY helper for AE2-Lite."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import asyncpg

from infrastructure.zone_event_trigger import ZoneEventTrigger


PayloadHandler = Callable[[str], Awaitable[None]]

TWO_TANK_TRIGGER_EVENTS = frozenset(
    {
        "CLEAN_FILL_COMPLETED",
        "SOLUTION_FILL_COMPLETED",
        "PREPARE_TARGETS_REACHED",
    }
)


def _to_zone_id(raw_zone_id: Any) -> Optional[int]:
    try:
        value = int(raw_zone_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _to_event_payload(raw_payload: Any) -> Dict[str, Any]:
    return raw_payload if isinstance(raw_payload, dict) else {}


def _extract_event_type(event: Dict[str, Any]) -> str:
    candidates = (
        event.get("event_type"),
        event.get("type"),
        event.get("event"),
        event.get("reason_code"),
        (_to_event_payload(event.get("payload"))).get("event_type"),
        (_to_event_payload(event.get("payload_json"))).get("event_type"),
        (_to_event_payload(event.get("details"))).get("event_type"),
    )
    for raw in candidates:
        normalized = str(raw or "").strip().upper()
        if normalized:
            return normalized
    return ""


async def handle_two_tank_zone_event_payload(
    payload: str,
    *,
    zone_event_trigger: ZoneEventTrigger,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """Dispatch two-tank trigger events to ZoneEventTrigger."""
    try:
        event = json.loads(payload) if payload else {}
    except Exception:
        logger.debug("Failed to decode two-tank notify payload: %s", payload)
        return None

    if not isinstance(event, dict):
        return None

    zone_id = _to_zone_id(event.get("zone_id"))
    if zone_id is None:
        return None

    event_type = _extract_event_type(event)
    if event_type not in TWO_TANK_TRIGGER_EVENTS:
        return None

    event_payload = _to_event_payload(event.get("payload"))
    return await zone_event_trigger.on_zone_event(
        zone_id=zone_id,
        event_type=event_type,
        payload=event_payload,
    )


class PgNotifyListener:
    def __init__(self, *, dsn: str, channel: str, handler: PayloadHandler):
        self._dsn = dsn
        self._channel = channel
        self._handler = handler
        self._conn: Optional[asyncpg.Connection] = None
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10000)

    def _callback(self, _conn, _pid: int, _channel: str, payload: str) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            # fallback polling is mandatory in runtime
            return

    async def connect(self) -> None:
        if self._conn is not None and not self._conn.is_closed():
            return
        self._conn = await asyncpg.connect(dsn=self._dsn)
        await self._conn.add_listener(self._channel, self._callback)

    async def close(self) -> None:
        conn = self._conn
        if conn is None:
            return
        self._conn = None
        try:
            await conn.remove_listener(self._channel, self._callback)
        except Exception:
            pass
        try:
            await conn.close()
        except Exception:
            pass

    async def pump_once(self, timeout_sec: float = 1.0) -> bool:
        payload = await asyncio.wait_for(self._queue.get(), timeout=max(0.05, timeout_sec))
        await self._handler(payload)
        return True


__all__ = [
    "PgNotifyListener",
    "TWO_TANK_TRIGGER_EVENTS",
    "handle_two_tank_zone_event_payload",
]
