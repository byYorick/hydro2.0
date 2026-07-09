"""Unit-тесты B1: phantom Prometheus metrics в history-logger."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from common.utils.time import utcnow
from fastapi.testclient import TestClient

from app import app
from common.redis_queue import TelemetryQueue, TelemetryQueueItem
from models import TelemetrySampleModel


@pytest.fixture
def client():
    return TestClient(app)


def _prepare_telemetry_caches() -> None:
    import telemetry_processing as tp

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._sensor_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._zone_greenhouse_cache[1] = 1
    tp._node_cache[("nd-ph-1", "gh-1")] = (101, 1, None)
    tp._sensor_cache[(1, 101, "PH", "ph_sensor")] = 501


async def _fetch_side_effect(query, *args):
    normalized = " ".join(str(query).split()).lower()
    if "from sensors" in normalized and "any($1" in normalized:
        return [{"id": 501}]
    return []


@pytest.mark.asyncio
async def test_telemetry_pg_write_failed_samples_stage():
    from metrics import TELEMETRY_PG_WRITE_FAILED
    from telemetry_processing import process_telemetry_batch

    _prepare_telemetry_caches()
    before = TELEMETRY_PG_WRITE_FAILED.labels(stage="samples")._value.get()

    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    async def execute_side_effect(query, *args):
        if "telemetry_samples" in str(query):
            raise RuntimeError("samples insert failed")
        return "INSERT 0 1"

    async def fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors" in normalized and "any($1" in normalized:
            return [{"id": 501}]
        if "telemetry_samples" in normalized and "returning" in normalized:
            raise RuntimeError("samples insert failed")
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = fetch_side_effect
        mock_execute.side_effect = execute_side_effect

        await process_telemetry_batch(samples)

    after = TELEMETRY_PG_WRITE_FAILED.labels(stage="samples")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_telemetry_pg_write_failed_last_stage():
    from metrics import TELEMETRY_PG_WRITE_FAILED
    from telemetry_processing import process_telemetry_batch

    _prepare_telemetry_caches()
    before = TELEMETRY_PG_WRITE_FAILED.labels(stage="last")._value.get()

    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    async def execute_side_effect(query, *args):
        if "telemetry_last" in str(query):
            raise RuntimeError("telemetry_last write failed")
        return "INSERT 0 1"

    async def fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors" in normalized and "any($1" in normalized:
            return [{"id": 501}]
        if "telemetry_samples" in normalized and "returning" in normalized:
            return [{"sensor_id": 501, "ts": args[1][0]}]
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = fetch_side_effect
        mock_execute.side_effect = execute_side_effect

        await process_telemetry_batch(samples)

    after = TELEMETRY_PG_WRITE_FAILED.labels(stage="last")._value.get()
    assert after == before + 2


@pytest.mark.asyncio
async def test_telemetry_dead_list_size_on_move_to_dead():
    from metrics import TELEMETRY_DEAD_LIST_SIZE

    queue = TelemetryQueue()
    raw = TelemetryQueueItem(node_uid="n1", metric_type="PH", value=1.0).to_json()
    queue._client = AsyncMock()
    queue._move_processing_to_dead_script = AsyncMock(return_value=1)
    queue.prune_expired_dead = AsyncMock(return_value=0)
    queue._client.llen = AsyncMock(return_value=3)

    before = TELEMETRY_DEAD_LIST_SIZE._value.get()
    await queue._move_raw_to_dead(raw, reason="max_pg_retries")
    after = TELEMETRY_DEAD_LIST_SIZE._value.get()

    assert after == 3
    assert after != before or before == 3


@pytest.mark.asyncio
async def test_telemetry_dead_list_size_method():
    from metrics import TELEMETRY_DEAD_LIST_SIZE

    queue = TelemetryQueue()
    queue._client = AsyncMock()
    queue._client.llen = AsyncMock(return_value=7)

    size = await queue.dead_list_size()
    assert size == 7


def test_health_updates_dlq_gauges(client):
    from metrics import ALERT_DLQ_SIZE, COMMAND_STATUS_DLQ_SIZE

    class _AcquireCtx:
        def __init__(self, conn):
            self._conn = conn

        async def __aenter__(self):
            return self._conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    conn = AsyncMock()
    conn.fetchval.return_value = 1

    class _PoolStub:
        def acquire(self):
            return _AcquireCtx(conn)

    class _MqttStub:
        def is_connected(self):
            return True

    alert_queue = AsyncMock()
    alert_queue.get_queue_metrics.return_value = {
        "size": 0,
        "oldest_age_seconds": 0,
        "dlq_size": 4,
        "success_rate": 1.0,
    }
    status_queue = AsyncMock()
    status_queue.get_queue_metrics.return_value = {
        "size": 0,
        "oldest_age_seconds": 0,
        "dlq_size": 9,
        "success_rate": 1.0,
    }

    redis_client = AsyncMock()
    redis_client.ping = AsyncMock(return_value=True)
    telemetry_queue = AsyncMock()
    telemetry_queue.get_health_metrics = AsyncMock(
        return_value={
            "size": 0,
            "processing_size": 0,
            "depth": 0,
            "utilization": 0.0,
            "oldest_age_seconds": 0.0,
            "dead_list_size": 0,
            "max_size": 50000,
        }
    )

    with patch("system_routes.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("system_routes.check_db_health", new_callable=AsyncMock), \
         patch("system_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("system_routes.check_mqtt_health", new_callable=AsyncMock), \
         patch("system_routes.get_alert_queue", new_callable=AsyncMock) as mock_get_alert_queue, \
         patch("system_routes.get_status_queue", new_callable=AsyncMock) as mock_get_status_queue, \
         patch("system_routes.get_redis_client", new_callable=AsyncMock) as mock_get_redis, \
         patch("system_routes.update_redis_health"), \
         patch("system_routes.hl_state") as mock_state:
        mock_get_pool.return_value = _PoolStub()
        mock_get_mqtt.return_value = _MqttStub()
        mock_get_alert_queue.return_value = alert_queue
        mock_get_status_queue.return_value = status_queue
        mock_get_redis.return_value = redis_client
        mock_state.telemetry_queue = telemetry_queue

        response = client.get("/health")

    assert response.status_code == 200
    assert ALERT_DLQ_SIZE._value.get() == 4
    assert COMMAND_STATUS_DLQ_SIZE._value.get() == 9


@pytest.mark.asyncio
async def test_config_report_buffer_expired_counter():
    from handlers import _shared
    from metrics import CONFIG_REPORT_BUFFER_EXPIRED

    _shared.PENDING_CONFIG_REPORTS.clear()
    before = CONFIG_REPORT_BUFFER_EXPIRED._value.get()
    _shared.PENDING_CONFIG_REPORTS["hw-expired"] = {
        "topic": "t",
        "payload": b"x",
        "ts": 0.0,
    }

    _shared.prune_pending_config_reports_locked(_shared.PENDING_CONFIG_REPORT_TTL_SEC + 1)

    after = CONFIG_REPORT_BUFFER_EXPIRED._value.get()
    assert after == before + 1
    assert "hw-expired" not in _shared.PENDING_CONFIG_REPORTS


@pytest.mark.asyncio
async def test_config_report_buffer_overflow_counter():
    from handlers import _shared
    from metrics import CONFIG_REPORT_BUFFER_OVERFLOW

    _shared.PENDING_CONFIG_REPORTS.clear()
    before = CONFIG_REPORT_BUFFER_OVERFLOW._value.get()
    max_size = _shared.PENDING_CONFIG_REPORT_MAX

    for idx in range(max_size + 1):
        await _shared.store_pending_config_report(f"hw-{idx}", "topic", b"payload")

    after = CONFIG_REPORT_BUFFER_OVERFLOW._value.get()
    assert after == before + 1
    assert len(_shared.PENDING_CONFIG_REPORTS) == max_size
