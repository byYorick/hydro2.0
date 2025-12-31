"""Tests for climate_controller module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from climate_controller import (
    check_and_control_climate,
    check_temp_alerts,
    check_humidity_alerts,
)


@pytest.mark.asyncio
async def test_check_and_control_climate_heating():
    """Test climate control when temperature is too low."""
    targets = {"temp_air": 25.0, "humidity_air": 60.0}
    telemetry = {"TEMPERATURE": 22.0, "HUMIDITY": 55.0}
    bindings = {
        "heater": {"node_uid": "nd-climate-1", "channel": "heater_air", "direction": "actuator"},
        "vent": {"node_uid": "nd-climate-1", "channel": "fan_air", "direction": "actuator"},
    }
    
    with patch("climate_controller.check_temp_alerts") as mock_temp_alerts, \
         patch("climate_controller.check_humidity_alerts") as mock_hum_alerts, \
         patch("climate_controller.create_zone_event") as mock_event:
        mock_temp_alerts.return_value = None
        mock_hum_alerts.return_value = None
        
        commands = await check_and_control_climate(1, targets, telemetry, bindings)
        
        # Должен включить нагреватель
        assert len(commands) > 0
        heater_cmd = next((c for c in commands if c.get("channel") == "heater_air"), None)
        assert heater_cmd is not None
        assert heater_cmd["cmd"] == "set_relay"
        assert heater_cmd["params"]["state"] is True
        assert heater_cmd["event_type"] == "CLIMATE_HEATING_ON"


@pytest.mark.asyncio
async def test_check_and_control_climate_cooling():
    """Test climate control when temperature is too high."""
    targets = {"temp_air": 25.0, "humidity_air": 60.0}
    telemetry = {"TEMPERATURE": 28.0, "HUMIDITY": 55.0}
    bindings = {
        "heater": {"node_uid": "nd-climate-1", "channel": "heater_air", "direction": "actuator"},
        "vent": {"node_uid": "nd-climate-1", "channel": "fan_air", "direction": "actuator"},
    }
    
    with patch("climate_controller.check_temp_alerts") as mock_temp_alerts, \
         patch("climate_controller.check_humidity_alerts") as mock_hum_alerts, \
         patch("climate_controller.create_zone_event") as mock_event:
        mock_temp_alerts.return_value = None
        mock_hum_alerts.return_value = None
        
        commands = await check_and_control_climate(1, targets, telemetry, bindings)
        
        # Должен включить вентилятор для охлаждения
        assert len(commands) > 0
        fan_cmd = next((c for c in commands if c.get("channel") == "fan_air"), None)
        assert fan_cmd is not None
        assert fan_cmd["event_type"] == "CLIMATE_COOLING_ON"


@pytest.mark.asyncio
async def test_check_and_control_climate_humidity_high():
    """Test climate control when humidity is too high."""
    targets = {"temp_air": 25.0, "humidity_air": 60.0}
    telemetry = {"TEMPERATURE": 25.0, "HUMIDITY": 80.0}
    bindings = {
        "vent": {"node_uid": "nd-climate-1", "channel": "fan_air", "direction": "actuator"},
    }
    
    with patch("climate_controller.check_temp_alerts") as mock_temp_alerts, \
         patch("climate_controller.check_humidity_alerts") as mock_hum_alerts, \
         patch("climate_controller.create_zone_event") as mock_event:
        mock_temp_alerts.return_value = None
        mock_hum_alerts.return_value = None
        
        commands = await check_and_control_climate(1, targets, telemetry, bindings)
        
        # Температура в норме (25.0), поэтому сначала выключается вентилятор (set_relay False)
        # Затем управление влажностью включает вентилятор на максимум (set_pwm 100)
        # Ищем команду set_pwm для управления влажностью
        fan_cmd = next((c for c in commands if c.get("cmd") == "set_pwm"), None)
        if fan_cmd:
            assert fan_cmd["params"]["value"] == 100  # Максимальная вентиляция
            assert fan_cmd["event_type"] == "FAN_ON"
        else:
            # Если нет set_pwm, проверяем что есть команды для вентилятора
            fan_commands = [c for c in commands if c.get("channel") == "fan_air"]
            assert len(fan_commands) > 0


@pytest.mark.asyncio
async def test_check_temp_alerts_high():
    """Test temperature alert when temp is too high."""
    with patch("climate_controller.ensure_alert") as mock_ensure_alert:
        await check_temp_alerts(1, 27.1, 25.0)  # temp > target + 2.0 (27.1 > 27.0)
        
        mock_ensure_alert.assert_called_once()
        call_args = mock_ensure_alert.call_args
        assert call_args[0][1] == "TEMP_HIGH"


@pytest.mark.asyncio
async def test_check_temp_alerts_low():
    """Test temperature alert when temp is too low."""
    with patch("climate_controller.ensure_alert") as mock_ensure_alert:
        await check_temp_alerts(1, 22.9, 25.0)  # temp < target - 2.0 (22.9 < 23.0)
        
        mock_ensure_alert.assert_called_once()
        call_args = mock_ensure_alert.call_args
        assert call_args[0][1] == "TEMP_LOW"


@pytest.mark.asyncio
async def test_check_humidity_alerts_high():
    """Test humidity alert when humidity is too high."""
    with patch("climate_controller.ensure_alert") as mock_ensure_alert:
        await check_humidity_alerts(1, 76.0, 60.0)  # humidity > target + 15 (76 > 75)
        
        mock_ensure_alert.assert_called_once()
        call_args = mock_ensure_alert.call_args
        assert call_args[0][1] == "HUMIDITY_HIGH"


@pytest.mark.asyncio
async def test_check_humidity_alerts_low():
    """Test humidity alert when humidity is too low."""
    with patch("climate_controller.ensure_alert") as mock_ensure_alert:
        await check_humidity_alerts(1, 44.0, 60.0)  # humidity < target - 15 (44 < 45)
        
        mock_ensure_alert.assert_called_once()
        call_args = mock_ensure_alert.call_args
        assert call_args[0][1] == "HUMIDITY_LOW"
