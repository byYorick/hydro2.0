"""Tests for water_flow module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, timedelta
from common.utils.time import utcnow

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.water_flow import (
    check_water_level,
    check_flow,
    check_dry_run_protection,
    calculate_irrigation_volume,
    ensure_water_level_alert,
    ensure_no_flow_alert,
    get_irrigation_nodes,
    execute_fill_mode,
    execute_drain_mode,
    calibrate_flow,
    WATER_LEVEL_LOW_THRESHOLD,
    MIN_FLOW_THRESHOLD,
)


@pytest.mark.asyncio
async def test_check_water_level_normal():
    """Test water level check when level is normal."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.5}]  # 50% - нормальный уровень
        is_ok, level = await check_water_level(1)
        assert is_ok is True
        assert level == 0.5


@pytest.mark.asyncio
async def test_check_water_level_low():
    """Test water level check when level is low."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.15}]  # 15% - низкий уровень
        is_ok, level = await check_water_level(1)
        assert is_ok is False
        assert level == 0.15


@pytest.mark.asyncio
async def test_check_water_level_no_data():
    """Test water level check when no data available."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []
        is_ok, level = await check_water_level(1)
        assert is_ok is True  # Не блокируем если нет данных
        assert level is None


@pytest.mark.asyncio
async def test_check_flow_normal():
    """Test flow check when flow is normal."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 2.5}]  # 2.5 L/min - нормальный поток
        is_ok, flow = await check_flow(1, min_flow=0.1)
        assert is_ok is True
        assert flow == 2.5


@pytest.mark.asyncio
async def test_check_flow_low():
    """Test flow check when flow is too low."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.05}]  # 0.05 L/min - низкий поток
        is_ok, flow = await check_flow(1, min_flow=0.1)
        assert is_ok is False
        assert flow == 0.05


