"""Tests for pump_safety module."""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.pump_safety import (
    check_dry_run,
    check_no_flow,
    check_pump_stuck_on,
    can_run_pump,
    get_active_critical_alerts,
    too_many_recent_failures,
    check_mcu_offline,
    get_pump_thresholds,
    MIN_WATER_LEVEL,
    CURRENT_IDLE_THRESHOLD,
    DRY_RUN_CHECK_DELAY_SEC,
)
from common.alerts import AlertCode, AlertSource


@pytest.mark.asyncio
async def test_check_dry_run_safe():
    """Test dry run check when water level is safe."""
    with patch("common.pump_safety.check_water_level") as mock_check:
        mock_check.return_value = (True, 0.5)  # Нормальный уровень
        
        is_safe, error_msg = await check_dry_run(1, MIN_WATER_LEVEL)
        
        assert is_safe is True
        assert error_msg is None


@pytest.mark.asyncio
async def test_check_dry_run_low_water():
    """Test dry run check when water level is too low."""
    with patch("common.pump_safety.check_water_level") as mock_check, \
         patch("common.pump_safety.create_alert") as mock_alert:
        mock_check.return_value = (False, 0.1)  # Низкий уровень
        
        is_safe, error_msg = await check_dry_run(1, MIN_WATER_LEVEL)
        
        assert is_safe is False
        assert error_msg is not None
        assert "Water level too low" in error_msg
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[1]["code"] == AlertCode.BIZ_DRY_RUN.value
        assert call_args[1]["source"] == AlertSource.BIZ.value


@pytest.mark.asyncio
async def test_check_no_flow_early():
    """Test no flow check when pump just started (less than delay)."""
    pump_start_time = utcnow() - timedelta(seconds=1)
    
    is_ok, error_msg = await check_no_flow(1, "pump_recirc", "cmd-1", pump_start_time)
    
    assert is_ok is True
    assert error_msg is None


@pytest.mark.asyncio
async def test_check_no_flow_detected():
    """Test no flow check when no flow detected."""
    pump_start_time = utcnow() - timedelta(seconds=5)
    
    with patch("common.pump_safety.check_flow") as mock_check_flow, \
         patch("common.pump_safety.create_alert") as mock_alert:
        mock_check_flow.return_value = (False, 0.0)  # Нет потока
        
        is_ok, error_msg = await check_no_flow(1, "pump_recirc", "cmd-1", pump_start_time)
        
        assert is_ok is False
        assert error_msg is not None
        assert "NO_FLOW" in error_msg
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[1]["code"] == AlertCode.BIZ_NO_FLOW.value


@pytest.mark.asyncio
async def test_check_no_flow_ok():
    """Test no flow check when flow is normal."""
    pump_start_time = utcnow() - timedelta(seconds=5)
    
    with patch("common.pump_safety.check_flow") as mock_check_flow:
        mock_check_flow.return_value = (True, 2.0)  # Поток нормальный
        
        is_ok, error_msg = await check_no_flow(1, "pump_recirc", "cmd-1", pump_start_time)
        
        assert is_ok is True
        assert error_msg is None


@pytest.mark.asyncio
async def test_check_pump_stuck_on_by_current():
    """Test pump stuck on detection by current."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_pump_thresholds") as mock_thresholds, \
         patch("common.pump_safety.create_alert") as mock_alert:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_thresholds.return_value = {
            "current_min": 0.1,
            "current_max": 2.5,
            "idle_threshold": CURRENT_IDLE_THRESHOLD,
        }
        # Желаемое состояние OFF, но ток > порога
        is_ok, error_msg = await check_pump_stuck_on(
            1, "pump_recirc", "OFF", current_ma=100.0, flow_value=None
        )
        
        assert is_ok is False
        assert error_msg is not None
        assert "Pump stuck ON" in error_msg
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[1]["code"] == AlertCode.BIZ_PUMP_STUCK_ON.value


@pytest.mark.asyncio
async def test_check_pump_stuck_on_by_flow():
    """Test pump stuck on detection by flow."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_pump_thresholds") as mock_thresholds, \
         patch("common.pump_safety.create_alert") as mock_alert:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_thresholds.return_value = {
            "current_min": 0.1,
            "current_max": 2.5,
            "idle_threshold": CURRENT_IDLE_THRESHOLD,
        }
        # Желаемое состояние OFF, но flow > порога
        is_ok, error_msg = await check_pump_stuck_on(
            1, "pump_recirc", "OFF", current_ma=None, flow_value=0.5
        )
        
        assert is_ok is False
        assert error_msg is not None
        assert "Pump stuck ON" in error_msg
        mock_alert.assert_called_once()


