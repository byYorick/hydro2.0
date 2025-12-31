"""Tests for controllers with bindings support."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Mock common modules before importing controllers
sys.modules['common'] = MagicMock()
sys.modules['common.db'] = MagicMock()
sys.modules['common.utils'] = MagicMock()
sys.modules['common.utils.time'] = MagicMock()
sys.modules['common.water_flow'] = MagicMock()
sys.modules['common.alerts'] = MagicMock()

from climate_controller import (
    check_and_control_climate,
    get_climate_bindings,
)
from irrigation_controller import (
    check_and_control_irrigation,
    get_irrigation_binding,
    get_recirculation_binding,
    check_and_control_recirculation,
)
from light_controller import (
    check_and_control_lighting,
    get_light_bindings,
)


def test_get_climate_bindings():
    """Test getting climate bindings from role-based bindings."""
    bindings = {
        "vent": {
            "node_id": 1,
            "node_uid": "nd-climate-1",
            "channel": "fan_A",
            "asset_type": "VENT",
            "direction": "actuator",
        },
        "heater": {
            "node_id": 2,
            "node_uid": "nd-climate-1",
            "channel": "heater_1",
            "asset_type": "HEATER",
            "direction": "actuator",
        },
        "climate_sensor": {
            "node_id": 3,
            "node_uid": "nd-climate-1",
            "channel": "temperature",
            "asset_type": "SENSOR",
            "direction": "sensor",
        },
    }
    
    result = get_climate_bindings(1, bindings)
    
    assert result["fan"] is not None
    assert result["heater"] is not None
    assert result["climate_sensor"] is not None
    assert result["fan"]["node_uid"] == "nd-climate-1"
    assert result["fan"]["channel"] == "fan_A"
    assert result["heater"]["channel"] == "heater_1"


def test_get_climate_bindings_missing():
    """Test getting climate bindings when some are missing."""
    bindings = {
        "vent": {
            "node_id": 1,
            "node_uid": "nd-climate-1",
            "channel": "fan_A",
            "asset_type": "VENT",
            "direction": "actuator",
        },
    }
    
    result = get_climate_bindings(1, bindings)
    
    assert result["fan"] is not None
    assert result["heater"] is None
    assert result["climate_sensor"] is None


@pytest.mark.asyncio
async def test_check_and_control_climate_with_bindings():
    """Test climate control using bindings."""
    targets = {"temp_air": 25.0, "humidity_air": 60.0}
    telemetry = {"TEMPERATURE": 22.0, "HUMIDITY": 55.0}
    bindings = {
        "vent": {
            "node_id": 1,
            "node_uid": "nd-climate-1",
            "channel": "fan_A",
            "asset_type": "VENT",
            "direction": "actuator",
        },
        "heater": {
            "node_id": 2,
            "node_uid": "nd-climate-1",
            "channel": "heater_1",
            "asset_type": "HEATER",
            "direction": "actuator",
        },
    }
    
    with patch("climate_controller.check_temp_alerts", new_callable=AsyncMock) as mock_temp_alerts, \
         patch("climate_controller.check_humidity_alerts", new_callable=AsyncMock) as mock_hum_alerts, \
         patch("climate_controller.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_temp_alerts.return_value = None
        mock_hum_alerts.return_value = None
        
        commands = await check_and_control_climate(1, targets, telemetry, bindings)
        
        # Должен включить нагреватель (temp 22 < target 25)
        assert len(commands) > 0
        heater_cmd = next((c for c in commands if c.get("channel") == "heater_1"), None)
        assert heater_cmd is not None
        assert heater_cmd["cmd"] == "set_relay"
        assert heater_cmd["params"]["state"] is True
        assert heater_cmd["event_type"] == "CLIMATE_HEATING_ON"


@pytest.mark.asyncio
async def test_check_and_control_climate_missing_binding():
    """Test climate control when binding is missing - should create alert."""
    targets = {"temp_air": 25.0}
    telemetry = {"TEMPERATURE": 22.0}
    bindings = {}  # No bindings
    
    with patch("climate_controller.check_temp_alerts", new_callable=AsyncMock) as mock_temp_alerts, \
         patch("climate_controller.ensure_alert", new_callable=AsyncMock) as mock_ensure_alert:
        mock_temp_alerts.return_value = None
        
        commands = await check_and_control_climate(1, targets, telemetry, bindings)
        
        # Должен создать alert для missing binding
        mock_ensure_alert.assert_called()
        call_args_list = mock_ensure_alert.call_args_list
        # Проверяем, что был вызов с MISSING_BINDING
        missing_binding_calls = [
            call for call in call_args_list
            if len(call[0]) > 1 and call[0][1] == "MISSING_BINDING"
        ]
        assert len(missing_binding_calls) > 0


def test_get_irrigation_binding():
    """Test getting irrigation binding from role-based bindings."""
    bindings = {
        "main_pump": {
            "node_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "pump_1",
            "asset_type": "PUMP",
            "direction": "actuator",
        },
    }
    
    result = get_irrigation_binding(bindings)
    
    assert result is not None
    assert result["node_uid"] == "nd-irrig-1"
    assert result["channel"] == "pump_1"


def test_get_irrigation_binding_alternative_roles():
    """Test getting irrigation binding with alternative role names."""
    bindings = {
        "irrigation_pump": {
            "node_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "pump_1",
            "asset_type": "PUMP",
            "direction": "actuator",
        },
    }
    
    result = get_irrigation_binding(bindings)
    
    assert result is not None
    assert result["node_uid"] == "nd-irrig-1"


@pytest.mark.asyncio
async def test_check_and_control_irrigation_with_bindings():
    """Test irrigation control using bindings."""
    targets = {"irrigation_interval_sec": 3600, "irrigation_duration_sec": 60}
    telemetry = {}
    bindings = {
        "main_pump": {
            "node_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "pump_1",
            "asset_type": "PUMP",
            "direction": "actuator",
        },
    }
    
    with patch("irrigation_controller.get_last_irrigation_time", new_callable=AsyncMock) as mock_last_time, \
         patch("irrigation_controller.check_water_level", new_callable=AsyncMock) as mock_water_level:
        # Последний полив был 2 часа назад (больше интервала)
        mock_last_time.return_value = datetime.now(timezone.utc).replace(hour=10, minute=0)
        mock_water_level.return_value = (True, 50.0)  # water_level_ok = True
        
        # Мокаем текущее время
        with patch("irrigation_controller.utcnow") as mock_now:
            mock_now.return_value = datetime.now(timezone.utc).replace(hour=12, minute=0)
            
            result = await check_and_control_irrigation(1, targets, telemetry, bindings)
            
            assert result is not None
            assert result["node_uid"] == "nd-irrig-1"
            assert result["channel"] == "pump_1"
            assert result["cmd"] == "run_pump"
            assert result["params"]["duration_ms"] == 60000


@pytest.mark.asyncio
async def test_check_and_control_irrigation_missing_binding():
    """Test irrigation control when binding is missing - should create alert."""
    targets = {"irrigation_interval_sec": 3600}
    telemetry = {}
    bindings = {}  # No bindings
    
    with patch("irrigation_controller.ensure_alert", new_callable=AsyncMock) as mock_ensure_alert:
        result = await check_and_control_irrigation(1, targets, telemetry, bindings)
        
        assert result is None
        # Должен создать alert для missing binding
        mock_ensure_alert.assert_called_once_with(
            1,
            "MISSING_BINDING",
            {
                "binding_role": "main_pump",
                "required_for": "irrigation_control",
            }
        )


def test_get_recirculation_binding():
    """Test getting recirculation binding from role-based bindings."""
    bindings = {
        "recirculation_pump": {
            "node_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "recirculation_pump",
            "asset_type": "PUMP",
            "direction": "actuator",
        },
    }
    
    result = get_recirculation_binding(bindings)
    
    assert result is not None
    assert result["node_uid"] == "nd-irrig-1"
    assert result["channel"] == "recirculation_pump"


@pytest.mark.asyncio
async def test_check_and_control_recirculation_missing_binding():
    """Test recirculation control when binding is missing - should create alert."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,
        "recirculation_duration_sec": 300,
    }
    telemetry = {}
    bindings = {}  # No bindings
    
    with patch("irrigation_controller.ensure_alert", new_callable=AsyncMock) as mock_ensure_alert:
        result = await check_and_control_recirculation(1, targets, telemetry, bindings)
        
        assert result is None
        # Должен создать alert для missing binding
        mock_ensure_alert.assert_called_once_with(
            1,
            "MISSING_BINDING",
            {
                "binding_role": "recirculation_pump",
                "required_for": "recirculation_control",
            }
        )


