"""Tests for scheduler."""
import pytest
from datetime import time, datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from main import (
    _parse_time_spec,
    get_active_schedules,
    get_zone_nodes_for_type,
    execute_irrigation_schedule,
    monitor_pump_safety,
)


def test_parse_time_spec():
    """Test parsing time spec."""
    assert _parse_time_spec("08:00") == time(8, 0)
    assert _parse_time_spec("14:30") == time(14, 30)
    assert _parse_time_spec("invalid") is None
    assert _parse_time_spec("25:00") is None


@pytest.mark.asyncio
async def test_get_active_schedules():
    """Test fetching active schedules."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "zone_id": 1,
                "current_phase_index": 0,
                "targets": {
                    "ph": 6.5,
                    "irrigation_schedule": ["08:00", "14:00", "20:00"],
                    "lighting_schedule": "06:00-22:00",
                },
                "status": "online",
            }
        ]
        schedules = await get_active_schedules()
        assert len(schedules) > 0
        irrigation_schedules = [s for s in schedules if s["type"] == "irrigation"]
        assert len(irrigation_schedules) == 3  # Three irrigation times
        lighting_schedules = [s for s in schedules if s["type"] == "lighting"]
        assert len(lighting_schedules) == 1  # One lighting window


@pytest.mark.asyncio
async def test_get_zone_nodes_for_type():
    """Test fetching zone nodes by type."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-irrig-1",
                "type": "irrigation",
                "channel": "pump1",  # Исправлено: должно быть "channel", а не "channel_name"
            }
        ]
        nodes = await get_zone_nodes_for_type(1, "irrigation")
        assert len(nodes) == 1
        assert nodes[0]["node_uid"] == "nd-irrig-1"
        assert nodes[0]["type"] == "irrigation"
        assert nodes[0]["channel"] == "pump1"


@pytest.mark.asyncio
async def test_execute_irrigation_schedule():
    """Test executing irrigation schedule."""
    mqtt = Mock()
    mqtt.publish_json = Mock()
    
    with patch("main.get_zone_nodes_for_type") as mock_nodes, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("main.check_water_level") as mock_water, \
         patch("main.check_flow") as mock_flow, \
         patch("main.calculate_irrigation_volume") as mock_volume, \
         patch("main.create_zone_event") as mock_event:
        
        mock_nodes.return_value = [
            {
                "node_uid": "nd-irrig-1",
                "channel": "pump1",
                "type": "irrigation",
            }
        ]
        mock_water.return_value = (True, 0.5)
        mock_flow.return_value = (True, 2.0)
        mock_volume.return_value = 10.0
        
        await execute_irrigation_schedule(1, mqtt, "gh-1", {})
        
        # Should publish irrigation command
        assert mqtt.publish_json.called
        # Проверяем, что была отправлена команда irrigate
        irrigate_calls = [call for call in mqtt.publish_json.call_args_list 
                         if len(call[0]) > 1 and isinstance(call[0][1], dict) and call[0][1].get("cmd") == "irrigate"]
        assert len(irrigate_calls) > 0


@pytest.mark.asyncio
async def test_monitor_pump_safety_safe():
    """Test pump safety monitoring when flow is normal."""
    mqtt = Mock()
    mqtt.publish_json = Mock()
    pump_start_time = datetime.utcnow() - timedelta(seconds=5)
    
    with patch("main.check_dry_run_protection") as mock_check, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("asyncio.sleep") as mock_sleep:
        
        mock_check.return_value = (True, None)  # Безопасно
        mock_sleep.return_value = None
        
        await monitor_pump_safety(1, pump_start_time, mqtt, "gh-1", "nd-irrig-1", "pump1")
        
        # Не должна быть отправлена команда остановки
        # mqtt.publish_json вызывается с (topic, payload, ...)
        stop_calls = [call for call in mqtt.publish_json.call_args_list 
                     if len(call[0]) > 1 and isinstance(call[0][1], dict) and call[0][1].get("cmd") == "stop"]
        assert len(stop_calls) == 0
        
        # Не должно быть создано событие PUMP_STOPPED
        pump_stopped_calls = [call for call in mock_event.call_args_list
                             if len(call[0]) > 1 and call[0][1] == "PUMP_STOPPED"]
        assert len(pump_stopped_calls) == 0


@pytest.mark.asyncio
async def test_monitor_pump_safety_dry_run():
    """Test pump safety monitoring when dry run detected."""
    mqtt = Mock()
    mqtt.publish_json = Mock()
    pump_start_time = datetime.utcnow() - timedelta(seconds=5)
    
    with patch("main.check_dry_run_protection") as mock_check, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("asyncio.sleep") as mock_sleep:
        
        mock_check.return_value = (False, "NO_FLOW detected: flow=0.0 L/min")
        mock_sleep.return_value = None
        
        await monitor_pump_safety(1, pump_start_time, mqtt, "gh-1", "nd-irrig-1", "pump1")
        
        # Должна быть отправлена команда остановки
        # mqtt.publish_json вызывается с (topic, payload, ...)
        stop_calls = [call for call in mqtt.publish_json.call_args_list 
                     if len(call[0]) > 1 and isinstance(call[0][1], dict) and call[0][1].get("cmd") == "stop"]
        assert len(stop_calls) > 0
        
        # Должно быть создано событие PUMP_STOPPED
        pump_stopped_calls = [call for call in mock_event.call_args_list
                             if len(call[0]) > 1 and call[0][1] == "PUMP_STOPPED"]
        assert len(pump_stopped_calls) == 1
        
        # Должен быть обновлен scheduler log
        mock_log.assert_called_once()

