"""Tests for automation-engine REST API."""
import pytest
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Добавляем путь к модулю для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api import app, set_command_bus
from infrastructure.command_bus import CommandBus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_command_bus():
    """Create mock command bus."""
    return Mock(spec=CommandBus)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "automation-engine"


@pytest.mark.asyncio
async def test_scheduler_command_success(client, mock_command_bus):
    """Test successful scheduler command."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default",
        "cmd": "irrigate",
        "params": {"duration": 60}
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["zone_id"] == 1
    assert data["data"]["node_uid"] == "nd-irrig-1"
    assert data["data"]["channel"] == "default"
    assert data["data"]["cmd"] == "irrigate"
    
    mock_command_bus.publish_command.assert_called_once_with(
        zone_id=1,
        node_uid="nd-irrig-1",
        channel="default",
        cmd="irrigate",
        params={"duration": 60}
    )


@pytest.mark.asyncio
async def test_scheduler_command_failed(client, mock_command_bus):
    """Test scheduler command when publish fails."""
    mock_command_bus.publish_command = AsyncMock(return_value=False)
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default",
        "cmd": "irrigate"
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 500
    assert "Failed to publish command" in response.json()["detail"]


@pytest.mark.asyncio
async def test_scheduler_command_not_initialized(client):
    """Test scheduler command when CommandBus is not initialized."""
    set_command_bus(None, "")
    
    payload = {
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default",
        "cmd": "irrigate"
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 503
    assert "CommandBus not initialized" in response.json()["detail"]


def test_scheduler_command_validation_error(client, mock_command_bus):
    """Test scheduler command with validation error."""
    set_command_bus(mock_command_bus, "gh-1")
    
    # Missing required fields
    payload = {
        "zone_id": 1,
        # Missing node_uid, channel, cmd
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 422  # Validation error


def test_scheduler_command_invalid_zone_id(client, mock_command_bus):
    """Test scheduler command with invalid zone_id."""
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 0,  # Invalid: must be >= 1
        "node_uid": "nd-irrig-1",
        "channel": "default",
        "cmd": "irrigate"
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 422  # Validation error


def test_scheduler_command_empty_strings(client, mock_command_bus):
    """Test scheduler command with empty strings."""
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 1,
        "node_uid": "",  # Invalid: min_length=1
        "channel": "default",
        "cmd": "irrigate"
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_scheduler_command_exception(client, mock_command_bus):
    """Test scheduler command when exception occurs."""
    mock_command_bus.publish_command = AsyncMock(side_effect=Exception("Internal error"))
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default",
        "cmd": "irrigate"
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_scheduler_command_without_params(client, mock_command_bus):
    """Test scheduler command without params."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    
    payload = {
        "zone_id": 1,
        "node_uid": "nd-relay-1",
        "channel": "default",
        "cmd": "set_relay"
        # params не указан, должен использоваться default_factory=dict
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 200
    
    mock_command_bus.publish_command.assert_called_once_with(
        zone_id=1,
        node_uid="nd-relay-1",
        channel="default",
        cmd="set_relay",
        params={}  # Пустой dict по умолчанию
    )

