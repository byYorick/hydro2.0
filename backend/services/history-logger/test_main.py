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


def test_ws_broadcast_metrics_endpoint(client):
    """Test WS broadcast metrics endpoint."""
    with patch("system_routes.WS_BROADCAST_TOTAL") as mock_metric:
        response = client.post("/internal/metrics/ws-broadcast", json={
            "event_type": "command_status_updated",
        })

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_metric.labels.assert_called_once_with(event_type="command_status_updated")


def test_ws_broadcast_metrics_endpoint_validation_error(client):
    """Test WS broadcast metrics endpoint payload validation."""
    response = client.post("/internal/metrics/ws-broadcast", json={
        "event_type": "",
    })

    assert response.status_code == 422


def test_ws_auth_metrics_endpoint(client):
    """Test WS auth metrics endpoint."""
    with patch("system_routes.WS_AUTH_TOTAL") as mock_metric:
        response = client.post("/internal/metrics/ws-auth", json={
            "channel_type": "zone",
            "result": "success",
        })

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_metric.labels.assert_called_once_with(channel_type="zone", result="success")


def test_ws_auth_metrics_endpoint_validation_error(client):
    """Test WS auth metrics endpoint payload validation."""
    response = client.post("/internal/metrics/ws-auth", json={
        "channel_type": "zone",
        "result": "",
    })

    assert response.status_code == 422


def test_ws_event_metrics_endpoint_broadcast(client):
    """Test unified WS metrics endpoint for broadcast payload."""
    with patch("system_routes.WS_BROADCAST_TOTAL") as mock_metric:
        response = client.post("/internal/metrics/ws-event", json={
            "event_type": "telemetry.batch.updated",
            "count": 2,
        })

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_metric.labels.assert_called_once_with(event_type="telemetry.batch.updated")


def test_ws_event_metrics_endpoint_auth(client):
    """Test unified WS metrics endpoint for auth payload."""
    with patch("system_routes.WS_AUTH_TOTAL") as mock_metric:
        response = client.post("/internal/metrics/ws-event", json={
            "channel_type": "commands",
            "result": "success",
            "count": 3,
        })

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_metric.labels.assert_called_once_with(channel_type="commands", result="success")


def test_ws_event_metrics_endpoint_invalid_payload(client):
    """Test unified WS metrics endpoint payload validation."""
    response = client.post("/internal/metrics/ws-event", json={"count": 1})
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_ws_event_metric_payload"


