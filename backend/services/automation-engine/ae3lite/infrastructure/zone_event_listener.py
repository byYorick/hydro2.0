"""PostgreSQL NOTIFY-listener для runtime node events AE3."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Callable, Coroutine, Optional

import asyncpg

from ae3lite.infrastructure.metrics import (
    LISTENER_CONNECTED,
    LISTENER_INVALID_PAYLOAD,
    LISTENER_RECONNECT_TOTAL,
)

logger = logging.getLogger(__name__)

_CHANNEL = "ae_zone_event"
_LISTENER_NAME = "zone_event"
_KEEPALIVE_INTERVAL_SEC = 30
_REPLAY_EVENT_TYPES = (
    "LEVEL_SWITCH_CHANGED",
    "EMERGENCY_STOP_ACTIVATED",
    "IRRIGATION_SOLUTION_LOW",
)


class ZoneEventListener:
    """Слушает NOTIFY ae_zone_event и вызывает callback с payload zone_event."""

    def __init__(
        self,
        dsn: str,
        on_zone_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        *,
        replay_lookback_minutes: int = 5,
    ) -> None:
        self._dsn = dsn
        self._on_zone_event = on_zone_event
        self._stop_event: asyncio.Event = asyncio.Event()
        self._replay_on_connect = True
        self._replay_lookback_minutes = max(1, int(replay_lookback_minutes))

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._run_once()
                backoff = 1.0
            except asyncio.CancelledError:
                logger.info("ZoneEventListener: получена отмена, listener завершает работу")
                return
            except Exception as exc:
                LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(0)
                LISTENER_RECONNECT_TOTAL.labels(listener=_LISTENER_NAME).inc()
                self._replay_on_connect = True
                logger.warning(
                    "ZoneEventListener: ошибка соединения, переподключение через %.1f с: %s",
                    backoff,
                    exc,
                    exc_info=True,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return
                backoff = min(backoff * 2, 60.0)

    async def _run_once(self) -> None:
        conn: asyncpg.Connection = await asyncpg.connect(self._dsn)
        LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(1)
        logger.info("ZoneEventListener: соединение установлено, прослушивается channel=%s", _CHANNEL)
        try:
            if self._replay_on_connect:
                await self._replay_missed_zone_events(conn)
                self._replay_on_connect = False
            await conn.add_listener(_CHANNEL, self._notify_handler)
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(_KEEPALIVE_INTERVAL_SEC),
                    )
                except asyncio.TimeoutError:
                    await conn.execute("SELECT 1")
        finally:
            try:
                await conn.remove_listener(_CHANNEL, self._notify_handler)
            except Exception:
                logger.warning(
                    "ZoneEventListener: не удалось снять listener с channel=%s",
                    _CHANNEL,
                    exc_info=True,
                )
            await conn.close()
            LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(0)
            logger.info("ZoneEventListener: соединение закрыто")

    async def _replay_missed_zone_events(self, conn: asyncpg.Connection) -> None:
        """Backfill критичных node runtime events, пропущенных во время разрыва LISTEN."""
        lookback = timedelta(minutes=self._replay_lookback_minutes)
        rows = await conn.fetch(
            """
            SELECT zone_id, type, payload_json, created_at
            FROM zone_events
            WHERE type = ANY($1::text[])
              AND created_at >= NOW() - $2::interval
              AND COALESCE(payload_json->>'source', 'node_event') = 'node_event'
            ORDER BY created_at ASC
            """,
            list(_REPLAY_EVENT_TYPES),
            lookback,
        )
        if not rows:
            logger.info(
                "ZoneEventListener: replay после reconnect — node events за последние %s мин не найдены",
                self._replay_lookback_minutes,
            )
            return

        logger.info(
            "ZoneEventListener: replay после reconnect — %d node event(s) за последние %s мин",
            len(rows),
            self._replay_lookback_minutes,
        )
        for row in rows:
            payload_json = row.get("payload_json")
            details = dict(payload_json) if isinstance(payload_json, dict) else {}
            data = {
                "zone_id": int(row["zone_id"]),
                "event_type": str(row["type"] or "").strip(),
                "source": str(details.get("source") or "node_event"),
                "channel": details.get("channel"),
                "state": details.get("state"),
                "initial": details.get("initial"),
                "snapshot": details.get("snapshot"),
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "replayed": True,
            }
            await self._dispatch(data)

    def _notify_handler(
        self,
        conn: asyncpg.Connection,  # noqa: ARG002
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        data = self._parse_payload(channel=channel, payload=payload)
        if data is None:
            return

        logger.debug(
            "ZoneEventListener: получен node-event notify zone_id=%s event_type=%s channel=%s",
            data.get("zone_id"),
            data.get("event_type"),
            data.get("channel"),
        )
        asyncio.get_running_loop().create_task(self._dispatch(data))

    def _parse_payload(self, *, channel: str, payload: str) -> Optional[dict[str, Any]]:
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            LISTENER_INVALID_PAYLOAD.labels(listener=_LISTENER_NAME).inc()
            logger.warning(
                "ZoneEventListener: получен некорректный JSON payload в channel=%s payload=%r",
                channel,
                payload,
            )
            return None

        if not isinstance(data, dict):
            LISTENER_INVALID_PAYLOAD.labels(listener=_LISTENER_NAME).inc()
            logger.warning(
                "ZoneEventListener: payload не является object в channel=%s payload=%r",
                channel,
                payload,
            )
            return None

        return data

    async def _dispatch(self, data: dict[str, Any]) -> None:
        try:
            await self._on_zone_event(data)
        except Exception as exc:
            logger.error(
                "ZoneEventListener: callback on_zone_event завершился ошибкой: %s",
                exc,
                exc_info=True,
            )


__all__ = ["ZoneEventListener"]
