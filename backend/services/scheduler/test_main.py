"""Tests for scheduler."""
import pytest
from datetime import time, datetime, timedelta, timezone
from common.utils.time import utcnow
from unittest.mock import Mock, patch, AsyncMock
import httpx
import sys
import types
from main import (
    _parse_time_spec,
    _extract_simulation_clock,
    _schedule_crossings,
    get_active_schedules,
    get_zone_nodes_for_type,
    execute_irrigation_schedule,
    execute_lighting_schedule,
    check_and_execute_schedules,
    monitor_pump_safety,
    send_command_via_automation_engine,
)


def test_parse_time_spec():
    """Test parsing time spec."""
    assert _parse_time_spec("08:00") == time(8, 0)
    assert _parse_time_spec("14:30") == time(14, 30)
    assert _parse_time_spec("invalid") is None
    assert _parse_time_spec("25:00") is None


def test_extract_simulation_clock_scales_time():
    """Test simulation clock scaling."""
    real_start = datetime(2025, 1, 1, 0, 0, 0)
    row = {
        "zone_id": 1,
        "scenario": {
            "simulation": {
                "real_started_at": real_start.isoformat(),
                "sim_started_at": real_start.isoformat(),
                "time_scale": 60,
            }
        },
        "duration_hours": 1,
        "created_at": real_start,
    }
    clock = _extract_simulation_clock(row)
    assert clock is not None
    with patch("main.utcnow") as mock_utcnow:
        mock_utcnow.return_value = real_start.replace(tzinfo=timezone.utc) + timedelta(seconds=60)
        sim_now = clock.now()
    assert sim_now == real_start + timedelta(hours=1)


def test_schedule_crossings_same_day():
    """Test schedule crossings within the same day."""
    last_dt = datetime(2025, 1, 1, 10, 0, 0)
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    target = time(11, 0)
    crossings = _schedule_crossings(last_dt, now_dt, target)
    assert crossings == [datetime(2025, 1, 1, 11, 0, 0)]


def test_schedule_crossings_across_midnight():
    """Test schedule crossings across midnight."""
    last_dt = datetime(2025, 1, 1, 23, 30, 0)
    now_dt = datetime(2025, 1, 2, 0, 30, 0)
    target = time(0, 15)
    crossings = _schedule_crossings(last_dt, now_dt, target)
    assert crossings == [datetime(2025, 1, 2, 0, 15, 0)]


@pytest.mark.asyncio
async def test_get_active_schedules():
    """Test fetching active schedules."""
    repositories_module = types.ModuleType("repositories")
    laravel_module = types.ModuleType("repositories.laravel_api_repository")

    class DummyLaravelApiRepository:
        pass

    laravel_module.LaravelApiRepository = DummyLaravelApiRepository
    sys.modules["repositories"] = repositories_module
    sys.modules["repositories.laravel_api_repository"] = laravel_module

    with patch("main.fetch") as mock_fetch, \
         patch("repositories.laravel_api_repository.LaravelApiRepository") as mock_api_cls:
        mock_fetch.return_value = [
            {"zone_id": 1},
        ]
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {
            1: {
                "zone_id": 1,
                "cycle_id": 10,
                "phase": {"id": 2, "name": "Germination"},
                "targets": {
                    "irrigation": {"interval_sec": 3600},
                    "irrigation_schedule": ["08:00", "14:00", "20:00"],
                    "lighting_schedule": "06:00-22:00",
                    "lighting": {"photoperiod_hours": 16, "start_time": "06:00"},
                },
            }
        }
        mock_api_cls.return_value = mock_api
        schedules = await get_active_schedules()
        assert len(schedules) > 0
        irrigation_schedules = [s for s in schedules if s["type"] == "irrigation"]
        assert len(irrigation_schedules) == 3  # Three irrigation times
        lighting_schedules = [s for s in schedules if s["type"] == "lighting"]
        assert len(lighting_schedules) == 1  # One lighting window from photoperiod


@pytest.mark.asyncio
async def test_get_zone_nodes_for_type():
    """Test fetching zone nodes by type."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-irrig-1",
                "type": "irrigation",
                "channel": "pump1",
            }
        ]
        nodes = await get_zone_nodes_for_type(1, "irrigation")
        assert len(nodes) == 1
        assert nodes[0]["node_uid"] == "nd-irrig-1"
        assert nodes[0]["type"] == "irrigation"
        assert nodes[0]["channel"] == "pump1"


@pytest.mark.asyncio
async def test_send_command_via_automation_engine_success():
    """Test successful command sending via automation-engine REST API."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "ok"})
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await send_command_via_automation_engine(
            zone_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd="run_pump",
            params={"duration_ms": 60000}
        )
        
        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "automation-engine:9405/scheduler/command" in call_args[0][0]
        assert call_args[1]["json"]["zone_id"] == 1
        assert call_args[1]["json"]["node_uid"] == "nd-irrig-1"
        assert call_args[1]["json"]["channel"] == "default"
        assert call_args[1]["json"]["cmd"] == "run_pump"
        assert call_args[1]["json"]["params"] == {"duration_ms": 60000}


