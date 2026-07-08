"""PostgreSQL NOTIFY-listener для канала scheduler_intent_terminal.

Слушает переходы zone_automation_intents в terminal-статусы и может
использоваться для реактивного reconcile задач без HTTP-polling.

Этот модуль относится к опциональной инфраструктуре: scheduler продолжит
работать через периодический polling, даже если listener не запущен.
"""

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

_CHANNEL = "scheduler_intent_terminal"
_LISTENER_NAME = "intent_status"
_KEEPALIVE_INTERVAL_SEC = 30
_REPLAY_LOOKBACK_MINUTES = 15
_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class IntentStatusListener:
    """Слушает NOTIFY scheduler_intent_terminal и вызывает callbacks.

    Устройство:
    - использует *выделенное* соединение вне общего пула, чтобы LISTEN
      не блокировал и не конкурировал с обычными запросами;
    - на каждый NOTIFY вызывает on_terminal_intent с распарсенным payload;
    - после переподключения воспроизводит terminal intents за последние N минут;
    - запускает keepalive-цикл (SELECT 1) каждые _KEEPALIVE_INTERVAL_SEC,
      чтобы избежать idle-timeout соединения;
    - пишет ошибки в лог и автоматически переподключается с экспоненциальным backoff.
    """

    def __init__(
        self,
        dsn: str,
        on_terminal_intent: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        *,
        replay_lookback_minutes: int = _REPLAY_LOOKBACK_MINUTES,
    ) -> None:
        self._dsn = dsn
        self._on_terminal_intent = on_terminal_intent
        self._replay_lookback_minutes = max(1, int(replay_lookback_minutes))
        self._stop_event: asyncio.Event = asyncio.Event()
        self._replay_on_connect: bool = False

    def stop(self) -> None:
        """Даёт listener'у сигнал остановиться после текущей итерации."""
        self._stop_event.set()

    async def run(self) -> None:
        """Запускает цикл listener'а с автоматическим переподключением при ошибках."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._run_once()
                backoff = 1.0
            except asyncio.CancelledError:
                logger.info("IntentStatusListener: получена отмена, listener завершает работу")
                return
            except Exception as exc:
                LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(0)
                LISTENER_RECONNECT_TOTAL.labels(listener=_LISTENER_NAME).inc()
                self._replay_on_connect = True
                logger.warning(
                    "IntentStatusListener: ошибка соединения, переподключение через %.1f с: %s",
                    backoff,
                    exc,
                    exc_info=True,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return
                backoff = min(backoff * 2, 15.0)

    async def _run_once(self) -> None:
        conn: asyncpg.Connection = await asyncpg.connect(self._dsn)
        LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(1)
        logger.info("IntentStatusListener: соединение установлено, прослушивается channel=%s", _CHANNEL)
        try:
            if self._replay_on_connect:
                await self._replay_missed_terminal_intents(conn)
                self._replay_on_connect = False
            await conn.add_listener(_CHANNEL, self._notify_handler)
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(_KEEPALIVE_INTERVAL_SEC),
                    )
                except asyncio.TimeoutError:
                    # Keepalive предотвращает idle-timeout соединения на стороне БД.
                    await conn.execute("SELECT 1")
        finally:
            try:
                await conn.remove_listener(_CHANNEL, self._notify_handler)
            except Exception:
                logger.warning(
                    "IntentStatusListener: не удалось снять listener с channel=%s",
                    _CHANNEL,
                    exc_info=True,
                )
            await conn.close()
            LISTENER_CONNECTED.labels(listener=_LISTENER_NAME).set(0)
            logger.info("IntentStatusListener: соединение закрыто")

    async def _replay_missed_terminal_intents(self, conn: asyncpg.Connection) -> None:
        """Воспроизводит terminal intents, пропущенные во время разрыва LISTEN."""
        lookback = timedelta(minutes=self._replay_lookback_minutes)
        rows = await conn.fetch(
            """
            SELECT id AS intent_id,
                   zone_id,
                   status,
                   error_code,
                   updated_at
            FROM zone_automation_intents
            WHERE status = ANY($1::text[])
              AND updated_at >= NOW() - $2::interval
            ORDER BY updated_at ASC
            """,
            list(_TERMINAL_STATUSES),
            lookback,
        )
        if not rows:
            logger.info(
                "IntentStatusListener: replay после reconnect — terminal intents за последние %s мин не найдены",
                self._replay_lookback_minutes,
            )
            return

        logger.info(
            "IntentStatusListener: replay после reconnect — %d terminal intent(s) за последние %s мин",
            len(rows),
            self._replay_lookback_minutes,
        )
        for row in rows:
            payload = {
                "intent_id": int(row["intent_id"]),
                "zone_id": int(row["zone_id"]),
                "status": str(row["status"]),
                "error_code": row["error_code"],
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "replayed": True,
            }
            await self._dispatch(payload)

    def _notify_handler(
        self,
        conn: asyncpg.Connection,  # noqa: ARG002
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        """Синхронный callback, зарегистрированный в asyncpg; планирует асинхронную работу."""
        data = self._parse_payload(channel=channel, payload=payload)
        if data is None:
            return

        intent_id = data.get("intent_id")
        zone_id = data.get("zone_id")
        status = data.get("status")
        logger.debug(
            "IntentStatusListener: получен terminal notify intent_id=%s zone_id=%s status=%s",
            intent_id,
            zone_id,
            status,
        )

        asyncio.get_running_loop().create_task(self._dispatch(data))

    def _parse_payload(self, *, channel: str, payload: str) -> Optional[dict[str, Any]]:
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            LISTENER_INVALID_PAYLOAD.labels(listener=_LISTENER_NAME).inc()
            logger.warning(
                "IntentStatusListener: получен некорректный JSON payload в channel=%s payload=%r",
                channel,
                payload,
            )
            return None

        if not isinstance(data, dict):
            LISTENER_INVALID_PAYLOAD.labels(listener=_LISTENER_NAME).inc()
            logger.warning(
                "IntentStatusListener: payload не является object в channel=%s payload=%r",
                channel,
                payload,
            )
            return None

        intent_id = data.get("intent_id")
        zone_id = data.get("zone_id")
        status = data.get("status")
        if intent_id is None or zone_id is None or not status:
            LISTENER_INVALID_PAYLOAD.labels(listener=_LISTENER_NAME).inc()
            logger.warning(
                "IntentStatusListener: payload без обязательных полей intent_id/zone_id/status channel=%s payload=%r",
                channel,
                payload,
            )
            return None

        return data

    async def _dispatch(self, data: dict[str, Any]) -> None:
        try:
            await self._on_terminal_intent(data)
        except Exception as exc:
            logger.error(
                "IntentStatusListener: callback on_terminal_intent завершился ошибкой: %s",
                exc,
                exc_info=True,
            )


__all__ = ["IntentStatusListener"]
