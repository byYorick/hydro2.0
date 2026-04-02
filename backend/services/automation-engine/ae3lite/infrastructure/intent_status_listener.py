"""PostgreSQL NOTIFY listener for scheduler_intent_terminal channel.

Listens to terminal status transitions of zone_automation_intents and can be
used to drive reactive task reconciliation without HTTP polling.

This module is optional infrastructure — the scheduler continues to function
via periodic polling even if this listener is not running.
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
    """Listens to scheduler_intent_terminal NOTIFY and dispatches callbacks.

    Design:
    - Acquires a *dedicated* connection outside the shared pool so LISTEN
      does not block or compete with regular queries.
    - On each NOTIFY, calls on_terminal_intent with the parsed payload.
    - Runs a keepalive loop (SELECT 1) every _KEEPALIVE_INTERVAL_SEC to
      prevent idle-connection timeouts.
    - Logs errors and auto-reconnects with exponential backoff (max 60 s).
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
        """Signal the listener to stop after the current iteration."""
        self._stop_event.set()

    async def run(self) -> None:
        """Run the listener loop with auto-reconnect on error."""
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                await self._run_once()
                backoff = 1.0
            except asyncio.CancelledError:
                logger.info("IntentStatusListener: cancelled, exiting")
                return
            except Exception as exc:
                logger.warning(
                    "IntentStatusListener: connection error, reconnecting in %.1fs: %s",
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
        logger.info("IntentStatusListener: connected, listening on channel=%s", _CHANNEL)
        try:
            await conn.add_listener(_CHANNEL, self._notify_handler)
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=float(_KEEPALIVE_INTERVAL_SEC),
                    )
                except asyncio.TimeoutError:
                    # Keepalive: prevents idle-connection timeout on the DB side.
                    await conn.execute("SELECT 1")
        finally:
            try:
                await conn.remove_listener(_CHANNEL, self._notify_handler)
            except Exception:
                logger.warning(
                    "IntentStatusListener: failed to remove listener for channel=%s",
                    _CHANNEL,
                    exc_info=True,
                )
            await conn.close()
            logger.info("IntentStatusListener: disconnected")

    def _notify_handler(
        self,
        conn: asyncpg.Connection,  # noqa: ARG002
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        """Sync callback registered with asyncpg; schedules async work."""
        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "IntentStatusListener: invalid JSON payload on channel=%s payload=%r",
                channel,
                payload,
            )
            return

        intent_id = data.get("intent_id")
        zone_id = data.get("zone_id")
        status = data.get("status")
        logger.debug(
            "IntentStatusListener: received terminal notify intent_id=%s zone_id=%s status=%s",
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
                "IntentStatusListener: on_terminal_intent callback failed: %s",
                exc,
                exc_info=True,
            )


__all__ = ["IntentStatusListener"]