@pytest.mark.asyncio
async def test_check_pump_stuck_on_ok():
    """Test pump stuck on check when pump is actually off."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_pump_thresholds") as mock_thresholds:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_thresholds.return_value = {
            "current_min": 0.1,
            "current_max": 2.5,
            "idle_threshold": CURRENT_IDLE_THRESHOLD,
        }
        # Желаемое состояние OFF, ток и flow в норме
        is_ok, error_msg = await check_pump_stuck_on(
            1, "pump_recirc", "OFF", current_ma=10.0, flow_value=0.0
        )
        
        assert is_ok is True
        assert error_msg is None


@pytest.mark.asyncio
async def test_check_pump_stuck_on_desired_on():
    """Test pump stuck on check when desired state is ON."""
    # Если желаемое состояние ON, проверка не выполняется
    is_ok, error_msg = await check_pump_stuck_on(
        1, "pump_recirc", "ON", current_ma=100.0, flow_value=2.0
    )
    
    assert is_ok is True
    assert error_msg is None


@pytest.mark.asyncio
async def test_get_active_critical_alerts():
    """Test getting active critical alerts."""
    mock_alerts = [
        {
            "id": 1,
            "code": AlertCode.BIZ_OVERCURRENT.value,
            "type": "Overcurrent",
            "details": {},
            "created_at": utcnow(),
        },
        {
            "id": 2,
            "code": AlertCode.BIZ_NO_FLOW.value,
            "type": "No flow",
            "details": {},
            "created_at": utcnow(),
        },
    ]
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_alerts
        
        alerts = await get_active_critical_alerts(1)
        
        assert len(alerts) == 2
        assert alerts[0]["code"] == AlertCode.BIZ_OVERCURRENT.value
        assert alerts[1]["code"] == AlertCode.BIZ_NO_FLOW.value


@pytest.mark.asyncio
async def test_too_many_recent_failures():
    """Test checking too many recent failures."""
    mock_failures = [{"count": 4}]  # 4 ошибки >= 3
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_failures
        
        result = await too_many_recent_failures(1, "pump_recirc", max_failures=3, window_minutes=30)
        
        assert result is True


@pytest.mark.asyncio
async def test_too_many_recent_failures_ok():
    """Test checking recent failures when count is normal."""
    mock_failures = [{"count": 1}]  # 1 ошибка < 3
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_failures
        
        result = await too_many_recent_failures(1, "pump_recirc", max_failures=3, window_minutes=30)
        
        assert result is False


@pytest.mark.asyncio
async def test_can_run_pump_with_active_critical_alert():
    """Test can_run_pump when there is active critical alert."""
    mock_alerts = [
        {
            "id": 1,
            "code": AlertCode.BIZ_OVERCURRENT.value,
            "type": "Overcurrent",
            "details": {},
            "created_at": utcnow(),
        }
    ]
    
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_active_critical_alerts") as mock_get_alerts:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_get_alerts.return_value = mock_alerts
        
        can_run, error_msg = await can_run_pump(1, "pump_recirc")
        
        assert can_run is False
        assert "Active critical alert" in error_msg


@pytest.mark.asyncio
async def test_can_run_pump_dry_run():
    """Test can_run_pump when dry run detected."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_active_critical_alerts") as mock_get_alerts, \
         patch("common.pump_safety.check_dry_run") as mock_dry_run:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_get_alerts.return_value = []  # Нет активных алертов
        mock_dry_run.return_value = (False, "Water level too low")
        
        can_run, error_msg = await can_run_pump(1, "pump_recirc")
        
        assert can_run is False
        assert "Water level too low" in error_msg


