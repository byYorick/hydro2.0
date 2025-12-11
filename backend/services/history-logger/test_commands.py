"""Tests for history-logger command endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for testing."""
    return {"Authorization": "Bearer dev-token-12345"}


@pytest.fixture
def mock_mqtt_client():
    """Create mock MQTT client."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock()
    return mqtt


@pytest.mark.asyncio
async def test_publish_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /commands endpoint."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration": 60}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]
        
        # Проверяем, что команда была опубликована в MQTT
        assert mock_mqtt_client.publish_json.called


@pytest.mark.asyncio
async def test_publish_command_legacy_type(client, auth_headers, mock_mqtt_client):
    """Test command publication with legacy 'type' field."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "type": "irrigate",  # Legacy format
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration": 60}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_publish_command_missing_fields(client, auth_headers):
    """Test command publication with missing required fields."""
    # Missing greenhouse_uid
    payload = {
        "cmd": "irrigate",
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default"
    }
    
    response = client.post("/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "greenhouse_uid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_missing_cmd(client, auth_headers):
    """Test command publication without cmd or type."""
    payload = {
        "greenhouse_uid": "gh-1",
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default"
    }
    
    response = client.post("/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "cmd" in response.json()["detail"] or "type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_unauthorized(client, mock_mqtt_client):
    """Test command publication without authentication."""
    payload = {
        "cmd": "irrigate",
        "greenhouse_uid": "gh-1",
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default"
    }
    
    response = client.post("/commands", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_publish_zone_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /zones/{zone_id}/commands endpoint."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration": 60}
        }
        
        response = client.post("/zones/1/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]


@pytest.mark.asyncio
async def test_publish_zone_command_missing_fields(client, auth_headers):
    """Test zone command publication with missing fields."""
    payload = {
        "cmd": "irrigate",
        "greenhouse_uid": "gh-1",
        # Missing node_uid and channel
    }
    
    response = client.post("/zones/1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "node_uid" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /nodes/{node_uid}/commands endpoint."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "channel": "default",
            "params": {"duration": 60}
        }
        
        response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]


@pytest.mark.asyncio
async def test_publish_node_command_missing_fields(client, auth_headers):
    """Test node command publication with missing fields."""
    payload = {
        "cmd": "irrigate",
        "greenhouse_uid": "gh-1",
        # Missing zone_id and channel
    }
    
    response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "zone_id" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_with_trace_id(client, auth_headers, mock_mqtt_client):
    """Test command publication with trace_id."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "trace_id": "trace-123"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_publish_command_with_cmd_id(client, auth_headers, mock_mqtt_client):
    """Test command publication with custom cmd_id."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "cmd_id": "custom-cmd-id-123"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["data"]["command_id"] == "custom-cmd-id-123"


@pytest.mark.asyncio
async def test_publish_command_mqtt_error(client, auth_headers, mock_mqtt_client):
    """Test command publication when MQTT publish fails."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings, \
         patch("main.publish_command_mqtt", new_callable=AsyncMock) as mock_publish:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_publish.side_effect = Exception("MQTT publish failed")
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 500
        assert "Failed to publish command" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_zone_uid_format(client, auth_headers, mock_mqtt_client):
    """Test command publication with mqtt_zone_format='uid'."""
    with patch("main.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("main.get_settings") as mock_settings, \
         patch("main._get_zone_uid_from_id", new_callable=AsyncMock) as mock_get_uid:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_get_uid.return_value = "zn-1"
        
        payload = {
            "cmd": "irrigate",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        # Проверяем, что zone_uid был получен из БД
        mock_get_uid.assert_called_once_with(1)