def test_get_light_bindings():
    """Test getting light bindings from role-based bindings."""
    bindings = {
        "light": {
            "node_id": 1,
            "node_uid": "nd-light-1",
            "channel": "white_light",
            "asset_type": "LIGHT",
            "direction": "actuator",
        },
        "uv_light": {
            "node_id": 2,
            "node_uid": "nd-light-2",  # Different node_uid to test multiple bindings
            "channel": "uv_light",
            "asset_type": "LIGHT",
            "direction": "actuator",
        },
    }
    
    result = get_light_bindings(bindings)
    
    assert len(result) == 2
    assert result[0]["node_uid"] == "nd-light-1"
    assert result[0]["channel"] == "white_light"
    assert result[1]["channel"] == "uv_light"


@pytest.mark.asyncio
async def test_check_and_control_lighting_with_bindings():
    """Test light control using bindings."""
    targets = {"light_hours": 16}  # 16 hours starting from 06:00
    bindings = {
        "light": {
            "node_id": 1,
            "node_uid": "nd-light-1",
            "channel": "white_light",
            "asset_type": "LIGHT",
            "direction": "actuator",
        },
    }
    
    # Мокаем текущее время - 12:00 (внутри периода 06:00-22:00)
    with patch("light_controller.utcnow") as mock_now, \
         patch("light_controller.check_light_failure", new_callable=AsyncMock) as mock_failure, \
         patch("light_controller.ensure_light_failure_alert", new_callable=AsyncMock) as mock_alert, \
         patch("light_controller.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_failure.return_value = False
        mock_fetch.return_value = []
        
        result = await check_and_control_lighting(1, targets, bindings)
        
        assert result is not None
        assert result["node_uid"] == "nd-light-1"
        assert result["channel"] == "white_light"
        assert result["cmd"] == "set_relay"
        assert result["params"]["state"] is True
        assert result["event_type"] == "LIGHT_ON"


@pytest.mark.asyncio
async def test_check_and_control_lighting_missing_binding():
    """Test light control when binding is missing - should create alert."""
    targets = {"light_hours": 16}
    bindings = {}  # No bindings
    
    with patch("light_controller.utcnow") as mock_now, \
         patch("light_controller.ensure_alert", new_callable=AsyncMock) as mock_ensure_alert:
        mock_now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        result = await check_and_control_lighting(1, targets, bindings)
        
        assert result is None
        # Должен создать alert для missing binding
        mock_ensure_alert.assert_called_once_with(
            1,
            "MISSING_BINDING",
            {
                "binding_role": "light",
                "required_for": "light_control",
            }
        )