def test_command_latency_metrics_endpoint(client):
    """Test command latency metrics endpoint."""
    with patch("system_routes.COMMAND_SENT_TO_ACK_LATENCY") as sent_to_ack, \
         patch("system_routes.COMMAND_ACK_TO_DONE_LATENCY") as ack_to_done, \
         patch("system_routes.COMMAND_E2E_LATENCY") as e2e:
        response = client.post(
            "/internal/metrics/command-latency",
            json={
                "cmd_id": "cmd-1",
                "metrics": {
                    "sent_to_accepted_seconds": 1.2,
                    "accepted_to_done_seconds": 0.8,
                    "e2e_latency_seconds": 2.0,
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    sent_to_ack.observe.assert_called_once_with(1.2)
    ack_to_done.observe.assert_called_once_with(0.8)
    e2e.observe.assert_called_once_with(2.0)


def test_error_delivery_latency_metrics_endpoint(client):
    """Test error delivery latency metrics endpoint."""
    with patch("system_routes.ERROR_MQTT_TO_LARAVEL_LATENCY") as mqtt_to_laravel, \
         patch("system_routes.ERROR_LARAVEL_TO_WS_LATENCY") as laravel_to_ws, \
         patch("system_routes.ERROR_DELIVERY_LATENCY") as total:
        response = client.post(
            "/internal/metrics/error-delivery-latency",
            json={
                "metrics": {
                    "mqtt_to_laravel_seconds": 0.4,
                    "laravel_to_ws_seconds": 0.2,
                    "total_latency_seconds": 0.6,
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mqtt_to_laravel.observe.assert_called_once_with(0.4)
    laravel_to_ws.observe.assert_called_once_with(0.2)
    total.observe.assert_called_once_with(0.6)


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


def test_effective_anomaly_throttle_sec_long_for_infra_codes_in_testing(monkeypatch):
    import telemetry_processing as tp

    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("TELEMETRY_ANOMALY_ALERT_THROTTLE_SEC", "30")
    monkeypatch.delenv("TELEMETRY_INFRA_ANOMALY_THROTTLE_SEC", raising=False)
    assert tp._effective_anomaly_throttle_sec("infra_telemetry_node_not_found") == 86400.0
    assert tp._effective_anomaly_throttle_sec("infra_telemetry_zone_not_found") == 30.0


def test_effective_anomaly_throttle_sec_respects_explicit_override(monkeypatch):
    import telemetry_processing as tp

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TELEMETRY_ANOMALY_ALERT_THROTTLE_SEC", "60")
    monkeypatch.setenv("TELEMETRY_INFRA_ANOMALY_THROTTLE_SEC", "120")
    assert tp._effective_anomaly_throttle_sec("infra_telemetry_invalid_timestamp") == 120.0


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
async def test_process_telemetry_batch_skips_unknown_entity_alerts_for_temp_namespace():
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._warning_throttle_last_sent.clear()
    tp._cache_last_update = time.time()

    samples = [
        TelemetrySampleModel(
            node_uid="nd-temp-1",
            zone_uid="zn-temp",
            gh_uid="gh-temp",
            metric_type="PH",
            value=6.5,
            channel="ph_sensor",
            ts=utcnow(),
        )
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert, \
         patch("telemetry_processing.logger") as mock_logger:
        mock_fetch.return_value = []
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    mock_alert.assert_not_awaited()
    mock_logger.warning.assert_not_called()


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
async def test_process_telemetry_batch_skips_unassigned_alert_while_node_binding_pending():
    """Telemetry from node with pending_zone_id should not emit node_unassigned anomaly."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._node_cache[("nd-pending-1", "gh-1")] = (101, None, 1)

    samples = [
        TelemetrySampleModel(
            node_uid="nd-pending-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=1.0,
            channel="level_clean_max",
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
    assert "infra_telemetry_node_unassigned" not in emitted_codes


@pytest.mark.asyncio
async def test_process_telemetry_batch_skips_zone_mismatch_alert_while_node_rebind_pending():
    """Telemetry from the new zone during rebind should not emit node_zone_mismatch anomaly."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-2", "gh-1")] = 2
    tp._node_cache[("nd-rebind-1", "gh-1")] = (101, 1, 2)

    samples = [
        TelemetrySampleModel(
            node_uid="nd-rebind-1",
            zone_uid="zn-2",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=1.0,
            channel="level_solution_max",
            ts=utcnow(),
        )
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute, \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.return_value = []
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    emitted_codes = [call.kwargs.get("code") for call in mock_alert.await_args_list]
    assert "infra_telemetry_node_zone_mismatch" not in emitted_codes
    mock_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_telemetry_batch_refreshes_stale_node_cache_before_unassigned_alert():
    """При stale cache должен быть принудительный refresh node assignment перед node_unassigned."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._zone_greenhouse_cache.clear()
    tp._sensor_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._node_cache[("nd-rebind-1", "gh-1")] = (101, None, None)
    tp._sensor_cache[(1, 101, "WATER_LEVEL", "level_clean_max")] = 501

    samples = [
        TelemetrySampleModel(
            node_uid="nd-rebind-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=1.0,
            channel="level_clean_max",
            ts=utcnow(),
        )
    ]

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes where uid = $1 limit 1" in normalized:
            return [{"id": 101, "zone_id": 1, "pending_zone_id": None}]
        if "from zones where id = any($1)" in normalized:
            return [{"id": 1, "greenhouse_id": 1}]
        return []

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock) as mock_execute, \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.side_effect = _fetch_side_effect
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    emitted_codes = [call.kwargs.get("code") for call in mock_alert.await_args_list]
    assert "infra_telemetry_node_unassigned" not in emitted_codes
    assert tp._node_cache[("nd-rebind-1", "gh-1")][1] == 1
    assert mock_execute.await_count > 0


@pytest.mark.asyncio
async def test_process_telemetry_batch_throttles_node_unassigned_alert_across_channels():
    """Node-unassigned anomaly should be throttled per node/zone, not per channel."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._node_cache[("nd-unassigned-1", "gh-1")] = (202, None, None)

    samples = [
        TelemetrySampleModel(
            node_uid="nd-unassigned-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=0.0,
            channel="level_clean_max",
            ts=utcnow(),
        ),
        TelemetrySampleModel(
            node_uid="nd-unassigned-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=0.0,
            channel="level_clean_min",
            ts=utcnow(),
        ),
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.return_value = []
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    emitted_codes = [call.kwargs.get("code") for call in mock_alert.await_args_list]
    assert emitted_codes.count("infra_telemetry_node_unassigned") == 1


@pytest.mark.asyncio
async def test_process_telemetry_batch_throttles_node_unassigned_warning_logs():
    """Repeated node_unassigned samples should not spam warning logs in one batch."""
    import telemetry_processing as tp
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    import time

    tp._zone_cache.clear()
    tp._node_cache.clear()
    tp._anomaly_alert_last_sent.clear()
    tp._warning_throttle_last_sent.clear()
    tp._cache_last_update = time.time()

    tp._zone_cache[("zn-1", "gh-1")] = 1
    tp._node_cache[("nd-unassigned-1", "gh-1")] = (202, None, None)

    samples = [
        TelemetrySampleModel(
            node_uid="nd-unassigned-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=0.0,
            channel="level_clean_max",
            ts=utcnow(),
        ),
        TelemetrySampleModel(
            node_uid="nd-unassigned-1",
            zone_uid="zn-1",
            gh_uid="gh-1",
            metric_type="WATER_LEVEL",
            value=0.0,
            channel="level_clean_min",
            ts=utcnow(),
        ),
    ]

    with patch("telemetry_processing.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("telemetry_processing.execute", new_callable=AsyncMock), \
         patch("telemetry_processing.send_infra_alert", new_callable=AsyncMock) as mock_alert, \
         patch("telemetry_processing.logger") as mock_logger:
        mock_fetch.return_value = []
        mock_alert.return_value = True

        await process_telemetry_batch(samples)

    mock_logger.warning.assert_called_once()
    assert mock_logger.warning.call_args.args[0] == "Skipping sample: node is not assigned to any zone"
    assert mock_logger.debug.call_count >= 1


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