@pytest.mark.asyncio
async def test_send_command_via_automation_engine_error():
    """Test command sending with HTTP error."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client
        
        result = await send_command_via_automation_engine(
            zone_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd="run_pump"
        )
        
        assert result is False


@pytest.mark.asyncio
async def test_send_command_via_automation_engine_timeout():
    """Test command sending with timeout."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value = mock_client
        
        result = await send_command_via_automation_engine(
            zone_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd="run_pump"
        )
        
        assert result is False


@pytest.mark.asyncio
async def test_execute_irrigation_schedule():
    """Test executing irrigation schedule."""
    with patch("main.get_zone_nodes_for_type") as mock_nodes, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("main.check_water_level") as mock_water, \
         patch("main.check_flow") as mock_flow, \
         patch("main.calculate_irrigation_volume") as mock_volume, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.send_command_via_automation_engine") as mock_send_command, \
         patch("main.monitor_pump_safety") as mock_monitor:
        
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
        mock_send_command.return_value = True
        
        await execute_irrigation_schedule(1, {})
        
        # Should send pump command via REST API
        assert mock_send_command.called
        # Проверяем, что была отправлена команда run_pump
        run_pump_calls = [
            call for call in mock_send_command.call_args_list
            if call[1]["cmd"] == "run_pump"
        ]
        assert len(run_pump_calls) > 0


@pytest.mark.asyncio
async def test_execute_lighting_schedule_crosses_midnight():
    """Test lighting schedule when window crosses midnight."""
    with patch("main.get_zone_nodes_for_type") as mock_nodes, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("main.send_command_via_automation_engine") as mock_send:
        mock_nodes.return_value = [
            {"node_uid": "nd-light-1", "channel": "light", "type": "light"},
        ]
        mock_send.return_value = True
        schedule = {
            "start_time": time(22, 0),
            "end_time": time(6, 0),
        }
        await execute_lighting_schedule(1, schedule, now_time=time(23, 0))
        assert mock_send.called
        assert mock_send.call_args_list[0][1]["cmd"] == "light_on"


@pytest.mark.asyncio
async def test_check_and_execute_schedules_passes_mqtt():
    """Test that mqtt client is passed to water change check."""
    mqtt = Mock()
    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.check_water_changes", new_callable=AsyncMock) as mock_water_changes:
        mock_schedules.return_value = []
        mock_sim_clocks.return_value = {}
        await check_and_execute_schedules(mqtt)
        mock_water_changes.assert_awaited_once_with(mqtt)


@pytest.mark.asyncio
async def test_monitor_pump_safety_safe():
    """Test pump safety monitoring when flow is normal."""
    pump_start_time = utcnow() - timedelta(seconds=5)
    
    with patch("main.check_dry_run_protection") as mock_check, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("main.send_command_via_automation_engine") as mock_send_command, \
         patch("asyncio.sleep") as mock_sleep:
        
        mock_check.return_value = (True, None)  # Безопасно
        mock_sleep.return_value = None
        
        await monitor_pump_safety(1, pump_start_time, "nd-irrig-1", "pump1")
        
        # Не должна быть отправлена команда остановки
        stop_calls = [
            call for call in mock_send_command.call_args_list
            if call[1]["cmd"] == "set_relay" and call[1]["params"] == {"state": False}
        ]
        assert len(stop_calls) == 0
        
        # Не должно быть создано событие PUMP_STOPPED
        pump_stopped_calls = [call for call in mock_event.call_args_list
                             if len(call[0]) > 1 and call[0][1] == "PUMP_STOPPED"]
        assert len(pump_stopped_calls) == 0


@pytest.mark.asyncio
async def test_monitor_pump_safety_dry_run():
    """Test pump safety monitoring when dry run detected."""
    pump_start_time = utcnow() - timedelta(seconds=5)
    
    with patch("main.check_dry_run_protection") as mock_check, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.create_scheduler_log") as mock_log, \
         patch("main.send_command_via_automation_engine") as mock_send_command, \
         patch("asyncio.sleep") as mock_sleep:
        
        mock_check.return_value = (False, "NO_FLOW detected: flow=0.0 L/min")
        mock_sleep.return_value = None
        mock_send_command.return_value = True
        
        await monitor_pump_safety(1, pump_start_time, "nd-irrig-1", "pump1")
        
        # Должна быть отправлена команда остановки через REST API
        stop_calls = [
            call for call in mock_send_command.call_args_list
            if call[1]["cmd"] == "set_relay" and call[1]["params"] == {"state": False}
        ]
        assert len(stop_calls) > 0
        
        # Должно быть создано событие PUMP_STOPPED
        pump_stopped_calls = [call for call in mock_event.call_args_list
                             if len(call[0]) > 1 and call[0][1] == "PUMP_STOPPED"]
        assert len(pump_stopped_calls) == 1
        
        # Должен быть обновлен scheduler log
        mock_log.assert_called_once()