@pytest.mark.asyncio
async def test_check_flow_no_data():
    """Test flow check when no data available."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []
        is_ok, flow = await check_flow(1, min_flow=0.1)
        assert is_ok is False  # Нет данных = нет потока
        assert flow is None


@pytest.mark.asyncio
async def test_check_dry_run_protection_safe():
    """Test dry run protection when pump just started."""
    pump_start_time = utcnow() - timedelta(seconds=1)  # Прошла 1 секунда
    
    with patch("common.water_flow.check_flow") as mock_check_flow:
        # Не проверяем flow если прошло меньше 3 секунд
        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)
        assert is_safe is True
        assert error is None
        mock_check_flow.assert_not_called()


@pytest.mark.asyncio
async def test_check_dry_run_protection_no_flow():
    """Test dry run protection when no flow detected."""
    pump_start_time = utcnow() - timedelta(seconds=5)  # Прошло 5 секунд
    
    with patch("common.water_flow.check_flow") as mock_check_flow, \
         patch("common.water_flow.create_zone_event") as mock_event:
        mock_check_flow.return_value = (False, 0.0)  # Нет потока
        
        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)
        assert is_safe is False
        assert error is not None
        assert "NO_FLOW" in error
        mock_event.assert_called_once()


@pytest.mark.asyncio
async def test_check_dry_run_protection_flow_ok():
    """Test dry run protection when flow is normal."""
    pump_start_time = utcnow() - timedelta(seconds=5)  # Прошло 5 секунд
    
    with patch("common.water_flow.check_flow") as mock_check_flow:
        mock_check_flow.return_value = (True, 2.0)  # Поток нормальный
        
        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)
        assert is_safe is True
        assert error is None


@pytest.mark.asyncio
async def test_calculate_irrigation_volume():
    """Test irrigation volume calculation."""
    start_time = utcnow() - timedelta(minutes=10)
    end_time = utcnow()
    
    # Симулируем данные flow: 2.0 L/min в течение 10 минут
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": 2.0, "ts": start_time},
            {"value": 2.0, "ts": end_time},
        ]
        
        volume = await calculate_irrigation_volume(1, start_time, end_time)
        # Объем = средний flow * время в минутах
        # (2.0 + 2.0) / 2 * 10 = 20 литров
        assert volume > 0
        assert volume == pytest.approx(20.0, rel=0.1)


@pytest.mark.asyncio
async def test_calculate_irrigation_volume_no_data():
    """Test irrigation volume calculation when no data."""
    start_time = utcnow() - timedelta(minutes=10)
    end_time = utcnow()
    
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        volume = await calculate_irrigation_volume(1, start_time, end_time)
        assert volume == 0.0


@pytest.mark.asyncio
async def test_ensure_water_level_alert_low():
    """Test water level alert creation when level is low."""
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.execute") as mock_execute, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.create_alert") as mock_create_alert:
        # Нет активного алерта
        mock_fetch.return_value = []
        mock_execute.return_value = [{"id": 1}]
        mock_create_alert.return_value = {"id": 1}
        mock_event.return_value = None
        
        await ensure_water_level_alert(1, 0.15)  # Низкий уровень
        
        # Должен создать алерт
        assert mock_create_alert.call_count >= 1
        # Должен создать событие
        assert mock_event.call_count >= 1


@pytest.mark.asyncio
async def test_ensure_water_level_alert_normal():
    """Test water level alert when level is normal."""
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.execute") as mock_execute:
        await ensure_water_level_alert(1, 0.5)  # Нормальный уровень
        
        # Не должен создавать алерт
        mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_no_flow_alert():
    """Test no flow alert creation."""
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.execute") as mock_execute, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.create_alert") as mock_create_alert:
        # Нет активного алерта
        mock_fetch.return_value = []
        mock_execute.return_value = [{"id": 1}]
        mock_create_alert.return_value = {"id": 1}
        mock_event.return_value = None
        
        await ensure_no_flow_alert(1, 0.05, min_flow=0.1)  # Низкий поток
        
        # Должен создать алерт
        assert mock_create_alert.call_count >= 1
        # Должен создать событие
        assert mock_event.call_count >= 1


@pytest.mark.asyncio
async def test_get_irrigation_nodes():
    """Test getting irrigation nodes for zone."""
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-irrig-1",
                "type": "irrig",
                "channel": "pump1",
            }
        ]
        
        nodes = await get_irrigation_nodes(1)
        assert len(nodes) == 1
        assert nodes[0]["node_uid"] == "nd-irrig-1"
        assert nodes[0]["type"] == "irrig"
        assert nodes[0]["channel"] == "pump1"


@pytest.mark.asyncio
async def test_get_irrigation_nodes_no_nodes():
    """Test getting irrigation nodes when no nodes available."""
    with patch("common.water_flow.fetch") as mock_fetch:
        # Первый вызов - нет специальных узлов
        # Второй вызов - нет обычных irrigation узлов
        mock_fetch.side_effect = [[], []]
        
        nodes = await get_irrigation_nodes(1)
        assert len(nodes) == 0


@pytest.mark.asyncio
async def test_execute_fill_mode_success():
    """Test fill mode execution when successful."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    call_count = {"sleep": 0, "level": 0}
    
    async def mock_sleep(delay):
        call_count["sleep"] += 1
        # После первого sleep возвращаем уровень, который достиг цели
        if call_count["sleep"] == 1:
            call_count["level"] = 1
    
    with patch("common.water_flow.get_irrigation_nodes") as mock_nodes, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.check_water_level") as mock_level, \
         patch("common.water_flow.send_command", new_callable=AsyncMock) as mock_send, \
         patch("asyncio.sleep", side_effect=mock_sleep):
        
        # Настройка моков
        mock_nodes.return_value = [
            {
                "node_id": 1,
                "node_uid": "nd-irrig-1",
                "type": "irrig",
                "channel": "pump1",
            }
        ]
        
        # Симулируем достижение целевого уровня после первого sleep
        def level_side_effect(*args):
            if call_count["level"] == 0:
                return (True, 0.3)  # Начальный уровень
            else:
                return (True, 0.9)  # Достигли цели
        
        mock_level.side_effect = level_side_effect
        
        mock_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}

        result = await execute_fill_mode(1, 0.9, mqtt_client, "gh-1", max_duration_sec=10)
        
        # Проверяем результат
        assert result["success"] is True
        assert result["target_level"] == 0.9
        assert result["final_level"] == 0.9
        
        # Проверяем, что были созданы события
        assert mock_event.call_count >= 2  # FILL_STARTED и FILL_FINISHED
        
        # Проверяем, что была отправлена команда fill и stop
        assert mock_send.call_count >= 2


@pytest.mark.asyncio
async def test_execute_fill_mode_no_nodes():
    """Test fill mode when no nodes available."""
    mqtt_client = Mock()
    
    with patch("common.water_flow.get_irrigation_nodes") as mock_nodes, \
         patch("common.water_flow.create_zone_event") as mock_event:
        
        mock_nodes.return_value = []
        
        result = await execute_fill_mode(1, 0.9, mqtt_client, "gh-1")
        
        assert result["success"] is False
        assert result["error"] == "no_nodes"
        # Должны быть созданы события STARTED и FINISHED с ошибкой
        assert mock_event.call_count == 2


