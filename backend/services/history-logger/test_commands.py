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


@pytest.fixture(autouse=True)
def mock_command_routes_db():
    """Mock DB calls used by command endpoints to keep tests deterministic."""
    async def _mock_fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()

        if "from nodes where uid = $1" in normalized and "zone_id = $2" not in normalized:
            node_uid = args[0]
            if node_uid in {"nd-irrig-1", "nd-relay-1", "nd-test"}:
                return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
            if node_uid == "nd-pending-1":
                return [{"id": 2, "zone_id": None, "pending_zone_id": 1}]
            if node_uid == "nd-other-zone":
                return [{"id": 3, "zone_id": 2, "pending_zone_id": None}]
            return []

        if "from nodes where uid = $1 and zone_id = $2" in normalized:
            node_uid, zone_id = args
            if node_uid in {"nd-irrig-1", "nd-relay-1", "nd-test"} and int(zone_id) == 1:
                return [{"id": 1}]
            return []

        if "from commands where cmd_id = $1" in normalized:
            return []

        return []

    with patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("command_routes.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.side_effect = _mock_fetch
        mock_execute.return_value = "OK"
        yield


@pytest.mark.asyncio
async def test_ensure_command_for_publish_handles_unique_violation_race():
    """Concurrent insert race by cmd_id must not end as 503 error."""
    import asyncpg
    from command_routes import _ensure_command_for_publish

    calls = {"commands_fetch": 0}

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            if calls["commands_fetch"] == 0:
                calls["commands_fetch"] += 1
                return []
            return [{
                "status": "SENT",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    async def _execute(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "insert into commands" in normalized:
            raise asyncpg.UniqueViolationError("duplicate key value violates unique constraint")
        return "OK"

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(side_effect=_execute)):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-race-1",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={"duration_ms": 1000},
            command_source="automation",
        )

    assert response is not None
    assert response["status"] == "ok"
    assert response["data"]["command_id"] == "cmd-race-1"


@pytest.mark.asyncio
async def test_ensure_command_for_publish_rejects_cmd_id_with_different_params():
    from fastapi import HTTPException
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "QUEUED",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        with pytest.raises(HTTPException) as exc_info:
            await _ensure_command_for_publish(
                cmd_id="cmd-same-id",
                zone_id=1,
                node_id=1,
                node_uid="nd-irrig-1",
                channel="default",
                cmd_name="run_pump",
                params={"duration_ms": 2000},
                command_source="automation",
            )

    assert exc_info.value.status_code == 409
    assert "params" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_ensure_command_for_publish_allows_empty_params_shape_compat():
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "QUEUED",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": [],
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-empty-shape-compat",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={},
            command_source="automation",
        )

    assert response is None


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
async def test_publish_command_returns_500_when_sent_status_not_persisted(client, auth_headers, mock_mqtt_client):
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.mark_command_sent", new_callable=AsyncMock, side_effect=RuntimeError("db write failed")):
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "published_but_status_not_persisted"


@pytest.mark.asyncio
async def test_publish_command_rejects_node_zone_mismatch(client, auth_headers, mock_mqtt_client):
    """Command must be rejected if node belongs to another zone."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-other-zone",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "assigned to zone 2" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_rejects_pending_assignment(client, auth_headers, mock_mqtt_client):
    """Command must be rejected until pending assignment is confirmed."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-pending-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "pending assignment confirmation" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_legacy_type(client, auth_headers, mock_mqtt_client):
    """Test command publication rejects legacy 'type' even when 'cmd' is present."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",  # Legacy format
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]


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
async def test_publish_zone_command_unauthorized_in_production(client, mock_mqtt_client):
    """Zone command endpoint must require token in production."""
    import os
    original_env = os.environ.get("APP_ENV")

    try:
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
                "node_uid": "nd-irrig-1",
                "channel": "default",
                "params": {"duration_ms": 1000},
            }
            response = client.post("/zones/1/commands", json=payload)
            assert response.status_code == 401
    finally:
        if original_env:
            os.environ["APP_ENV"] = original_env
        elif "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


@pytest.mark.asyncio
async def test_publish_node_command_unauthorized_in_production(client, mock_mqtt_client):
    """Node command endpoint must require token in production."""
    import os
    original_env = os.environ.get("APP_ENV")

    try:
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
                "channel": "default",
                "params": {"duration_ms": 1000},
            }
            response = client.post("/nodes/nd-irrig-1/commands", json=payload)
            assert response.status_code == 401
    finally:
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
async def test_publish_zone_command_rejects_legacy_type(client, auth_headers, mock_mqtt_client):
    """Zone command endpoint must reject legacy 'type' alias."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",
            "greenhouse_uid": "gh-1",
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/zones/1/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


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
async def test_publish_node_command_rejects_legacy_type(client, auth_headers, mock_mqtt_client):
    """Node command endpoint must reject legacy 'type' alias."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


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


@pytest.mark.asyncio
async def test_publish_command_fails_closed_on_db_error_before_publish(
    client, auth_headers, mock_mqtt_client
):
    """Команда не должна публиковаться в MQTT, если БД недоступна при проверке cmd_id."""

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes where uid = $1" in normalized:
            return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
        if "from commands where cmd_id = $1" in normalized:
            raise Exception("db unavailable")
        return []

    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_fetch.side_effect = _fetch_side_effect

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 503
        assert "Unable to persist command" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_rejects_cmd_id_collision(
    client, auth_headers, mock_mqtt_client
):
    """Команда с тем же cmd_id, но другим target должна быть отклонена."""

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes where uid = $1" in normalized:
            return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
        if "from commands where cmd_id = $1" in normalized:
            return [
                {
                    "status": "QUEUED",
                    "source": "automation",
                    "zone_id": 2,
                    "node_id": 77,
                    "channel": "default",
                    "cmd": "run_pump",
                }
            ]
        return []

    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_fetch.side_effect = _fetch_side_effect

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "cmd_id": "collision-cmd-id-1",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "already belongs to another command" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called
