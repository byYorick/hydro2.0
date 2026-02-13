import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import common.http_client_pool as pool


def _reset_http_pool_state() -> None:
    with pool._state_lock:
        pool._http_clients.clear()
        pool._http_semaphores.clear()


@pytest.mark.asyncio
async def test_get_http_client_creates_single_client_under_concurrency():
    _reset_http_pool_state()

    fake_client = SimpleNamespace()
    fake_settings = SimpleNamespace(
        laravel_api_timeout_sec=5.0,
        http_max_keepalive_connections=10,
        http_max_connections=30,
        http_keepalive_expiry_sec=15.0,
        http_max_concurrent_requests=20,
    )
    created_clients = []

    def _factory(*args, **kwargs):
        created_clients.append((args, kwargs))
        return fake_client

    with patch.object(pool, "get_settings", return_value=fake_settings), \
         patch.object(pool.httpx, "AsyncClient", side_effect=_factory):
        clients = await asyncio.gather(*[pool.get_http_client() for _ in range(20)])

    assert all(client is fake_client for client in clients)
    assert len(created_clients) == 1


@pytest.mark.asyncio
async def test_get_http_client_creates_separate_clients_for_different_event_loops():
    _reset_http_pool_state()

    fake_settings = SimpleNamespace(
        laravel_api_timeout_sec=5.0,
        http_max_keepalive_connections=10,
        http_max_connections=30,
        http_keepalive_expiry_sec=15.0,
        http_max_concurrent_requests=20,
    )
    main_loop_client = SimpleNamespace()
    thread_loop_client = SimpleNamespace()
    created_clients = [main_loop_client, thread_loop_client]

    def _factory(*args, **kwargs):
        return created_clients.pop(0)

    with patch.object(pool, "get_settings", return_value=fake_settings), \
         patch.object(pool.httpx, "AsyncClient", side_effect=_factory):
        main_client = await pool.get_http_client()
        assert main_client is main_loop_client

        done = threading.Event()
        holder = {}

        def _runner() -> None:
            async def _job() -> None:
                holder["client"] = await pool.get_http_client()

            asyncio.run(_job())
            done.set()

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=5)

        assert done.is_set()
        assert holder["client"] is thread_loop_client

