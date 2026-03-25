from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

import common.db as db


def _context_manager_for(conn):
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=conn)
    manager.__aexit__ = AsyncMock(return_value=None)
    return manager


@pytest.mark.asyncio
async def test_fetch_retries_once_after_stale_schema_error() -> None:
    stale_conn = AsyncMock()
    stale_conn.fetch = AsyncMock(
        side_effect=asyncpg.InternalServerError("could not open relation with OID 33264")
    )
    stale_conn.reload_schema_state = AsyncMock(return_value=None)

    fresh_conn = AsyncMock()
    fresh_conn.fetch = AsyncMock(return_value=[{"id": 7}])

    pool = MagicMock()
    pool.acquire.side_effect = [
        _context_manager_for(stale_conn),
        _context_manager_for(fresh_conn),
    ]
    pool.expire_connections = AsyncMock(return_value=None)

    with patch.object(db, "get_pool", AsyncMock(return_value=pool)):
        rows = await db.fetch("SELECT id FROM zones WHERE id = $1", 7)

    assert rows == [{"id": 7}]
    stale_conn.reload_schema_state.assert_awaited_once()
    pool.expire_connections.assert_awaited_once()
    assert pool.acquire.call_count == 2
    fresh_conn.fetch.assert_awaited_once_with("SELECT id FROM zones WHERE id = $1", 7)


@pytest.mark.asyncio
async def test_execute_does_not_retry_non_schema_errors() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("boom"))

    pool = MagicMock()
    pool.acquire.return_value = _context_manager_for(conn)
    pool.expire_connections = AsyncMock(return_value=None)

    with patch.object(db, "get_pool", AsyncMock(return_value=pool)):
        with pytest.raises(RuntimeError, match="boom"):
            await db.execute("SELECT 1")

    pool.expire_connections.assert_not_awaited()
    assert pool.acquire.call_count == 1
