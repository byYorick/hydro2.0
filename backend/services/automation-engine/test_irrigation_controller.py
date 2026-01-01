"""Tests for irrigation_controller module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from irrigation_controller import (
    check_and_control_irrigation,
    get_last_irrigation_time,
    get_last_recirculation_time,
    check_and_control_recirculation,
)


@pytest.mark.asyncio
async def test_get_last_irrigation_time():
    """Test getting last irrigation time."""
    last_time = datetime.utcnow() - timedelta(hours=2)
    
    with patch("irrigation_controller.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"created_at": last_time}
        ]
        
        result = await get_last_irrigation_time(1)
        assert result is not None
        assert isinstance(result, datetime)


@pytest.mark.asyncio
async def test_check_and_control_irrigation_interval_reached():
    """Test irrigation when interval is reached."""
    targets = {
        "irrigation": {"interval_sec": 3600, "duration_sec": 60},  # 1 час, 1 минута
    }
    telemetry = {}
    bindings = {}
    actuators = {
        "irrigation_pump": {"node_uid": "nd-irrig-1", "channel": "pump_irrigation"}
    }
    
    # Последний полив был 2 часа назад
    last_irrigation_time = datetime.utcnow() - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_irrigation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level:
        mock_last_time.return_value = last_irrigation_time
        mock_water_level.return_value = (True, 0.5)  # Уровень воды нормальный
        
        cmd = await check_and_control_irrigation(1, targets, telemetry, bindings, actuators)
        
        # Должен вернуть команду на полив
        assert cmd is not None
        assert cmd["node_uid"] == "nd-irrig-1"
        assert cmd["cmd"] == "run_pump"
        assert cmd["params"]["duration_ms"] == 60000
        assert cmd["event_type"] == "IRRIGATION_STARTED"


@pytest.mark.asyncio
async def test_check_and_control_irrigation_interval_not_reached():
    """Test irrigation when interval is not reached."""
    targets = {
        "irrigation": {"interval_sec": 3600, "duration_sec": 60},  # 1 час
    }
    telemetry = {}
    
    # Последний полив был 30 минут назад
    last_irrigation_time = datetime.utcnow() - timedelta(minutes=30)
    
    with patch("irrigation_controller.get_last_irrigation_time") as mock_last_time, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        mock_last_time.return_value = last_irrigation_time
        
        cmd = await check_and_control_irrigation(1, targets, telemetry, {}, {})
        
        # Не должен возвращать команду
        assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_irrigation_water_level_low():
    """Test irrigation blocked when water level is low."""
    targets = {
        "irrigation": {"interval_sec": 3600, "duration_sec": 60},
    }
    telemetry = {}
    
    last_irrigation_time = datetime.utcnow() - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_irrigation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        mock_last_time.return_value = last_irrigation_time
        mock_water_level.return_value = (False, 0.15)  # Низкий уровень воды
        
        cmd = await check_and_control_irrigation(1, targets, telemetry, {}, {})
        
        # Не должен возвращать команду из-за низкого уровня воды
        assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_irrigation_no_nodes():
    """Test irrigation when no irrigation nodes available."""
    targets = {
        "irrigation": {"interval_sec": 3600, "duration_sec": 60},
    }
    telemetry = {}
    
    last_irrigation_time = datetime.utcnow() - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_irrigation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        mock_last_time.return_value = last_irrigation_time
        mock_water_level.return_value = (True, 0.5)
        
        cmd = await check_and_control_irrigation(1, targets, telemetry, {}, {})
        
        # Не должен возвращать команду без actuator
        assert cmd is None


@pytest.mark.asyncio
async def test_get_last_recirculation_time():
    """Test getting last recirculation time."""
    last_time = datetime.utcnow() - timedelta(hours=2)
    
    with patch("irrigation_controller.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"created_at": last_time}
        ]
        
        result = await get_last_recirculation_time(1)
        assert result is not None
        assert isinstance(result, datetime)


@pytest.mark.asyncio
async def test_get_last_recirculation_time_no_events():
    """Test getting last recirculation time when no events exist."""
    with patch("irrigation_controller.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await get_last_recirculation_time(1)
        assert result is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_enabled_interval_reached():
    """Test recirculation when enabled and interval is reached."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,  # 1 час
        "recirculation_duration_sec": 300,  # 5 минут
    }
    
    telemetry = {}  # Не используется в тесте, но требуется для совместимости
    actuators = {"recirculation_pump": {"node_uid": "nd-recirc-1", "channel": "recirculation_pump"}}
    
    # Последняя рециркуляция была 2 часа назад (с timezone)
    from datetime import timezone
    last_recirculation_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_recirculation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level:
        
        mock_last_time.return_value = last_recirculation_time
        mock_water_level.return_value = (True, 0.5)  # Уровень воды нормальный
        
        cmd = await check_and_control_recirculation(1, targets, telemetry, {}, actuators)
        
        # Должен вернуть команду на рециркуляцию
        assert cmd is not None
        assert cmd["node_uid"] == "nd-recirc-1"
        assert cmd["cmd"] == "run_pump"
        assert cmd["params"]["duration_ms"] == 300000
        assert cmd["event_type"] == "RECIRCULATION_CYCLE"


