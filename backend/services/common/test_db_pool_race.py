import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import common.db as db


def _reset_pool_state() -> None:
    with db._state_lock:
        db._pools.clear()
        db._pool_locks.clear()


@pytest.mark.asyncio
async def test_get_pool_creates_single_pool_under_concurrency():
    # Сбрасываем глобальное состояние пулов/lock перед тестом.
    _reset_pool_state()

    fake_pool = SimpleNamespace()
    fake_settings = SimpleNamespace(
        pg_host="db",
        pg_port=5432,
        pg_db="hydro_dev",
        pg_user="hydro",
        pg_pass="hydro",
        pg_pool_min_size=1,
        pg_pool_max_size=5,
        pg_app_name="hydro:test",
    )

    create_pool = AsyncMock(return_value=fake_pool)

    with patch.object(db, "get_settings", return_value=fake_settings), \
         patch.object(db.asyncpg, "create_pool", create_pool):
        pools = await asyncio.gather(*[db.get_pool() for _ in range(25)])

    assert all(pool is fake_pool for pool in pools)
    assert create_pool.await_count == 1


@pytest.mark.asyncio
async def test_get_pool_uses_separate_pools_for_different_event_loops():
    _reset_pool_state()

    main_loop_pool = SimpleNamespace()
    thread_loop_pool = SimpleNamespace()
    fake_settings = SimpleNamespace(
        pg_host="db",
        pg_port=5432,
        pg_db="hydro_dev",
        pg_user="hydro",
        pg_pass="hydro",
        pg_pool_min_size=1,
        pg_pool_max_size=5,
        pg_app_name="hydro:test",
    )

    create_pool = AsyncMock(side_effect=[main_loop_pool, thread_loop_pool])

    with patch.object(db, "get_settings", return_value=fake_settings), \
         patch.object(db.asyncpg, "create_pool", create_pool):
        first = await db.get_pool()
        assert first is main_loop_pool

        done = threading.Event()
        holder = {}

        def _runner() -> None:
            async def _thread_job() -> None:
                holder["pool"] = await db.get_pool()

            asyncio.run(_thread_job())
            done.set()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=5)

        assert done.is_set()
        assert holder["pool"] is thread_loop_pool
        assert create_pool.await_count == 2
