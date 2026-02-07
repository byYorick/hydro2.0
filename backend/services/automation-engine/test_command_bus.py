"""Tests for command_bus."""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
from infrastructure.command_bus import CommandBus


@pytest.fixture(autouse=True)
def mock_simulation_events():
    with patch("infrastructure.command_bus.record_simulation_event", new=AsyncMock(return_value=True)) as mock:
        yield mock


@pytest.mark.asyncio
async def test_publish_command_success():
    """Test successful command publication via REST API."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300",
            history_logger_token="test-token"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump", {"duration_ms": 60000})
        
        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://history-logger:9300/commands"
        assert call_args[1]["json"]["cmd"] == "run_pump"
        assert call_args[1]["json"]["zone_id"] == 1
        assert call_args[1]["json"]["node_uid"] == "nd-irrig-1"
        assert call_args[1]["json"]["channel"] == "default"
        assert call_args[1]["json"]["params"] == {"duration_ms": 60000}
        assert call_args[1]["json"]["source"] == "automation"
        assert "Authorization" in call_args[1]["headers"]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_publish_command_http_error():
    """Test command publication with HTTP error."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is False


@pytest.mark.asyncio
async def test_publish_command_timeout():
    """Test command publication with timeout."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is False


@pytest.mark.asyncio
async def test_publish_command_request_error():
    """Test command publication with request error."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection error"))
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is False


@pytest.mark.asyncio
async def test_publish_command_json_decode_error():
    """Test command publication with JSON decode error."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is False


@pytest.mark.asyncio
async def test_publish_controller_command():
    """Test publishing controller command."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        # Используем правильный формат для команды run_pump: duration_ms
        command = {
            'node_uid': 'nd-irrig-1',
            'channel': 'default',
            'cmd': 'run_pump',
            'params': {'duration_ms': 60000}
        }
        
        result = await command_bus.publish_controller_command(1, command)
        
        assert result is True
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_publish_controller_command_invalid():
    """Test publishing invalid controller command."""
    command_bus = CommandBus(
        mqtt=None,
        gh_uid="gh-1",
        history_logger_url="http://history-logger:9300"
    )
    
    # Missing node_uid
    command = {'channel': 'default', 'cmd': 'run_pump'}
    result = await command_bus.publish_controller_command(1, command)
    assert result is False
    
    # Missing cmd
    command = {'node_uid': 'nd-irrig-1', 'channel': 'default'}
    result = await command_bus.publish_controller_command(1, command)
    assert result is False


@pytest.mark.asyncio
async def test_publish_command_with_params():
    """Test command publication with parameters."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        params = {"duration_ms": 60000, "value": 80}
        result = await command_bus.publish_command(1, "nd-light-1", "white_light", "set_pwm", params)
        
        assert result is True
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["cmd"] == "set_pwm"
        assert call_args[1]["json"]["params"] == params


@pytest.mark.asyncio
async def test_publish_command_without_params():
    """Test command publication without parameters."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-relay-1", "default", "set_relay")
        
        assert result is True
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["cmd"] == "set_relay"
        # params всегда передается как объект
        assert call_args[1]["json"]["params"] == {}


@pytest.mark.asyncio
async def test_publish_command_with_trace_id():
    """Test command publication with trace_id from context."""
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch("infrastructure.command_bus.get_trace_id") as mock_trace_id:
        
        mock_trace_id.return_value = "trace-123"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300"
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is True
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["trace_id"] == "trace-123"


@pytest.mark.asyncio
async def test_publish_command_without_token(monkeypatch):
    """Test command publication without authentication token."""
    monkeypatch.delenv("HISTORY_LOGGER_API_TOKEN", raising=False)
    monkeypatch.delenv("PY_INGEST_TOKEN", raising=False)
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300",
            history_logger_token=None
        )
        result = await command_bus.publish_command(1, "nd-irrig-1", "default", "run_pump")
        
        assert result is True
        call_args = mock_client.post.call_args
        # Authorization header не должен быть если token не передан
        assert "Authorization" not in call_args[1]["headers"]


@pytest.mark.asyncio
async def test_publish_controller_command_without_params_preserves_cmd_id():
    """Test that command preserves cmd_id and it reaches history-logger."""
    from infrastructure.command_tracker import CommandTracker
    
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok", "data": {"command_id": "cmd-123"}})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        # Создаем CommandTracker для генерации cmd_id
        tracker = CommandTracker()
        command_bus = CommandBus(
            mqtt=None,
            gh_uid="gh-1",
            history_logger_url="http://history-logger:9300",
            command_tracker=tracker
        )
        
        # Команда с валидными params (cmd_id должен добавиться)
        command = {
            'node_uid': 'nd-relay-1',
            'channel': 'default',
            'cmd': 'set_relay',
            'params': {'state': True},
        }
        
        result = await command_bus.publish_controller_command(1, command)
        
        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        
        # Проверяем, что cmd_id добавлен в payload
        payload = call_args[1]["json"]
        assert "cmd_id" in payload, "cmd_id должен быть в payload"
        
        # Проверяем, что cmd_id не пустой
        cmd_id_in_payload = payload["cmd_id"]
        assert cmd_id_in_payload is not None
        assert len(cmd_id_in_payload) > 0
        
        # Проверяем, что cmd_id также был добавлен в исходную команду
        assert "cmd_id" in command, "cmd_id должен быть добавлен в исходную команду"
        cmd_id_in_command = command["cmd_id"]
        
        # Проверяем, что cmd_id совпадает (тот же cmd_id, что был сгенерирован трекером)
        assert cmd_id_in_command == cmd_id_in_payload, "cmd_id в команде и в payload должны совпадать"
        
        # Проверяем, что cmd_id дошел до history-logger
        assert payload["cmd"] == "set_relay"
        assert payload["node_uid"] == "nd-relay-1"
        assert payload["zone_id"] == 1
        
        # Проверяем, что команда была отслежена трекером
        pending_commands = await tracker.get_pending_commands(zone_id=1)
        assert len(pending_commands) > 0, "Команда должна быть в pending_commands трекера"
        # Проверяем, что cmd_id из трекера совпадает с отправленным
        tracked_cmd_id = list(pending_commands.keys())[0]
        assert tracked_cmd_id == cmd_id_in_payload, "cmd_id из трекера должен совпадать с отправленным в history-logger"
