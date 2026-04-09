"""PostgreSQL NOTIFY-listener для runtime node events AE3."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import asyncpg

logger = logging.getLogger(__name__)

_CHANNEL = "ae_zone_event"
_KEEPALIVE_INTERVAL_SEC = 30


class ZoneEventListener:
    """Слушает NOTIFY ae_zone_event и вызывает callback с payload zone_event."""

    def __init__(
        self,
        dsn: str,
        on_zone_event: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self._dsn = dsn
        self._on_zone_event = on_zone_event
        self._stop_event: asyncio.Event = asyncio.Event()

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
        logger.info("ZoneEventListener: соединение установлено, прослушивается channel=%s", _CHANNEL)
        try:
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
            logger.info("ZoneEventListener: соединение закрыто")

    def _notify_handler(
        self,
        conn: asyncpg.Connection,  # noqa: ARG002
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "ZoneEventListener: получен некорректный JSON payload в channel=%s payload=%r",
                channel,
                payload,
            )
            return

        logger.debug(
            "ZoneEventListener: получен node-event notify zone_id=%s event_type=%s channel=%s",
            data.get("zone_id"),
            data.get("event_type"),
            data.get("channel"),
        )
        asyncio.get_running_loop().create_task(self._dispatch(data))

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
