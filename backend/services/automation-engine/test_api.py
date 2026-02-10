"""Tests for automation-engine REST API."""
import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Добавляем путь к модулю для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api
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


@pytest.fixture(autouse=True)
def mock_api_fetch():
    """Mock DB lookups used by scheduler API target validation."""
    async def _mock_fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()

        if "from nodes" in normalized and "where uid = $1" in normalized:
            node_uid = args[0]
            if node_uid == "nd-irrig-1":
                return [{"id": 1, "zone_id": 1}]
            if node_uid == "nd-relay-1":
                return [{"id": 2, "zone_id": 1}]
            if node_uid == "nd-other-zone":
                return [{"id": 3, "zone_id": 2}]
            return []

        if "from node_channels" in normalized and "where node_id = $1 and channel = $2" in normalized:
            node_id, channel = args
            valid_channels = {
                1: {"pump_a", "default"},
                2: {"relay_1", "default"},
            }
            if channel in valid_channels.get(int(node_id), set()):
                return [{"?column?": 1}]
            return []

        return []

    with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = _mock_fetch
        yield mock_fetch


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
        "cmd": "run_pump",
        "params": {"duration_ms": 60000}
    }
    
    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["zone_id"] == 1
    assert data["data"]["node_uid"] == "nd-irrig-1"
    assert data["data"]["channel"] == "default"
    assert data["data"]["cmd"] == "run_pump"
    
    mock_command_bus.publish_command.assert_called_once_with(
        zone_id=1,
        node_uid="nd-irrig-1",
        channel="default",
        cmd="run_pump",
        params={"duration_ms": 60000}
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
        "cmd": "run_pump"
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
        "cmd": "run_pump"
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
        "cmd": "run_pump"
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
        "cmd": "run_pump"
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
        "cmd": "run_pump"
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


@pytest.mark.asyncio
async def test_scheduler_command_rejects_node_zone_mismatch(client, mock_command_bus):
    """Scheduler command must fail if node belongs to another zone."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    payload = {
        "zone_id": 1,
        "node_uid": "nd-other-zone",
        "channel": "default",
        "cmd": "run_pump"
    }

    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 409
    assert "assigned to zone 2" in response.json()["detail"]
    mock_command_bus.publish_command.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_command_rejects_unknown_channel(client, mock_command_bus):
    """Scheduler command must fail if channel is not present on node."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    payload = {
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "unknown_channel",
        "cmd": "run_pump"
    }

    response = client.post("/scheduler/command", json=payload)
    assert response.status_code == 422
    assert "Channel 'unknown_channel' not found" in response.json()["detail"]
    mock_command_bus.publish_command.assert_not_called()


def test_test_hook_forbidden_when_test_mode_disabled(client):
    """Test hook should be unavailable when AE_TEST_MODE is disabled."""
    old_mode = api._test_mode
    try:
        api._test_mode = False
        response = client.post("/test/hook", json={
            "zone_id": 1,
            "action": "reset_backoff",
        })
        assert response.status_code == 403
    finally:
        api._test_mode = old_mode


