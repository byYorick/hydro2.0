"""Tests for history-logger HTTP API."""
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime
from common.utils.time import utcnow
from app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def bypass_ingest_auth():
    """Disable auth for ingest endpoint tests."""
    with patch("ingest_routes._auth_ingest") as mock_auth:
        mock_auth.return_value = None
        yield mock_auth


def test_health_endpoint(client):
    """Test health check endpoint."""
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

    queue = AsyncMock()
    queue.get_queue_metrics.return_value = {
        "size": 0,
        "oldest_age_seconds": 0,
        "dlq_size": 0,
        "success_rate": 1.0,
    }

    with patch("system_routes.get_pool", new_callable=AsyncMock) as mock_get_pool, \
         patch("system_routes.check_db_health", new_callable=AsyncMock), \
         patch("system_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("system_routes.check_mqtt_health", new_callable=AsyncMock), \
         patch("system_routes.get_alert_queue", new_callable=AsyncMock) as mock_get_alert_queue, \
         patch("system_routes.get_status_queue", new_callable=AsyncMock) as mock_get_status_queue:
        mock_get_pool.return_value = _PoolStub()
        mock_get_mqtt.return_value = _MqttStub()
        mock_get_alert_queue.return_value = queue
        mock_get_status_queue.return_value = queue

        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "components" in data


def test_ingest_telemetry_endpoint(client):
    """Test telemetry ingestion endpoint."""
    with patch("ingest_routes.process_telemetry_batch") as mock_process:
        mock_process.return_value = None  # async function
        
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_id": 1,
                    "metric_type": "PH",
                    "value": 6.5,
                    "channel": "ph_sensor"
                }
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["count"] == 1
        # Проверяем, что process_telemetry_batch был вызван
        # Но поскольку это async, нужно проверить через mock
        # Для синхронного теста нужно использовать AsyncMock правильно


def test_ingest_telemetry_endpoint_multiple_samples(client):
    """Test telemetry ingestion with multiple samples."""
    with patch("ingest_routes.process_telemetry_batch") as mock_process:
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_id": 1,
                    "metric_type": "PH",
                    "value": 6.5
                },
                {
                    "node_uid": "nd-ec-1",
                    "zone_id": 1,
                    "metric_type": "EC",
                    "value": 1.8
                },
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["count"] == 2


def test_ingest_telemetry_endpoint_with_ts_string(client):
    """Test telemetry ingestion with timestamp as ISO string."""
    with patch("ingest_routes.process_telemetry_batch") as mock_process:
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_id": 1,
                    "metric_type": "PH",
                    "value": 6.5,
                    "ts": "2025-01-27T10:00:00Z"
                }
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200


def test_ingest_telemetry_endpoint_with_ts_numeric(client):
    """Test telemetry ingestion with ts as numeric (seconds from firmware)."""
    with patch("ingest_routes.process_telemetry_batch") as mock_process:
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_id": 1,
                    "metric_type": "PH",
                    "value": 6.5,
                    "ts": 1737979.2  # seconds (from firmware: esp_timer_get_time() / 1000000)
                }
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200


def test_ingest_telemetry_endpoint_invalid_payload(client):
    """Test telemetry ingestion with invalid payload."""
    # Нет samples - пустой массив допустим
    response = client.post("/ingest/telemetry", json={"samples": []})
    assert response.status_code == 200
    assert response.json()["count"] == 0
    
    # Нет samples в payload
    response = client.post("/ingest/telemetry", json={})
    assert response.status_code == 200  # Возвращает 200 с count=0
    assert response.json()["count"] == 0