@pytest.mark.asyncio
async def test_can_run_pump_too_many_failures():
    """Test can_run_pump when too many recent failures."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_active_critical_alerts") as mock_get_alerts, \
         patch("common.pump_safety.check_dry_run") as mock_dry_run, \
         patch("common.pump_safety.too_many_recent_failures") as mock_failures:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_get_alerts.return_value = []
        mock_dry_run.return_value = (True, None)
        mock_failures.return_value = True
        
        can_run, error_msg = await can_run_pump(1, "pump_recirc")
        
        assert can_run is False
        assert "Too many recent failures" in error_msg


@pytest.mark.asyncio
async def test_can_run_pump_ok():
    """Test can_run_pump when all checks pass."""
    with patch("common.pump_safety.get_active_critical_alerts") as mock_get_alerts, \
         patch("common.pump_safety.check_dry_run") as mock_dry_run, \
         patch("common.pump_safety.too_many_recent_failures") as mock_failures, \
         patch("common.pump_safety.check_mcu_offline") as mock_mcu:
        mock_get_alerts.return_value = []
        mock_dry_run.return_value = (True, None)
        mock_failures.return_value = False
        mock_mcu.return_value = (True, None)  # MCU онлайн
        
        can_run, error_msg = await can_run_pump(1, "pump_recirc")
        
        assert can_run is True
        assert error_msg is None


@pytest.mark.asyncio
async def test_check_mcu_offline_online():
    """Test MCU offline check when MCU is online."""
    now = utcnow()
    mock_nodes = [
        {
            "id": 1,
            "status": "online",
            "last_telemetry": now - timedelta(seconds=60),  # Телеметрия 1 минуту назад
        }
    ]
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_nodes
        
        is_online, error_msg = await check_mcu_offline(1)
        
        assert is_online is True
        assert error_msg is None


@pytest.mark.asyncio
async def test_check_mcu_offline_offline():
    """Test MCU offline check when MCU is offline."""
    now = utcnow()
    mock_nodes = [
        {
            "id": 1,
            "status": "online",
            "last_telemetry": now - timedelta(seconds=400),  # Телеметрия 400 секунд назад (> 300)
        }
    ]
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_nodes
        
        is_online, error_msg = await check_mcu_offline(1)
        
        assert is_online is False
        assert error_msg is not None
        assert "offline" in error_msg.lower()


@pytest.mark.asyncio
async def test_check_mcu_offline_no_telemetry():
    """Test MCU offline check when no telemetry data."""
    mock_nodes = [
        {
            "id": 1,
            "status": "online",
            "last_telemetry": None,  # Нет телеметрии
        }
    ]
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_nodes
        
        is_online, error_msg = await check_mcu_offline(1)
        
        assert is_online is False
        assert error_msg is not None
        assert "no telemetry" in error_msg.lower()


@pytest.mark.asyncio
async def test_check_mcu_offline_wrong_status():
    """Test MCU offline check when node status is not online."""
    mock_nodes = [
        {
            "id": 1,
            "status": "offline",
            "last_telemetry": utcnow(),
        }
    ]
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = mock_nodes
        
        is_online, error_msg = await check_mcu_offline(1)
        
        assert is_online is False
        assert error_msg is not None
        assert "status" in error_msg.lower()


@pytest.mark.asyncio
async def test_get_pump_thresholds_from_config():
    """Test getting pump thresholds from node config."""
    mock_config = {
        "config": {
            "limits": {
                "currentMin": 0.2,
                "currentMax": 2.0,
            }
        },
        "channel_config": {},
    }
    
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = [mock_config]
        
        from common.pump_safety import get_pump_thresholds
        thresholds = await get_pump_thresholds(1, "pump_recirc")
        
        assert thresholds["current_min"] == 0.2
        assert thresholds["current_max"] == 2.0
        assert thresholds["idle_threshold"] >= 0.2  # Idle threshold = max(50.0, 2.0 * 0.1) = max(50.0, 0.2) = 50.0


@pytest.mark.asyncio
async def test_get_pump_thresholds_defaults():
    """Test getting pump thresholds with defaults."""
    with patch("common.pump_safety.fetch") as mock_fetch:
        mock_fetch.return_value = []  # Нет конфигурации
        
        from common.pump_safety import get_pump_thresholds
        thresholds = await get_pump_thresholds(1, "pump_recirc")
        
        assert thresholds["current_min"] == 0.1
        assert thresholds["current_max"] == 2.5
        assert thresholds["idle_threshold"] == CURRENT_IDLE_THRESHOLD


@pytest.mark.asyncio
async def test_check_pump_stuck_on_with_thresholds():
    """Test pump stuck on check with thresholds from config."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu, \
         patch("common.pump_safety.get_pump_thresholds") as mock_thresholds, \
         patch("common.pump_safety.create_alert") as mock_alert:
        mock_mcu.return_value = (True, None)  # MCU онлайн
        mock_thresholds.return_value = {
            "current_min": 0.2,
            "current_max": 2.0,
            "idle_threshold": 100.0,  # Кастомный порог
        }
        
        # Ток 120 мА > порога 100 мА
        is_ok, error_msg = await check_pump_stuck_on(
            1, "pump_recirc", "OFF", current_ma=120.0, flow_value=None, node_id=1
        )
        
        assert is_ok is False
        assert "Pump stuck ON" in error_msg
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args[1]["code"] == AlertCode.BIZ_PUMP_STUCK_ON.value
        # Проверяем, что использовался кастомный порог
        assert call_args[1]["details"]["threshold_ma"] == 100.0


@pytest.mark.asyncio
async def test_can_run_pump_mcu_offline():
    """Test can_run_pump when MCU is offline."""
    with patch("common.pump_safety.check_mcu_offline") as mock_mcu:
        mock_mcu.return_value = (False, "Node 1 offline: no telemetry for 400s")
        
        can_run, error_msg = await can_run_pump(1, "pump_recirc")
        
        assert can_run is False
        assert "MCU offline" in error_msg
