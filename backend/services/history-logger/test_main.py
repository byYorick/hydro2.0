"""Tests for history-logger HTTP API."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
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
                    "metric_type": "ph",
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
                    "metric_type": "ph",
                    "value": 6.5
                },
                {
                    "node_uid": "nd-ec-1",
                    "zone_id": 1,
                    "metric_type": "ec",
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
                    "metric_type": "ph",
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
                    "metric_type": "ph",
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
                    "metric_type": "ph",
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
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    from datetime import datetime
    
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
    from telemetry_processing import process_telemetry_batch
    from models import TelemetrySampleModel
    from unittest.mock import patch, AsyncMock
    from datetime import datetime
    
    samples = [
        TelemetrySampleModel(
            node_uid="nd-ph-1",
            zone_uid="zn-1",  # zone_id будет извлечен из zone_uid
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
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