def test_ingest_telemetry_endpoint_with_zone_uid(client):
    """Test telemetry ingestion with zone_uid."""
    with patch("ingest_routes.process_telemetry_batch") as mock_process:
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_uid": "zn-1",
                    "metric_type": "PH",
                    "value": 6.5
                }
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_process_telemetry_batch_includes_ts_parameter():
    """Test that process_telemetry_batch includes ts parameter in SQL query."""
    from unittest.mock import patch, AsyncMock
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from telemetry_processing import _node_cache, _zone_cache
    from models import TelemetrySampleModel
    import time

    _node_cache.clear()
    _zone_cache.clear()
    tp._cache_last_update = time.time()
    _node_cache[("nd-ph-1", None)] = (1, 1)
    _zone_cache[("zn-1", None)] = 1

    # Мокаем execute для проверки SQL запроса
    with patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute:
        # Мокаем fetch для получения node_id
        with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("telemetry_processing._sensor_cache", {
                 (1, 1, "PH", "ph_sensor"): 101,
             }):
            mock_fetch.return_value = [
                {"id": 1, "uid": "nd-ph-1"}
            ]

            # Создаём тестовые образцы
            samples = [
                TelemetrySampleModel(
                    node_uid="nd-ph-1",
                    zone_uid="zn-1",
                    zone_id=1,
                    metric_type="PH",
                    value=6.5,
                    ts=datetime(2025, 1, 27, 10, 0, 0),
                    channel="ph_sensor"
                ),
                TelemetrySampleModel(
                    node_uid="nd-ph-1",
                    zone_uid="zn-1",
                    zone_id=1,
                    metric_type="PH",
                    value=6.6,
                    ts=datetime(2025, 1, 27, 10, 1, 0),
                    channel="ph_sensor"
                ),
            ]
            
            # Запускаем функцию
            await process_telemetry_batch(samples)
            
            # Проверяем, что execute был вызван
            assert mock_execute.called
            
            # Получаем аргументы вызова для вставки telemetry_samples
            call_args = next(
                call for call in mock_execute.call_args_list
                if "telemetry_samples" in str(call)
            )
            query = call_args[0][0]  # SQL запрос
            params = call_args[0][1:]  # Параметры
            
            # Проверяем, что в запросе есть 6 плейсхолдеров для каждого образца
            assert "$6" in query or "$12" in query
            
            # Проверяем, что параметров достаточно (6 на образец)
            assert len(params) >= 12
            
            # Проверяем, что ts присутствует в параметрах (позиции 2 и 8)
            assert isinstance(params[1], datetime)
            assert isinstance(params[7], datetime)


@pytest.mark.asyncio
async def test_extract_zone_id_from_uid():
    """Test extract_zone_id_from_uid function."""
    from utils import extract_zone_id_from_uid
    
    # Валидные значения
    assert extract_zone_id_from_uid("zn-1") == 1
    assert extract_zone_id_from_uid("zn-123") == 123
    
    # Невалидные значения
    assert extract_zone_id_from_uid("zone-1") is None
    assert extract_zone_id_from_uid("zn") is None
    assert extract_zone_id_from_uid(None) is None
    assert extract_zone_id_from_uid("") is None


@pytest.mark.asyncio
async def test_telemetry_payload_model_validation():
    """Test TelemetryPayloadModel validation."""
    from models import TelemetryPayloadModel
    from pydantic import ValidationError
    
    # Валидный payload
    payload = TelemetryPayloadModel(metric_type="PH", value=6.5)
    assert payload.metric_type == "PH"
    assert payload.value == 6.5
    
    # Пустой metric_type недопустим
    with pytest.raises(ValidationError):
        TelemetryPayloadModel(metric_type="", value=6.5)
    
    # Слишком длинный metric_type недопустим
    with pytest.raises(ValidationError):
        TelemetryPayloadModel(metric_type="A" * 51, value=6.5)


