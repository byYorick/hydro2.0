"""Tests for light_controller module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from light_controller import (
    check_and_control_lighting,
    check_light_failure,
)


@pytest.mark.asyncio
async def test_check_and_control_lighting_on():
    """Test light control when should be on."""
    targets = {"lighting": {"photoperiod_hours": 16, "start_time": "06:00"}}
    current_time = datetime(2025, 1, 1, 12, 0)  # 12:00 - в активном периоде
    bindings = {
        "light": {
            "node_id": 201,
            "node_uid": "nd-light-1",
            "channel": "white_light",
            "direction": "actuator",
            "asset_type": "light",
        }
    }
    
    with patch("light_controller.check_light_failure") as mock_failure:
        mock_failure.return_value = False  # Нет отказа
        
        cmd = await check_and_control_lighting(1, targets, bindings, current_time)
        
        assert cmd is not None
        assert cmd["node_uid"] == "nd-light-1"
        assert cmd["event_type"] == "LIGHT_ON"
        assert cmd["cmd"] in ["set_relay", "set_pwm"]


@pytest.mark.asyncio
async def test_check_and_control_lighting_off():
    """Test light control when should be off."""
    targets = {"lighting": {"photoperiod_hours": 16, "start_time": "06:00"}}
    current_time = datetime(2025, 1, 1, 23, 0)  # 23:00 - вне активного периода
    bindings = {
        "light": {
            "node_id": 201,
            "node_uid": "nd-light-1",
            "channel": "white_light",
            "direction": "actuator",
            "asset_type": "light",
        }
    }
    
    with patch("light_controller.check_light_failure") as mock_failure:
        mock_failure.return_value = False
        
        cmd = await check_and_control_lighting(1, targets, bindings, current_time)
        
        assert cmd is not None
        assert cmd["event_type"] == "LIGHT_OFF"
        assert cmd["cmd"] == "set_relay"
        assert cmd["params"]["state"] is False


@pytest.mark.asyncio
async def test_check_and_control_lighting_with_intensity():
    """Test light control with intensity setting."""
    targets = {
        "lighting": {
            "photoperiod_hours": 16,
            "start_time": "06:00",
            "intensity": 75,
        }
    }
    current_time = datetime(2025, 1, 1, 12, 0)
    bindings = {
        "light": {
            "node_id": 201,
            "node_uid": "nd-light-1",
            "channel": "white_light",
            "direction": "actuator",
            "asset_type": "light",
        }
    }
    
    with patch("light_controller.check_light_failure") as mock_failure:
        mock_failure.return_value = False
        
        cmd = await check_and_control_lighting(1, targets, bindings, current_time)
        
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
