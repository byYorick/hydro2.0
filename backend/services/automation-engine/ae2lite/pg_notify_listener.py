"""PostgreSQL LISTEN/NOTIFY helper for AE2-Lite."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

import asyncpg


PayloadHandler = Callable[[str], Awaitable[None]]


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


__all__ = ["PgNotifyListener"]
