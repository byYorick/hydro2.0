"""Tests for light_controller module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import datetime, time

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from light_controller import (
    check_and_control_lighting,
    parse_photoperiod,
    get_light_nodes,
    check_light_failure,
)


def test_parse_photoperiod_string():
    """Test parsing photoperiod from string format."""
    result = parse_photoperiod("06:00-22:00")
    assert result is not None
    start, end = result
    assert start == time(6, 0)
    assert end == time(22, 0)


def test_parse_photoperiod_dict():
    """Test parsing photoperiod from dict format."""
    result = parse_photoperiod({"start": "08:00", "end": "20:00"})
    assert result is not None
    start, end = result
    assert start == time(8, 0)
    assert end == time(20, 0)


def test_parse_photoperiod_hours():
    """Test parsing photoperiod from hours number."""
    result = parse_photoperiod(16)  # 16 часов, начиная с 06:00
    assert result is not None
    start, end = result
    assert start == time(6, 0)
    assert end == time(22, 0)  # 6 + 16 = 22


def test_parse_photoperiod_none():
    """Test parsing photoperiod when None."""
    result = parse_photoperiod(None)
    assert result is None


@pytest.mark.asyncio
async def test_get_light_nodes():
    """Test getting light nodes for zone."""
    with patch("light_controller.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": 1, "uid": "nd-light-1", "type": "light", "channel": "white_light"},
        ]
        
        nodes = await get_light_nodes(1)
        assert len(nodes) > 0
        assert nodes[0]["node_uid"] == "nd-light-1"
        assert nodes[0]["channel"] == "white_light"


@pytest.mark.asyncio
async def test_check_and_control_lighting_on():
    """Test light control when should be on."""
    targets = {"light_hours": "06:00-22:00"}
    current_time = datetime(2025, 1, 1, 12, 0)  # 12:00 - в активном периоде
    
    with patch("light_controller.get_light_nodes") as mock_nodes, \
         patch("light_controller.check_light_failure") as mock_failure:
        mock_nodes.return_value = [
            {"node_uid": "nd-light-1", "channel": "white_light"},
        ]
        mock_failure.return_value = False  # Нет отказа
        
        cmd = await check_and_control_lighting(1, targets, current_time)
        
        assert cmd is not None
        assert cmd["node_uid"] == "nd-light-1"
        assert cmd["event_type"] == "LIGHT_ON"
        assert cmd["cmd"] in ["set_relay", "set_pwm"]


@pytest.mark.asyncio
async def test_check_and_control_lighting_off():
    """Test light control when should be off."""
    targets = {"light_hours": "06:00-22:00"}
    current_time = datetime(2025, 1, 1, 23, 0)  # 23:00 - вне активного периода
    
    with patch("light_controller.get_light_nodes") as mock_nodes, \
         patch("light_controller.check_light_failure") as mock_failure:
        mock_nodes.return_value = [
            {"node_uid": "nd-light-1", "channel": "white_light"},
        ]
        mock_failure.return_value = False
        
        cmd = await check_and_control_lighting(1, targets, current_time)
        
        assert cmd is not None
        assert cmd["event_type"] == "LIGHT_OFF"
        assert cmd["cmd"] == "set_relay"
        assert cmd["params"]["state"] is False


@pytest.mark.asyncio
async def test_check_and_control_lighting_with_intensity():
    """Test light control with intensity setting."""
    targets = {"light_hours": "06:00-22:00", "light_intensity": 75}
    current_time = datetime(2025, 1, 1, 12, 0)
    
    with patch("light_controller.get_light_nodes") as mock_nodes, \
         patch("light_controller.check_light_failure") as mock_failure:
        mock_nodes.return_value = [
            {"node_uid": "nd-light-1", "channel": "white_light"},
        ]
        mock_failure.return_value = False
        
        cmd = await check_and_control_lighting(1, targets, current_time)
        
        assert cmd is not None
        assert cmd["cmd"] == "set_pwm"
        assert cmd["params"]["value"] == 75


@pytest.mark.asyncio
async def test_check_light_failure_detected():
    """Test light failure detection."""
    with patch("light_controller.fetch") as mock_fetch:
        # Свет должен быть включен, но показания низкие
        mock_fetch.return_value = [{"value": 5.0}]  # 5 lux - очень низко
        
        failure = await check_light_failure(1, should_be_on=True)
        assert failure is True


@pytest.mark.asyncio
async def test_check_light_failure_normal():
    """Test light failure when light is working normally."""
    with patch("light_controller.fetch") as mock_fetch:
        # Свет включен и показания нормальные
        mock_fetch.return_value = [{"value": 500.0}]  # 500 lux - нормально
        
        failure = await check_light_failure(1, should_be_on=True)
        assert failure is False


@pytest.mark.asyncio
async def test_check_light_failure_should_be_off():
    """Test light failure check when light should be off."""
    # Если свет должен быть выключен, не проверяем отказ
    failure = await check_light_failure(1, should_be_on=False)
    assert failure is False

