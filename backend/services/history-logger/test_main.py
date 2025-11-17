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

