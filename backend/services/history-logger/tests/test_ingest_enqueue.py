"""HTTP ingest enqueue tests (C2)."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def bypass_ingest_auth():
    with patch("ingest_routes._auth_ingest"), patch("ingest_routes._check_rate_limit", return_value=True):
        yield


def test_ingest_http_enqueues_to_redis(client):
    payload = {
        "samples": [
            {
                "node_uid": "nd-ph-1",
                "zone_id": 1,
                "metric_type": "PH",
                "value": 6.5,
                "channel": "ph_sensor",
            }
        ]
    }

    with patch("ingest_routes._enqueue_http_samples", new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = (1, 0)
        response = client.post("/ingest/telemetry", json=payload)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    mock_enqueue.assert_awaited_once()


def test_ingest_http_queue_failure_returns_503(client):
    payload = {
        "samples": [
            {
                "node_uid": "nd-ph-1",
                "zone_id": 1,
                "metric_type": "PH",
                "value": 6.5,
            }
        ]
    }

    with patch("ingest_routes._enqueue_http_samples", new_callable=AsyncMock) as mock_enqueue:
        mock_enqueue.return_value = (0, 1)
        response = client.post("/ingest/telemetry", json=payload)

    assert response.status_code == 503
