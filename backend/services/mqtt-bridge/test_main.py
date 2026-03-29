"""Tests for canonical mqtt-bridge endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, Mock, patch

from common.env import Settings
from main import app


@pytest.fixture
def mock_auth():
    with patch("main._auth") as mock:
        yield mock


@pytest.fixture
def mock_publisher():
    publisher = Mock()
    publisher.is_ready.return_value = True
    publisher.publish_command.return_value = True
    publisher.publish_config.return_value = True
    with patch("main.publisher", publisher):
        yield publisher


@pytest.mark.asyncio
async def test_metrics_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "bridge_requests_total" in response.text


@pytest.mark.asyncio
async def test_send_zone_command_success(mock_auth, mock_publisher):
    mock_auth.return_value = None

    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main.mark_command_sent", new_callable=AsyncMock) as mock_mark_sent, \
         patch("main.record_simulation_event", new_callable=AsyncMock) as mock_record_event, \
         patch("main.new_command_id", return_value="cmd-zone-1"), \
         patch("main.get_settings", return_value=Mock(mqtt_zone_format="id", node_default_secret=None)):
        mock_fetch.return_value = []

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

    assert response.status_code == 200
    assert response.json()["data"]["command_id"] == "cmd-zone-1"
    mock_publisher.publish_command.assert_called_once()
    mock_mark_sent.assert_awaited_once_with("cmd-zone-1")
    mock_record_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_node_command_success(mock_auth, mock_publisher):
    mock_auth.return_value = None

    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main.mark_command_sent", new_callable=AsyncMock) as mock_mark_sent, \
         patch("main.record_simulation_event", new_callable=AsyncMock), \
         patch("main.new_command_id", return_value="cmd-node-1"), \
         patch("main.get_settings", return_value=Mock(mqtt_zone_format="id", node_default_secret=None)):
        mock_fetch.return_value = []

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

    assert response.status_code == 200
    assert response.json()["data"]["command_id"] == "cmd-node-1"
    mock_publisher.publish_command.assert_called_once()
    mock_mark_sent.assert_awaited_once_with("cmd-node-1")


@pytest.mark.asyncio
async def test_publish_node_config_success(mock_auth, mock_publisher):
    mock_auth.return_value = None

    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []

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

    assert response.status_code == 200
    assert response.json()["data"]["published"] is True
    mock_publisher.publish_config.assert_called_once()


@pytest.mark.asyncio
async def test_send_zone_command_returns_503_when_bridge_not_ready(mock_auth):
    mock_auth.return_value = None
    publisher = Mock()
    publisher.is_ready.return_value = False

    with patch("main.publisher", publisher):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/commands",
                json={
                    "cmd": "run_pump",
                    "greenhouse_uid": "gh-1",
                    "node_uid": "nd-irrig-1",
                    "channel": "default",
                },
                headers={"Authorization": "Bearer test-token"},
            )

    assert response.status_code == 503
    assert response.json()["detail"] == "bridge_not_ready"


@pytest.mark.asyncio
async def test_auth_requires_token_when_configured():
    settings = Settings(bridge_api_token="required-token-123")
    publisher = Mock()
    publisher.is_ready.return_value = False

    with patch("main.get_settings", return_value=settings), \
         patch("main.publisher", publisher):
        transport = ASGITransport(app=app, client=("10.0.0.2", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/commands",
                json={
                    "cmd": "run_pump",
                    "greenhouse_uid": "gh-1",
                    "node_uid": "nd-irrig-1",
                    "channel": "default",
                },
            )
            assert response.status_code == 401

            response = await client.post(
                "/bridge/zones/1/commands",
                json={
                    "cmd": "run_pump",
                    "greenhouse_uid": "gh-1",
                    "node_uid": "nd-irrig-1",
                    "channel": "default",
                },
                headers={"Authorization": "Bearer wrong-token"},
            )
            assert response.status_code == 401

            response = await client.post(
                "/bridge/zones/1/commands",
                json={
                    "cmd": "run_pump",
                    "greenhouse_uid": "gh-1",
                    "node_uid": "nd-irrig-1",
                    "channel": "default",
                },
                headers={"Authorization": "Bearer required-token-123"},
            )
            assert response.status_code == 503


@pytest.mark.asyncio
async def test_auth_rejects_non_localhost_without_token():
    settings = Settings(bridge_api_token="")

    with patch("main.get_settings", return_value=settings):
        transport = ASGITransport(app=app, client=("10.0.0.2", 1234))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/commands",
                json={
                    "cmd": "run_pump",
                    "greenhouse_uid": "gh-1",
                    "node_uid": "nd-irrig-1",
                    "channel": "default",
                },
            )

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
