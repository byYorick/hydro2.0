"""Smoke tests для skeleton feature-builder (Phase 2A, без реальной обработки)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client_with_pool():
    """Поднимаем TestClient с мок-пулом; проверяем только HTTP-слой."""
    fake_conn = AsyncMock()

    # /healthz выполняет SELECT 1 и to_regclass(...) для 3 таблиц
    async def fake_fetchrow(sql):
        return {"features": "public.zone_features_5m",
                "labels": "public.ml_labels",
                "dq": "public.ml_data_quality_windows"}

    fake_conn.fetchrow = fake_fetchrow
    fake_conn.execute = AsyncMock(return_value=None)

    class FakePool:
        def acquire(self):
            class Ctx:
                async def __aenter__(self_inner):
                    return fake_conn

                async def __aexit__(self_inner, *a):
                    return False
            return Ctx()

        async def close(self):
            return None

    with patch.object(main, "_pool", FakePool()):
        with TestClient(main.app) as c:
            yield c


def test_healthz_ok(client_with_pool):
    r = client_with_pool.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == main.SCHEMA_VERSION
    assert body["horizons"] == main.HORIZONS


def test_readyz_mirrors_healthz(client_with_pool):
    r = client_with_pool.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_endpoint_exposed():
    # /metrics mount не требует пула; достаточно проверить, что endpoint есть.
    with TestClient(main.app) as c:
        r = c.get("/metrics")
        assert r.status_code == 200
        body = r.text
        assert "feature_builder_poll_runs_total" in body
        assert "feature_builder_errors_total" in body


def test_horizons_env_parsed():
    assert isinstance(main.HORIZONS, list)
    assert all(isinstance(h, int) and h > 0 for h in main.HORIZONS)


def test_poll_once_is_noop_but_counts(monkeypatch):
    """Phase 2A — _poll_once только инкрементит счётчик, не трогает БД."""
    import asyncio as aio
    before = main.FB_POLL_RUNS._value.get()
    aio.get_event_loop().run_until_complete(main._poll_once())
    after = main.FB_POLL_RUNS._value.get()
    assert after == before + 1