@pytest.mark.asyncio
async def test_process_telemetry_batch_with_zone_id_extraction():
    """Test process_telemetry_batch with zone_id extraction from zone_uid."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from telemetry_processing import _node_cache, _zone_cache
    from models import TelemetrySampleModel
    from unittest.mock import patch, AsyncMock
    from datetime import datetime
    import time

    _node_cache.clear()
    _zone_cache.clear()
    tp._cache_last_update = time.time()
    _node_cache[("nd-ph-1", None)] = (1, 1)
    _zone_cache[("zn-1", None)] = 1

    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_uid="zn-1",  # zone_id будет извлечен из zone_uid
            metric_type="PH",
            value=6.5,
            ts=utcnow()
        )
    ]
    
    with patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute, \
         patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing._sensor_cache", {(1, 1, "PH", "PH"): 101}):
        mock_fetch.return_value = [{"id": 1, "uid": "nd-ph-1"}]
        
        await process_telemetry_batch(samples)
        
        # Проверяем, что execute был вызван
        assert mock_execute.called
        
        # Проверяем, что zone_id был правильно извлечен (должен быть 1)
        call_args = next(
            call for call in mock_execute.call_args_list
            if "telemetry_samples" in str(call)
        )
        params = call_args[0][1:]
        assert params[2] == 1


@pytest.mark.asyncio
async def test_handle_telemetry_invalid_timestamp_emits_throttled_alert():
    """Invalid firmware timestamp should emit one throttled telemetry anomaly alert."""
    import telemetry_processing as tp
    from telemetry_processing import handle_telemetry

    tp._anomaly_alert_last_sent.clear()

    queue = AsyncMock()
    queue.push = AsyncMock(return_value=True)

    payload = {
        "metric_type": "PH",
        "value": 6.5,
        "ts": 123,  # uptime-like timestamp, should be treated as invalid
    }
    topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"

    with patch.object(tp.state, "telemetry_queue", queue), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_alert.return_value = True
        await handle_telemetry(topic, json.dumps(payload).encode("utf-8"))
        await handle_telemetry(topic, json.dumps(payload).encode("utf-8"))

    assert mock_alert.await_count == 1
    assert mock_alert.await_args.kwargs["code"] == "infra_telemetry_invalid_timestamp"


@pytest.mark.asyncio
async def test_process_telemetry_batch_emits_alerts_for_unknown_zone_and_node():
    """Batch processing should emit anomaly alerts when zone/node is unknown."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    samples = [
        TelemetrySampleModel(
            node_uid="nd-unknown-1",
            zone_uid="zn-unknown-1",
            gh_uid="gh-unknown-1",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.return_value = []
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    emitted_codes = [call.kwargs.get("code") for call in mock_alert.await_args_list]
    assert "infra_telemetry_zone_not_found" in emitted_codes
    assert "infra_telemetry_node_not_found" in emitted_codes


@pytest.mark.asyncio
async def test_process_telemetry_batch_resolves_node_unassigned_alert_on_recovery():
    """Valid telemetry from assigned node should emit RESOLVED for node_unassigned anomaly."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._anomaly_resolved_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", None)] = 1
    tp._node_cache[("nd-ph-1", None)] = (1, 1)
    tp._zone_greenhouse_cache[1] = 1

    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.4,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_resolved_alert", new_callable=AsyncMock) as mock_resolved, \
         patch("telemetry_processing._sensor_cache", {(1, 1, "PH", "ph_sensor"): 101}):
        mock_fetch.return_value = []
        mock_resolved.return_value = True

        await process_telemetry_batch(samples)

    assert mock_resolved.await_count == 1
    assert mock_resolved.await_args.kwargs["code"] == "infra_telemetry_node_unassigned"
    assert mock_resolved.await_args.kwargs["zone_id"] == 1
    assert mock_resolved.await_args.kwargs["node_uid"] == "nd-ph-1"


@pytest.mark.asyncio
async def test_process_telemetry_batch_falls_back_to_uid_lookup_for_unassigned_node_with_gh_uid():
    """If node cache is cold, resolver must fallback to UID-only lookup and emit node_unassigned."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()
    tp._zone_cache[("zn-1", "gh-1")] = 1

    samples = [
        TelemetrySampleModel(
            node_uid="nd-cold-cache-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="PH",
            value=6.3,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.side_effect = [
            [],
            [{"id": 101, "uid": "nd-cold-cache-1", "zone_id": None}],
        ]
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    emitted_codes = [call.kwargs.get("code") for call in mock_alert.await_args_list]
    assert "infra_telemetry_node_unassigned" in emitted_codes
    assert "infra_telemetry_node_not_found" not in emitted_codes


@pytest.mark.asyncio
async def test_process_telemetry_batch_skips_immediate_node_unassigned_recovery():
    """Recovery alert should wait for grace interval after recent unassigned sample."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._anomaly_resolved_last_sent.clear()
    tp._node_unassigned_last_seen.clear()
    tp._cache_last_update = time.time()

    original_grace = tp._node_unassigned_recovery_grace_sec
    tp._node_unassigned_recovery_grace_sec = 5.0

    try:
        tp._zone_cache[("zn-1", None)] = 1
        tp._node_cache[("nd-ph-1", None)] = (1, 1)
        tp._zone_greenhouse_cache[1] = 1
        tp._node_unassigned_last_seen[(1, "nd-ph-1")] = time.time()

        samples = [
            TelemetrySampleModel(
                node_uid="nd-ph-1",
                zone_uid="zn-1",
                gh_uid="gh-1",
                metric_type="PH",
                value=6.2,
                channel="ph_sensor",
                ts=utcnow(),
            )
        ]

        with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("telemetry_processing.execute", new_callable=AsyncMock), \
             patch("telemetry_processing.send_infra_resolved_alert", new_callable=AsyncMock) as mock_resolved, \
             patch("telemetry_processing._sensor_cache", {(1, 1, "PH", "ph_sensor"): 101}):
            mock_fetch.return_value = []
            mock_resolved.return_value = True

            await process_telemetry_batch(samples)

        assert mock_resolved.await_count == 0
    finally:
        tp._node_unassigned_recovery_grace_sec = original_grace
