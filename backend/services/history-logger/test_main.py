"""Tests for history-logger HTTP API."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_telemetry_endpoint(client):
    """Test telemetry ingestion endpoint."""
    with patch("main.process_telemetry_batch") as mock_process:
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
    with patch("main.process_telemetry_batch") as mock_process:
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
    with patch("main.process_telemetry_batch") as mock_process:
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
    """Test telemetry ingestion with timestamp as numeric (milliseconds)."""
    with patch("main.process_telemetry_batch") as mock_process:
        payload = {
            "samples": [
                {
                    "node_uid": "nd-ph-1",
                    "zone_id": 1,
                    "metric_type": "ph",
                    "value": 6.5,
                    "ts": 1737979200000  # milliseconds
                }
            ]
        }
        
        response = client.post("/ingest/telemetry", json=payload)
        
        assert response.status_code == 200


def test_ingest_telemetry_endpoint_invalid_payload(client):
    """Test telemetry ingestion with invalid payload."""
    # Пустой payload
    response = client.post("/ingest/telemetry", json={})
    assert response.status_code == 400
    
    # Нет samples
    response = client.post("/ingest/telemetry", json={"samples": []})
    assert response.status_code == 200  # Пустой массив допустим
    assert response.json()["count"] == 0


def test_ingest_telemetry_endpoint_with_zone_uid(client):
    """Test telemetry ingestion with zone_uid."""
    with patch("main.process_telemetry_batch") as mock_process:
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
    from main import process_telemetry_batch, TelemetrySampleModel
    from datetime import datetime
    
    # Мокаем execute для проверки SQL запроса
    with patch("main.execute", new_callable=AsyncMock) as mock_execute:
        # Мокаем fetch для получения node_id
        with patch("main.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {"id": 1, "uid": "nd-ph-1"}
            ]
            
            # Мокаем upsert_telemetry_last
            with patch("main.upsert_telemetry_last", new_callable=AsyncMock) as mock_upsert:
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
                
                # Получаем аргументы вызова
                call_args = mock_execute.call_args
                query = call_args[0][0]  # Первый позиционный аргумент - SQL запрос
                params = call_args[0][1:]  # Остальные - параметры
                
                # Проверяем, что в запросе есть 6 плейсхолдеров для каждого образца
                # Формат: ($1, $2, $3, $4, $5, $6) для каждого образца
                assert "$6" in query or "$12" in query  # Должен быть 6-й параметр
                
                # Проверяем, что параметров достаточно (6 на образец)
                # 2 образца * 6 параметров = 12 параметров
                assert len(params) >= 12
                
                # Проверяем, что ts присутствует в параметрах
                # ts должен быть в позициях 5, 11 (для каждого образца)
                # Формат: zone_id, node_id, metric_type, channel, value, ts
                assert isinstance(params[5], datetime)  # ts для первого образца
                assert isinstance(params[11], datetime)  # ts для второго образца