@pytest.mark.asyncio
async def test_execute_fill_mode_timeout():
    """Test fill mode when timeout occurs."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    start_time = utcnow()
    call_count = {"sleep": 0}
    
    async def mock_sleep(delay):
        call_count["sleep"] += 1
    
    with patch("common.water_flow.get_irrigation_nodes") as mock_nodes, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.check_water_level") as mock_level, \
         patch("common.water_flow.send_command", new_callable=AsyncMock) as mock_send, \
         patch("common.water_flow.utcnow") as mock_utcnow, \
         patch("asyncio.sleep", side_effect=mock_sleep):
        
        mock_nodes.return_value = [
            {
                "node_id": 1,
                "node_uid": "nd-irrig-1",
                "type": "irrig",
                "channel": "pump1",
            }
        ]
        
        # Симулируем, что уровень не достигает цели
        mock_level.return_value = (True, 0.5)
        
        # Симулируем таймаут - после первого sleep время превышает max_duration
        def utcnow_side_effect():
            if call_count["sleep"] <= 1:
                return start_time
            return start_time + timedelta(seconds=301)

        mock_utcnow.side_effect = utcnow_side_effect
        
        mock_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}

        result = await execute_fill_mode(1, 0.9, mqtt_client, "gh-1", max_duration_sec=300)
        
        assert result["success"] is False
        assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_execute_drain_mode_success():
    """Test drain mode execution when successful."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    call_count = {"sleep": 0, "level": 0}
    
    async def mock_sleep(delay):
        call_count["sleep"] += 1
        if call_count["sleep"] == 1:
            call_count["level"] = 1
    
    with patch("common.water_flow.get_irrigation_nodes") as mock_nodes, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.check_water_level") as mock_level, \
         patch("common.water_flow.send_command", new_callable=AsyncMock) as mock_send, \
         patch("asyncio.sleep", side_effect=mock_sleep):
        
        mock_nodes.return_value = [
            {
                "node_id": 1,
                "node_uid": "nd-irrig-1",
                "type": "irrig",
                "channel": "drain_valve",
            }
        ]
        
        # Симулируем достижение целевого уровня после первого sleep
        def level_side_effect(*args):
            if call_count["level"] == 0:
                return (True, 0.7)  # Начальный уровень
            else:
                return (True, 0.1)  # Достигли цели
        
        mock_level.side_effect = level_side_effect
        
        mock_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}

        result = await execute_drain_mode(1, 0.1, mqtt_client, "gh-1", max_duration_sec=10)
        
        assert result["success"] is True
        assert result["target_level"] == 0.1
        assert result["final_level"] == 0.1
        
        # Проверяем события
        assert mock_event.call_count >= 2  # DRAIN_STARTED и DRAIN_FINISHED
        
        # Проверяем команду
        assert mock_send.call_count >= 2


@pytest.mark.asyncio
async def test_execute_drain_mode_no_nodes():
    """Test drain mode when no nodes available."""
    mqtt_client = Mock()
    
    with patch("common.water_flow.get_irrigation_nodes") as mock_nodes, \
         patch("common.water_flow.create_zone_event") as mock_event:
        
        mock_nodes.return_value = []
        
        result = await execute_drain_mode(1, 0.1, mqtt_client, "gh-1")
        
        assert result["success"] is False
        assert result["error"] == "no_nodes"
        assert mock_event.call_count == 2