def test_test_hook_reset_backoff_and_get_state(client):
    """Reset backoff should persist state override and be retrievable."""
    old_mode = api._test_mode
    old_hooks = dict(api._test_hooks)
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._test_hooks.clear()
        api._zone_states_override.clear()

        reset_resp = client.post("/test/hook", json={
            "zone_id": 11,
            "action": "reset_backoff",
        })
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "ok"

        state_resp = client.get("/test/hook/11")
        assert state_resp.status_code == 200
        payload = state_resp.json()["data"]["state_override"]
        assert payload["error_streak"] == 0
        assert payload["next_allowed_run_at"] is None
        assert payload["degraded_alert_active"] is False
        assert payload["last_backoff_reported_until"] is None
        assert payload["last_missing_targets_report_at"] is None
    finally:
        api._test_mode = old_mode
        api._test_hooks.clear()
        api._test_hooks.update(old_hooks)
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_set_state_and_unknown_action_validation(client):
    """set_state should require state payload, unknown action should return 400."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        missing_state_resp = client.post("/test/hook", json={
            "zone_id": 12,
            "action": "set_state",
        })
        assert missing_state_resp.status_code == 400
        assert "set_state requires state" in missing_state_resp.json()["detail"]

        unknown_action_resp = client.post("/test/hook", json={
            "zone_id": 12,
            "action": "unknown_action",
        })
        assert unknown_action_resp.status_code == 400
        assert "Unknown action" in unknown_action_resp.json()["detail"]
    finally:
        api._test_mode = old_mode
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_set_state_normalizes_datetime_fields(client):
    """set_state должен преобразовывать ISO-дату в datetime внутри override."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        response = client.post("/test/hook", json={
            "zone_id": 13,
            "action": "set_state",
            "state": {
                "error_streak": 2,
                "next_allowed_run_at": "2099-01-01T00:00:00Z",
            },
        })
        assert response.status_code == 200

        state = api._zone_states_override[13]
        assert state["error_streak"] == 2
        assert isinstance(state["next_allowed_run_at"], datetime)
        assert state["next_allowed_run_at"].isoformat().startswith("2099-01-01T00:00:00")
        assert state["degraded_alert_active"] is False
    finally:
        api._test_mode = old_mode
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_publish_command_success(client, mock_command_bus):
    """publish_command в test hook должен вызывать CommandBus и возвращать флаг published."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        mock_command_bus.publish_command = AsyncMock(return_value=False)
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 21,
            "action": "publish_command",
            "command": {
                "node_uid": "nd-ph-esp32una",
                "channel": "main_pump",
                "cmd": "set_relay",
                "params": {"state": 1, "marker": "e2e-marker"},
                "cmd_id": "cmd-e2e-1",
            },
        })

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["data"]["published"] is False
        assert payload["data"]["zone_id"] == 21
        assert payload["data"]["node_uid"] == "nd-ph-esp32una"

        mock_command_bus.publish_command.assert_called_once_with(
            zone_id=21,
            node_uid="nd-ph-esp32una",
            channel="main_pump",
            cmd="set_relay",
            params={"state": 1, "marker": "e2e-marker"},
            cmd_id="cmd-e2e-1",
        )
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_requires_payload(client, mock_command_bus):
    """publish_command в test hook должен требовать command payload."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 22,
            "action": "publish_command",
        })

        assert response.status_code == 400
        assert "publish_command requires command payload" in response.json()["detail"]
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_validates_required_fields(client, mock_command_bus):
    """publish_command в test hook валидирует обязательные поля node_uid/channel/cmd."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 23,
            "action": "publish_command",
            "command": {
                "node_uid": "",
                "channel": "main_pump",
                "cmd": "set_relay",
            },
        })

        assert response.status_code == 400
        assert "command.node_uid" in response.json()["detail"]
        mock_command_bus.publish_command.assert_not_called()
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_uses_temporary_command_bus_when_not_initialized(client):
    """При отсутствии глобального CommandBus test hook должен поднять временный экземпляр."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        set_command_bus(None, "")

        temp_bus = Mock()
        temp_bus.start = AsyncMock(return_value=None)
        temp_bus.stop = AsyncMock(return_value=None)
        temp_bus.publish_command = AsyncMock(return_value=False)

        with patch("api.CommandBus", return_value=temp_bus) as command_bus_cls:
            response = client.post("/test/hook", json={
                "zone_id": 24,
                "action": "publish_command",
                "command": {
                    "node_uid": "nd-ph-esp32una",
                    "channel": "main_pump",
                    "cmd": "set_relay",
                    "params": {"state": 1},
                },
            })

        assert response.status_code == 200
        assert response.json()["data"]["published"] is False
        command_bus_cls.assert_called_once()
        assert command_bus_cls.call_args.kwargs["enforce_node_zone_assignment"] is True
        temp_bus.start.assert_awaited_once()
        temp_bus.publish_command.assert_awaited_once()
        temp_bus.stop.assert_awaited_once()
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)
