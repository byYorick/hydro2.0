"""Tests for canonical mqtt-bridge endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from common.env import Settings
from main import app

LIVE_STATUS_PATH = "/bridge/nodes/nd-irrig-1/live-status"
LIVE_STATUS_PARAMS = {"greenhouse_uid": "gh-1", "zone_segment": "zn-1"}


@pytest.fixture
def mock_auth():
    with patch("main._auth") as mock:
        yield mock


@pytest.mark.asyncio
async def test_metrics_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "bridge_requests_total" in response.text


@pytest.mark.asyncio
async def test_send_zone_command_returns_404_not_found(mock_auth):
    mock_auth.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/bridge/zones/1/commands",
            json={
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "node_uid": "nd-irrig-1",
                "channel": "default",
                "params": {"duration_ms": 1000},
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_node_command_returns_404_not_found(mock_auth):
    mock_auth.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/bridge/nodes/nd-irrig-1/commands",
            json={
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "channel": "default",
                "params": {"duration_ms": 1000},
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_publish_node_config_returns_404_not_found(mock_auth):
    mock_auth.return_value = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/bridge/nodes/nd-test/config",
            json={
                "node_uid": "nd-test",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "config": {"version": 1},
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_live_node_status_ok(mock_auth):
    mock_auth.return_value = None
    probe_result = {"reachable": True, "reason": None}

    with patch("main.probe_node_status", return_value=probe_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                LIVE_STATUS_PATH,
                params=LIVE_STATUS_PARAMS,
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["reachable"] is True


@pytest.mark.asyncio
async def test_auth_requires_token_when_configured():
    settings = Settings(bridge_api_token="required-token-123")
    probe_result = {"reachable": True, "reason": None}

    with patch("main.get_settings", return_value=settings), \
         patch("main.probe_node_status", return_value=probe_result):
        transport = ASGITransport(app=app, client=("10.0.0.2", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(LIVE_STATUS_PATH, params=LIVE_STATUS_PARAMS)
            assert response.status_code == 401

            response = await client.get(
                LIVE_STATUS_PATH,
                params=LIVE_STATUS_PARAMS,
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert response.status_code == 401

            response = await client.get(
                LIVE_STATUS_PATH,
                params=LIVE_STATUS_PARAMS,
                headers={"Authorization": "Bearer required-token-123"},
            )
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_rejects_non_localhost_without_token():
    settings = Settings(bridge_api_token="")

    with patch("main.get_settings", return_value=settings):
        transport = ASGITransport(app=app, client=("10.0.0.2", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(LIVE_STATUS_PATH, params=LIVE_STATUS_PARAMS)

    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/bridge/zones/1/fill", {"target_level": 0.9}),
        ("/bridge/zones/1/drain", {"target_level": 0.1}),
        ("/bridge/zones/1/calibrate-flow", {"node_id": 1, "channel": "flow_sensor"}),
    ],
)
@pytest.mark.asyncio
async def test_legacy_zone_orchestration_endpoints_are_removed(path, payload):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=payload, headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 404