@pytest.mark.asyncio
async def test_check_and_control_recirculation_disabled():
    """Test recirculation when disabled."""
    targets = {
        "recirculation_enabled": False,
        "recirculation_interval_min": 60,
        "recirculation_duration_sec": 300,
    }
    
    telemetry = {}
    
    cmd = await check_and_control_recirculation(1, targets, telemetry, {}, {})
    
    # Не должен возвращать команду
    assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_interval_not_reached():
    """Test recirculation when interval is not reached."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,  # 1 час
        "recirculation_duration_sec": 300,
    }
    
    telemetry = {}
    
    # Последняя рециркуляция была 30 минут назад (с timezone)
    from datetime import timezone
    last_recirculation_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=30)
    
    with patch("irrigation_controller.get_last_recirculation_time") as mock_last_time, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        mock_last_time.return_value = last_recirculation_time
        cmd = await check_and_control_recirculation(1, targets, telemetry, {}, {})
        
        # Не должен возвращать команду
        assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_no_interval():
    """Test recirculation when interval is not specified."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_duration_sec": 300,
        # recirculation_interval_min отсутствует
    }
    
    telemetry = {}
    
    cmd = await check_and_control_recirculation(1, targets, telemetry, {}, {})
    
    # Не должен возвращать команду
    assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_water_level_low():
    """Test recirculation blocked when water level is low."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,
        "recirculation_duration_sec": 300,
    }
    
    telemetry = {}
    
    from datetime import timezone
    last_recirculation_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_recirculation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        
        mock_last_time.return_value = last_recirculation_time
        mock_water_level.return_value = (False, 0.15)  # Низкий уровень воды
        
        cmd = await check_and_control_recirculation(
            1,
            targets,
            telemetry,
            {},
            {"recirculation_pump": {"node_uid": "nd-recirc-1", "channel": "recirculation_pump"}}
        )
        
        # Не должен возвращать команду из-за низкого уровня воды
        assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_no_nodes():
    """Test recirculation when no recirculation nodes available."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,
        "recirculation_duration_sec": 300,
    }
    
    telemetry = {}
    
    from datetime import timezone
    last_recirculation_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=2)
    
    with patch("irrigation_controller.get_last_recirculation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        
        mock_last_time.return_value = last_recirculation_time
        mock_water_level.return_value = (True, 0.5)
        
        cmd = await check_and_control_recirculation(1, targets, telemetry, {}, {})
        
        # Не должен возвращать команду
        assert cmd is None


@pytest.mark.asyncio
async def test_check_and_control_recirculation_first_time():
    """Test recirculation when it's the first time (no previous recirculation)."""
    targets = {
        "recirculation_enabled": True,
        "recirculation_interval_min": 60,
        "recirculation_duration_sec": 300,
    }
    
    telemetry = {}
    
    with patch("irrigation_controller.get_last_recirculation_time") as mock_last_time, \
         patch("irrigation_controller.check_water_level") as mock_water_level, \
         patch("irrigation_controller.ensure_alert", new_callable=AsyncMock):
        
        mock_last_time.return_value = None  # Нет предыдущей рециркуляции
        mock_water_level.return_value = (True, 0.5)
        
        cmd = await check_and_control_recirculation(
            1,
            targets,
            telemetry,
            {},
            {"recirculation_pump": {"node_uid": "nd-recirc-1", "channel": "recirculation_pump"}}
        )
        
        # Должен вернуть команду (первая рециркуляция)
        assert cmd is not None
        assert cmd["cmd"] == "run_pump"
        assert cmd["params"]["duration_ms"] == 300000
