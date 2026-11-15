"""Shared dispatch exclusion for HTTP and restart recovery."""
from contextlib import asynccontextmanager
from typing import AsyncIterator
import zlib
import asyncio
from weakref import WeakKeyDictionary
from fastapi import HTTPException
from common.db import get_pool

# Namespace for per-cmd_id session advisory locks during MQTT republish.
# Keeps concurrent drain workers from double-publishing the same row after
# FOR UPDATE is released (previous bug: SKIP LOCKED ended with the SELECT txn).
_DRAIN_PUBLISH_LOCK_NAMESPACE = zlib.crc32(b"hl_queued_cmd_drain_publish") & 0x7FFFFFFF


def _cmd_publish_advisory_lock_key(cmd_id: str) -> int:
    """Stable 63-bit key: namespace in high 31 bits + crc32(cmd_id) in low 32."""
    cmd_hash = zlib.crc32(cmd_id.encode("utf-8")) & 0xFFFFFFFF
    return (_DRAIN_PUBLISH_LOCK_NAMESPACE << 32) | cmd_hash


_dispatch_capacity = WeakKeyDictionary()


def _capacity_for_pool(pool):
    # Session locks hold a pooled connection across MQTT I/O. Reserve at least
    # half the pool for lifecycle queries so concurrent publishers cannot deadlock.
    size = getattr(pool, "get_max_size", lambda: 4)()
    if size < 2:
        raise HTTPException(status_code=503, detail="Command dispatch requires PG pool size >= 2")
    loop = asyncio.get_running_loop()
    capacity = _dispatch_capacity.get(loop)
    if capacity is None:
        capacity = asyncio.Semaphore(max(1, size // 2))
        _dispatch_capacity[loop] = capacity
    return capacity


@asynccontextmanager
async def _try_claim_cmd_for_publish(cmd_id: str, *, allow_missing: bool = False) -> AsyncIterator[bool]:
    """Hold a session advisory lock on ``cmd_id`` for the publish window.

    Yields True only when the lock was acquired AND the row is still in
    QUEUED/SEND_FAILED. Connection stays checked out until exit so the
    session lock survives MQTT I/O (unlike FOR UPDATE SKIP LOCKED alone).
    """
    lock_key = _cmd_publish_advisory_lock_key(cmd_id)
    pool = await get_pool()
    capacity = _capacity_for_pool(pool)
    if capacity.locked():
        yield False
        return
    async with capacity:
        async with pool.acquire() as conn:
            acquired = bool(
                await conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", int(lock_key))
            )
            if not acquired:
                yield False
                return
            try:
                still_pending = await conn.fetchval(
                    """
                    SELECT 1
                    FROM commands
                    WHERE cmd_id = $1
                      AND status IN ('QUEUED', 'SEND_FAILED')
                    """,
                    cmd_id,
                )
                yield allow_missing or still_pending is not None
            finally:
                await conn.execute("SELECT pg_advisory_unlock($1::bigint)", int(lock_key))



async def reserve_dispatch(cmd_id: str) -> None:
    """Persist uncertainty BEFORE MQTT I/O; a crash cannot authorize a new dose."""
    from common.db import execute
    from common.commands import _affected_rows
    result = await execute("""
        UPDATE commands SET params = (CASE WHEN jsonb_typeof(params) = 'object' THEN params ELSE '{}'::jsonb END) ||
            '{"__hl_dispatch_started":true}'::jsonb, updated_at = NOW()
        WHERE cmd_id = $1 AND status IN ('QUEUED', 'SEND_FAILED')
          AND NOT (COALESCE(params, '{}'::jsonb) ? '__hl_dispatch_started')
    """, cmd_id)
    if _affected_rows(result) != 1:
        raise HTTPException(status_code=409, detail="Dispatch already attempted or command is no longer pending")