@pytest.mark.asyncio
async def test_calibrate_flow_success():
    """Test flow calibration when successful."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    # Моки для fetch
    node_info = {
        "id": 1,
        "uid": "nd-flow-1",
        "zone_id": 1,
        "channel_id": 10,
        "config": {}
    }
    
    pump_info = {
        "id": 2,
        "uid": "nd-pump-1",
        "channel": "pump_irrigation"
    }
    
    # Данные flow для калибровки
    flow_samples = [
        {"value": 2.0, "ts": utcnow() - timedelta(seconds=8), "metadata": {"raw": {"pulses": 100}}},
        {"value": 2.1, "ts": utcnow() - timedelta(seconds=6), "metadata": {"raw": {"pulses": 120}}},
        {"value": 2.0, "ts": utcnow() - timedelta(seconds=4), "metadata": {"raw": {"pulses": 140}}},
        {"value": 2.2, "ts": utcnow() - timedelta(seconds=2), "metadata": {"raw": {"pulses": 160}}},
    ]
    
    # Мок для MQTT клиента
    mqtt_client.publish_json = Mock()
    
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.check_water_level") as mock_water_level, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.send_command", new_callable=AsyncMock) as mock_send, \
         patch("common.command_orchestrator.send_command", new_callable=AsyncMock) as mock_orchestrator_send, \
         patch("common.water_flow.httpx.AsyncClient") as mock_httpx_client, \
         patch("asyncio.sleep") as mock_sleep:
        
        # Настройка моков
        mock_fetch.side_effect = [
            [node_info],  # Получение информации об узле
            [pump_info],  # Получение насоса
            flow_samples,  # Получение данных flow
        ]
        mock_water_level.return_value = (True, 0.5)  # Нормальный уровень воды
        
        mock_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}
        mock_orchestrator_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_http_client = AsyncMock()
        mock_http_client.__aenter__.return_value = mock_http_client
        mock_http_client.patch.return_value = mock_response
        mock_httpx_client.return_value = mock_http_client
        
        result = await calibrate_flow(1, 1, "flow_sensor", mqtt_client, "gh-1", pump_duration_sec=10)
        
        # Проверяем результат
        assert result["success"] is True
        assert "K" in result
        assert "avg_flow_l_per_min" in result
        assert "samples_count" in result
        assert result["samples_count"] == len(flow_samples)
        
        # Проверяем, что были созданы события
        assert mock_event.call_count >= 2  # FLOW_CALIBRATION_STARTED и FLOW_CALIBRATION_FINISHED
        
        # Проверяем, что была отправлена команда запуска насоса
        assert mock_send.called


@pytest.mark.asyncio
async def test_calibrate_flow_no_node():
    """Test flow calibration when node not found."""
    mqtt_client = Mock()
    
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []  # Узел не найден
        
        with pytest.raises(ValueError, match="Node.*not found"):
            await calibrate_flow(1, 1, "flow_sensor", mqtt_client, "gh-1")


@pytest.mark.asyncio
async def test_calibrate_flow_no_pump():
    """Test flow calibration when no pump found."""
    mqtt_client = Mock()
    
    node_info = {
        "id": 1,
        "uid": "nd-flow-1",
        "zone_id": 1,
        "channel_id": 10,
        "config": {}
    }
    
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.check_water_level") as mock_water_level:
        
        mock_fetch.side_effect = [
            [node_info],  # Узел найден
            [],  # Насос не найден
        ]
        mock_water_level.return_value = (True, 0.5)
        
        with pytest.raises(ValueError, match="No irrigation pump found"):
            await calibrate_flow(1, 1, "flow_sensor", mqtt_client, "gh-1")


@pytest.mark.asyncio
async def test_calibrate_flow_low_water_level():
    """Test flow calibration when water level is low."""
    mqtt_client = Mock()
    
    node_info = {
        "id": 1,
        "uid": "nd-flow-1",
        "zone_id": 1,
        "channel_id": 10,
        "config": {}
    }
    
    pump_info = {
        "id": 2,
        "uid": "nd-pump-1",
        "channel": "pump_irrigation"
    }
    
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.check_water_level") as mock_water_level:
        
        mock_fetch.side_effect = [
            [node_info],
            [pump_info],
        ]
        mock_water_level.return_value = (False, 0.15)  # Низкий уровень воды
        
        with pytest.raises(ValueError, match="Water level too low"):
            await calibrate_flow(1, 1, "flow_sensor", mqtt_client, "gh-1")


@pytest.mark.asyncio
async def test_calibrate_flow_insufficient_data():
    """Test flow calibration when insufficient flow data."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    node_info = {
        "id": 1,
        "uid": "nd-flow-1",
        "zone_id": 1,
        "channel_id": 10,
        "config": {}
    }
    
    pump_info = {
        "id": 2,
        "uid": "nd-pump-1",
        "channel": "pump_irrigation"
    }
    
    with patch("common.water_flow.fetch") as mock_fetch, \
         patch("common.water_flow.check_water_level") as mock_water_level, \
         patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.send_command", new_callable=AsyncMock) as mock_send, \
         patch("common.command_orchestrator.send_command", new_callable=AsyncMock) as mock_orchestrator_send, \
         patch("asyncio.sleep") as mock_sleep:
        
        mock_fetch.side_effect = [
            [node_info],
            [pump_info],
            [],  # Нет данных flow
        ]
        mock_water_level.return_value = (True, 0.5)
        mock_event.return_value = None
        
        mock_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}
        mock_orchestrator_send.return_value = {"status": "sent", "cmd_id": "cmd-1"}

        with pytest.raises(ValueError, match="Insufficient flow data"):
            await calibrate_flow(1, 1, "flow_sensor", mqtt_client, "gh-1", pump_duration_sec=10)
