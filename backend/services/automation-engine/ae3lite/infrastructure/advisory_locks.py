"""PostgreSQL session advisory locks для координации multi-instance AE3."""

from __future__ import annotations

import zlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from common.db import get_pool

# Стабильный 31-bit ключ для pg_advisory_lock(bigint); namespace: ae3_startup_recovery
AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY = zlib.crc32(b"ae3_startup_recovery") & 0x7FFFFFFF


@asynccontextmanager
async def try_session_advisory_lock(lock_key: int) -> AsyncIterator[bool]:
    """Держит session advisory lock на одном соединении, пока lock взят.

    Yields True, если lock взят. Если не взят — соединение сразу возвращается в
    пул: иначе при pytest ``max_size=1`` любой последующий ``fetch()``
    (например ``load_open_pending_correction_interrupt_checks``) deadlocks.
    """
    pool = await get_pool()
    conn = await pool.acquire()
    acquired = False
    try:
        acquired = bool(
            await conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", int(lock_key))
        )
        if not acquired:
            await pool.release(conn)
            conn = None
            yield False
            return
        yield True
    finally:
        if conn is not None:
            try:
                if acquired:
                    await conn.execute(
                        "SELECT pg_advisory_unlock($1::bigint)", int(lock_key)
                    )
            finally:
                await pool.release(conn)
