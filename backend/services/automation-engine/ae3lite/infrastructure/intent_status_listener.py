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
from typing import Any, Callable, Coroutine

import asyncpg

logger = logging.getLogger(__name__)

_CHANNEL = "scheduler_intent_terminal"
_KEEPALIVE_INTERVAL_SEC = 30


class IntentStatusListener:
    """Слушает NOTIFY scheduler_intent_terminal и вызывает callbacks.

    Устройство:
    - использует *выделенное* соединение вне общего пула, чтобы LISTEN
      не блокировал и не конкурировал с обычными запросами;
    - на каждый NOTIFY вызывает on_terminal_intent с распарсенным payload;
    - запускает keepalive-цикл (SELECT 1) каждые _KEEPALIVE_INTERVAL_SEC,
      чтобы избежать idle-timeout соединения;
    - пишет ошибки в лог и автоматически переподключается с экспоненциальным backoff.
    """

    def __init__(
        self,
        dsn: str,
        on_terminal_intent: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        self._dsn = dsn
        self._on_terminal_intent = on_terminal_intent
        self._stop_event: asyncio.Event = asyncio.Event()

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
                backoff = min(backoff * 2, 60.0)

    async def _run_once(self) -> None:
        conn: asyncpg.Connection = await asyncpg.connect(self._dsn)
        logger.info("IntentStatusListener: соединение установлено, прослушивается channel=%s", _CHANNEL)
        try:
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
            logger.info("IntentStatusListener: соединение закрыто")

    def _notify_handler(
        self,
        conn: asyncpg.Connection,  # noqa: ARG002
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        """Синхронный callback, зарегистрированный в asyncpg; планирует асинхронную работу."""
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "IntentStatusListener: получен некорректный JSON payload в channel=%s payload=%r",
                channel,
                payload,
            )
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
