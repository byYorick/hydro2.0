"""Tests for history-logger command endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for testing."""
    return {"Authorization": "Bearer dev-token-12345"}


@pytest.fixture(autouse=True)
def auth_settings():
    """Ensure auth uses a stable test token unless overridden."""
    with patch("auth.get_settings") as mock_settings:
        mock_settings.return_value = Mock(history_logger_api_token="dev-token-12345")
        yield mock_settings


@pytest.fixture
def mock_mqtt_client():
    """Create mock MQTT client with proper structure."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    
    # Создаем правильную структуру для mqtt_client._client._client.publish()
    publish_result = Mock()
    publish_result.rc = 0  # 0 означает успех в paho-mqtt
    
    base_client = Mock()
    base_client._client = Mock()
    base_client._client.publish = Mock(return_value=publish_result)
    
    mqtt._client = base_client
    return mqtt


@pytest.mark.asyncio
async def test_publish_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]
        
        # Проверяем, что команда была опубликована в MQTT
        # Структура: mqtt_client._client._client.publish()
        assert mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_legacy_type(client, auth_headers, mock_mqtt_client):
    """Test command publication with legacy 'type' field rejected."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "type": "run_pump",  # Legacy format
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "cmd" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_missing_fields(client, auth_headers):
    """Test command publication with missing required fields."""
    # Missing greenhouse_uid
    payload = {
        "cmd": "run_pump",
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
    assert "cmd" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_unauthorized(client, mock_mqtt_client):
    """Test command publication without authentication."""
    import os
    original_env = os.environ.get("APP_ENV")
    
    try:
        # Устанавливаем production окружение для проверки авторизации
        os.environ["APP_ENV"] = "production"
        
        with patch("auth.get_settings") as mock_auth_settings, \
             patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
             patch("command_routes.get_settings") as mock_settings:
            
            mock_auth_settings.return_value = Mock(history_logger_api_token="required-token")
            mock_get_mqtt.return_value = mock_mqtt_client
            mock_settings.return_value = Mock(mqtt_zone_format="id")
            
            payload = {
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "node_uid": "nd-irrig-1",
                "channel": "default"
            }
            
            response = client.post("/commands", json=payload)
            assert response.status_code == 401
    finally:
        # Восстанавливаем окружение
        if original_env:
            os.environ["APP_ENV"] = original_env
        elif "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


@pytest.mark.asyncio
async def test_publish_zone_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /zones/{zone_id}/commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
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
        "cmd": "run_pump",
        "greenhouse_uid": "gh-1",
        # Missing node_uid and channel
    }
    
    response = client.post("/zones/1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "node_uid" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /nodes/{node_uid}/commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "channel": "default",
            "params": {"duration_ms": 60000}
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
        "cmd": "run_pump",
        "greenhouse_uid": "gh-1",
        # Missing zone_id and channel
    }
    
    response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "zone_id" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_config_missing_zone_id(client, auth_headers):
    """Config publish требует zone_id."""
    payload = {
        "greenhouse_uid": "gh-1",
        "zone_uid": "zn-1",
        "config": {"version": 1},
    }

    response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert "zone_id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_config_success(client, auth_headers, mock_mqtt_client):
    """Config publish использует только параметры теплица/зона."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_service.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_fetch.return_value = [
            {"id": 1, "zone_id": 1, "pending_zone_id": None, "hardware_id": "esp32-test"}
        ]

        payload = {
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "zone_uid": "zn-1",
            "config": {"version": 1},
        }

        response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["data"]["greenhouse_uid"] == "gh-1"
        assert data["data"]["zone_uid"] == "zn-1"
        assert mock_mqtt_client._client._client.publish.called
        publish_call = mock_mqtt_client._client._client.publish.call_args
        assert publish_call.args[0] == "hydro/gh-1/zn-1/nd-test/config"


@pytest.mark.asyncio
async def test_publish_node_config_temp_topic(client, auth_headers, mock_mqtt_client):
    """Config publish в temp-топик при pending_zone_id."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_service.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_fetch.return_value = [
            {"id": 1, "zone_id": None, "pending_zone_id": 1, "hardware_id": "esp32-temp"}
        ]

        payload = {
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "zone_uid": "zn-1",
            "config": {"version": 1},
        }

        response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

        assert response.status_code == 200
        publish_call = mock_mqtt_client._client._client.publish.call_args
        assert publish_call.args[0] == "hydro/gh-temp/zn-temp/esp32-temp/config"


@pytest.mark.asyncio
async def test_publish_command_with_trace_id(client, auth_headers, mock_mqtt_client):
    """Test command publication with trace_id."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
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
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
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
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.publish_command_mqtt", new_callable=AsyncMock) as mock_publish:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_publish.side_effect = Exception("MQTT publish failed")
        
        payload = {
            "cmd": "run_pump",
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
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes._get_zone_uid_from_id", new_callable=AsyncMock) as mock_get_uid:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_get_uid.return_value = "zn-1"
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        # Проверяем, что zone_uid был получен из БД
        mock_get_uid.assert_called_once_with(1)
