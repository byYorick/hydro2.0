"""Tests for command_bus."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from infrastructure.command_bus import CommandBus


@pytest.mark.asyncio
async def test_publish_command_success():
    """Test successful command publication."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock()
    
    command_bus = CommandBus(mqtt, "gh-1")
    result = await command_bus.publish_command(1, "nd-irrig-1", "default", "irrigate", {"duration": 60})
    
    assert result is True
    mqtt.publish_json.assert_called_once()
    call_args = mqtt.publish_json.call_args
    assert "hydro/gh-1/zn-1/nd-irrig-1/default/command" in call_args[0][0]
    assert call_args[0][1]["cmd"] == "irrigate"


@pytest.mark.asyncio
async def test_publish_command_not_connected():
    """Test command publication when MQTT is not connected."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=False)
    
    command_bus = CommandBus(mqtt, "gh-1")
    result = await command_bus.publish_command(1, "nd-irrig-1", "default", "irrigate")
    
    assert result is False
    mqtt.publish_json.assert_not_called()


@pytest.mark.asyncio
async def test_publish_command_exception():
    """Test command publication with exception."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock(side_effect=Exception("MQTT error"))
    
    command_bus = CommandBus(mqtt, "gh-1")
    result = await command_bus.publish_command(1, "nd-irrig-1", "default", "irrigate")
    
    assert result is False


@pytest.mark.asyncio
async def test_publish_controller_command():
    """Test publishing controller command."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock()
    
    command_bus = CommandBus(mqtt, "gh-1")
    command = {
        'node_uid': 'nd-irrig-1',
        'channel': 'default',
        'cmd': 'irrigate',
        'params': {'duration': 60}
    }
    
    result = await command_bus.publish_controller_command(1, command)
    
    assert result is True
    mqtt.publish_json.assert_called_once()


@pytest.mark.asyncio
async def test_publish_controller_command_invalid():
    """Test publishing invalid controller command."""
    mqtt = Mock()
    command_bus = CommandBus(mqtt, "gh-1")
    
    # Missing node_uid
    command = {'channel': 'default', 'cmd': 'irrigate'}
    result = await command_bus.publish_controller_command(1, command)
    assert result is False
    
    # Missing cmd
    command = {'node_uid': 'nd-irrig-1', 'channel': 'default'}
    result = await command_bus.publish_controller_command(1, command)
    assert result is False


@pytest.mark.asyncio
async def test_publish_command_with_params():
    """Test command publication with parameters."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock()
    
    command_bus = CommandBus(mqtt, "gh-1")
    params = {"duration": 60, "intensity": 80}
    result = await command_bus.publish_command(1, "nd-light-1", "white_light", "set_pwm", params)
    
    assert result is True
    call_args = mqtt.publish_json.call_args
    assert call_args[0][1]["cmd"] == "set_pwm"
    assert call_args[0][1]["params"] == params


@pytest.mark.asyncio
async def test_publish_command_without_params():
    """Test command publication without parameters."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    mqtt.publish_json = Mock()
    
    command_bus = CommandBus(mqtt, "gh-1")
    result = await command_bus.publish_command(1, "nd-relay-1", "default", "set_relay")
    
    assert result is True
    call_args = mqtt.publish_json.call_args
    assert call_args[0][1]["cmd"] == "set_relay"
    assert "params" not in call_args[0][1]

