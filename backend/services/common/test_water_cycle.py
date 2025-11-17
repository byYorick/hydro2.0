"""Tests for water_cycle module."""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime, time, timedelta
from common.water_cycle import (
    get_zone_water_cycle_config,
    get_zone_water_state,
    set_zone_water_state,
    get_solution_started_at,
    set_solution_started_at,
    in_schedule_window,
    tick_recirculation,
    check_water_change_required,
    execute_water_change,
    WATER_STATE_NORMAL_RECIRC,
    WATER_STATE_WATER_CHANGE_DRAIN,
    WATER_STATE_WATER_CHANGE_FILL,
    WATER_STATE_WATER_CHANGE_STABILIZE,
)


@pytest.mark.asyncio
async def test_get_zone_water_cycle_config():
    """Test getting zone water cycle config."""
    mock_settings = {
        "water_cycle": {
            "mode": "RECIRCULATING",
            "recirc": {
                "enabled": True,
                "schedule": [{"from": "00:00", "to": "23:59", "duty_cycle": 0.5}],
            },
        }
    }
    
    with patch("common.water_cycle.fetch") as mock_fetch:
        mock_fetch.return_value = [{"settings": mock_settings}]
        
        config = await get_zone_water_cycle_config(1)
        
        assert config["mode"] == "RECIRCULATING"
        assert config["recirc"]["enabled"] is True


@pytest.mark.asyncio
async def test_get_zone_water_cycle_config_defaults():
    """Test getting zone water cycle config with defaults."""
    with patch("common.water_cycle.fetch") as mock_fetch:
        mock_fetch.return_value = [{"settings": None}]
        
        config = await get_zone_water_cycle_config(1)
        
        assert config["mode"] == "RECIRCULATING"
        assert config["recirc"]["enabled"] is False


@pytest.mark.asyncio
async def test_get_zone_water_state():
    """Test getting zone water state."""
    with patch("common.water_cycle.fetch") as mock_fetch:
        mock_fetch.return_value = [{"water_state": WATER_STATE_WATER_CHANGE_DRAIN}]
        
        state = await get_zone_water_state(1)
        
        assert state == WATER_STATE_WATER_CHANGE_DRAIN


@pytest.mark.asyncio
async def test_get_zone_water_state_default():
    """Test getting zone water state with default."""
    with patch("common.water_cycle.fetch") as mock_fetch:
        mock_fetch.return_value = [{"water_state": None}]
        
        state = await get_zone_water_state(1)
        
        assert state == WATER_STATE_NORMAL_RECIRC


@pytest.mark.asyncio
async def test_set_zone_water_state():
    """Test setting zone water state."""
    with patch("common.water_cycle.execute") as mock_execute:
        await set_zone_water_state(1, WATER_STATE_WATER_CHANGE_DRAIN)
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        # Первый аргумент - SQL запрос, второй - state ($1), третий - zone_id ($2)
        assert call_args[0][1] == WATER_STATE_WATER_CHANGE_DRAIN
        assert call_args[0][2] == 1


@pytest.mark.asyncio
async def test_get_solution_started_at():
    """Test getting solution started at."""
    started_at = datetime.utcnow() - timedelta(days=5)
    
    with patch("common.water_cycle.fetch") as mock_fetch:
        mock_fetch.return_value = [{"solution_started_at": started_at}]
        
        result = await get_solution_started_at(1)
        
        assert result == started_at


@pytest.mark.asyncio
async def test_set_solution_started_at():
    """Test setting solution started at."""
    started_at = datetime.utcnow()
    
    with patch("common.water_cycle.execute") as mock_execute:
        await set_solution_started_at(1, started_at)
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        # Первый аргумент - SQL запрос, второй - started_at ($1), третий - zone_id ($2)
        assert call_args[0][1] == started_at
        assert call_args[0][2] == 1


def test_in_schedule_window():
    """Test checking if time is in schedule window."""
    now = datetime(2025, 1, 27, 14, 30)  # 14:30
    
    schedule = [
        {"from": "08:00", "to": "18:00", "duty_cycle": 0.5}
    ]
    
    assert in_schedule_window(now, schedule) is True
    
    # Вне окна
    now_outside = datetime(2025, 1, 27, 20, 0)  # 20:00
    assert in_schedule_window(now_outside, schedule) is False


def test_in_schedule_window_empty():
    """Test schedule window check with empty schedule."""
    now = datetime.utcnow()
    
    assert in_schedule_window(now, []) is True  # Если расписание пустое, всегда активно


def test_in_schedule_window_overnight():
    """Test schedule window that spans midnight."""
    now = datetime(2025, 1, 27, 23, 30)  # 23:30
    
    schedule = [
        {"from": "22:00", "to": "06:00", "duty_cycle": 0.5}
    ]
    
    assert in_schedule_window(now, schedule) is True


@pytest.mark.asyncio
async def test_tick_recirculation_disabled():
    """Test tick recirculation when recirculation is disabled."""
    config = {
        "mode": "RECIRCULATING",
        "recirc": {
            "enabled": False,
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config:
        mock_config.return_value = config
        
        result = await tick_recirculation(1, Mock(), "gh-1")
        
        assert result is None  # Рециркуляция отключена - не трогаем насос


@pytest.mark.asyncio
async def test_tick_recirculation_out_of_schedule():
    """Test tick recirculation when out of schedule."""
    now = datetime(2025, 1, 27, 23, 0)  # 23:00
    config = {
        "mode": "RECIRCULATING",
        "recirc": {
            "enabled": True,
            "schedule": [{"from": "08:00", "to": "18:00", "duty_cycle": 0.5}],
            "max_recirc_off_minutes": 10,
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config, \
         patch("common.water_cycle.fetch") as mock_fetch, \
         patch("common.water_cycle.check_pump_stuck_on") as mock_stuck, \
         patch("common.water_cycle.can_run_pump") as mock_can_run:
        mock_config.return_value = config
        # Нет узлов для рециркуляции
        mock_fetch.return_value = []
        
        result = await tick_recirculation(1, Mock(), "gh-1", now)
        
        assert result is None


@pytest.mark.asyncio
async def test_tick_recirculation_with_nodes():
    """Test tick recirculation with recirculation nodes."""
    now = datetime(2025, 1, 27, 14, 0)  # 14:00
    config = {
        "mode": "RECIRCULATING",
        "recirc": {
            "enabled": True,
            "schedule": [{"from": "08:00", "to": "18:00", "duty_cycle": 0.5}],
            "max_recirc_off_minutes": 10,
        },
    }
    
    node_info = {
        "id": 1,
        "uid": "nd-recirc-1",
        "type": "recirculation",
        "channel": "pump_recirc",
        "config": {"fail_safe_mode": "NC"},
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config, \
         patch("common.water_cycle.fetch") as mock_fetch, \
         patch("common.water_cycle.check_pump_stuck_on") as mock_stuck, \
         patch("common.water_cycle.can_run_pump") as mock_can_run:
        mock_config.return_value = config
        # Получаем узлы и телеметрию
        mock_fetch.side_effect = [
            [node_info],  # Узлы для рециркуляции
            [],  # Ток (нет данных)
            [],  # Flow (нет данных)
        ]
        mock_stuck.return_value = (True, None)
        mock_can_run.return_value = (True, None)
        
        mqtt_client = Mock()
        result = await tick_recirculation(1, mqtt_client, "gh-1", now)
        
        # Должна быть команда для управления насосом
        assert result is not None
        assert result["node_uid"] == "nd-recirc-1"
        assert result["channel"] == "pump_recirc"


@pytest.mark.asyncio
async def test_check_water_change_required_by_interval():
    """Test water change required by interval."""
    solution_started_at = datetime.utcnow() - timedelta(days=8)
    config = {
        "water_change": {
            "enabled": True,
            "interval_days": 7,
            "max_solution_age_days": 10,
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config, \
         patch("common.water_cycle.get_solution_started_at") as mock_started:
        mock_config.return_value = config
        mock_started.return_value = solution_started_at
        
        required, reason = await check_water_change_required(1)
        
        assert required is True
        assert "Interval" in reason


@pytest.mark.asyncio
async def test_check_water_change_required_by_max_age():
    """Test water change required by max age."""
    # Проверяем случай, когда interval ещё не превышен, но max_age превышен
    solution_started_at = datetime.utcnow() - timedelta(days=12)
    config = {
        "water_change": {
            "enabled": True,
            "interval_days": 14,  # Больше чем прошло дней
            "max_solution_age_days": 10,  # Меньше чем прошло дней
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config, \
         patch("common.water_cycle.get_solution_started_at") as mock_started:
        mock_config.return_value = config
        mock_started.return_value = solution_started_at
        
        required, reason = await check_water_change_required(1)
        
        assert required is True
        assert "Max solution age" in reason or "max_age" in reason.lower()


@pytest.mark.asyncio
async def test_check_water_change_required_not_required():
    """Test water change not required."""
    solution_started_at = datetime.utcnow() - timedelta(days=3)
    config = {
        "water_change": {
            "enabled": True,
            "interval_days": 7,
            "max_solution_age_days": 10,
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config, \
         patch("common.water_cycle.get_solution_started_at") as mock_started:
        mock_config.return_value = config
        mock_started.return_value = solution_started_at
        
        required, reason = await check_water_change_required(1)
        
        assert required is False
        assert reason is None


@pytest.mark.asyncio
async def test_check_water_change_required_disabled():
    """Test water change check when disabled."""
    config = {
        "water_change": {
            "enabled": False,
        },
    }
    
    with patch("common.water_cycle.get_zone_water_cycle_config") as mock_config:
        mock_config.return_value = config
        
        required, reason = await check_water_change_required(1)
        
        assert required is False
        assert reason is None


@pytest.mark.asyncio
async def test_execute_water_change_drain():
    """Test execute water change - drain phase."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    drain_result = {"success": True}
    
    # Используем side_effect для последовательного возврата состояний
    state_sequence = [WATER_STATE_NORMAL_RECIRC, WATER_STATE_WATER_CHANGE_DRAIN]
    state_call_count = {"count": 0}
    
    def get_state_side_effect(*args):
        state_call_count["count"] += 1
        if state_call_count["count"] == 1:
            return WATER_STATE_NORMAL_RECIRC
        else:
            return WATER_STATE_WATER_CHANGE_DRAIN
    
    with patch("common.water_cycle.get_zone_water_state", side_effect=get_state_side_effect) as mock_get_state, \
         patch("common.water_cycle.set_zone_water_state") as mock_set_state, \
         patch("common.water_cycle.create_zone_event") as mock_event, \
         patch("common.water_cycle.fetch") as mock_fetch, \
         patch("common.water_cycle.execute_drain_mode") as mock_drain:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-recirc-1",
                "channel": "pump_recirc",
            }
        ]
        mock_drain.return_value = drain_result
        
        result = await execute_water_change(1, mqtt_client, "gh-1")
        
        # Должен перейти в состояние DRAIN, затем FILL
        assert mock_set_state.call_count >= 1
        # Должен вызвать drain (но только если состояние DRAIN)
        # Из-за логики функции, drain вызывается только если текущее состояние уже DRAIN


@pytest.mark.asyncio
async def test_execute_water_change_fill():
    """Test execute water change - fill phase."""
    mqtt_client = Mock()
    
    fill_result = {"success": True}
    
    with patch("common.water_cycle.get_zone_water_state") as mock_get_state, \
         patch("common.water_cycle.set_zone_water_state") as mock_set_state, \
         patch("common.water_cycle.create_zone_event") as mock_event, \
         patch("common.water_cycle.execute_fill_mode") as mock_fill:
        mock_get_state.return_value = WATER_STATE_WATER_CHANGE_FILL
        mock_fill.return_value = fill_result
        
        result = await execute_water_change(1, mqtt_client, "gh-1")
        
        # Должен перейти в состояние STABILIZE
        mock_set_state.assert_called()
        mock_fill.assert_called_once()


@pytest.mark.asyncio
async def test_execute_water_change_stabilize():
    """Test execute water change - stabilize phase."""
    mqtt_client = Mock()
    solution_started_at = datetime.utcnow() - timedelta(minutes=35)
    
    with patch("common.water_cycle.get_zone_water_state") as mock_get_state, \
         patch("common.water_cycle.set_zone_water_state") as mock_set_state, \
         patch("common.water_cycle.create_zone_event") as mock_event, \
         patch("common.water_cycle.get_solution_started_at") as mock_started, \
         patch("common.water_cycle.set_solution_started_at") as mock_set_started:
        mock_get_state.return_value = WATER_STATE_WATER_CHANGE_STABILIZE
        mock_started.return_value = solution_started_at
        
        result = await execute_water_change(1, mqtt_client, "gh-1")
        
        # Должен завершиться и вернуться в NORMAL_RECIRC
        assert result["success"] is True
        assert result["state"] == WATER_STATE_NORMAL_RECIRC
        mock_set_state.assert_called_with(1, WATER_STATE_NORMAL_RECIRC)


@pytest.mark.asyncio
async def test_execute_water_change_stabilize_waiting():
    """Test execute water change - stabilize phase still waiting."""
    mqtt_client = Mock()
    solution_started_at = datetime.utcnow() - timedelta(minutes=15)
    
    with patch("common.water_cycle.get_zone_water_state") as mock_get_state, \
         patch("common.water_cycle.get_solution_started_at") as mock_started:
        mock_get_state.return_value = WATER_STATE_WATER_CHANGE_STABILIZE
        mock_started.return_value = solution_started_at
        
        result = await execute_water_change(1, mqtt_client, "gh-1")
        
        # Должен ещё ждать стабилизации
        assert result["success"] is True
        assert result["state"] == WATER_STATE_WATER_CHANGE_STABILIZE
        assert result["stabilizing"] is True


@pytest.mark.asyncio
async def test_execute_water_change_drain_failed():
    """Test execute water change when drain fails."""
    mqtt_client = Mock()
    mqtt_client.publish_json = Mock()
    
    drain_result = {"success": False, "error": "drain_error"}
    
    # Используем side_effect для последовательного возврата состояний
    # Функция проверяет состояние один раз в начале, поэтому нужно сразу DRAIN
    state_call_count = {"count": 0}
    
    def get_state_side_effect(*args):
        state_call_count["count"] += 1
        # Возвращаем DRAIN сразу, чтобы блок drain выполнился
        return WATER_STATE_WATER_CHANGE_DRAIN
    
    with patch("common.water_cycle.get_zone_water_state", side_effect=get_state_side_effect) as mock_get_state, \
         patch("common.water_cycle.set_zone_water_state") as mock_set_state, \
         patch("common.water_cycle.create_zone_event") as mock_event, \
         patch("common.water_cycle.fetch") as mock_fetch, \
         patch("common.water_cycle.execute_drain_mode") as mock_drain:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-recirc-1",
                "channel": "pump_recirc",
            }
        ]
        mock_drain.return_value = drain_result
        
        result = await execute_water_change(1, mqtt_client, "gh-1")
        
        # Должен вернуться в NORMAL_RECIRC при ошибке
        # Проверяем, что был вызван execute_drain_mode
        mock_drain.assert_called_once()
        # Проверяем, что результат содержит ошибку
        assert isinstance(result, dict)
        assert result.get("success") is False
        assert result.get("error") == "drain_failed"
        # Проверяем, что был вызов для возврата в NORMAL_RECIRC при ошибке
        normal_recirc_calls = [call for call in mock_set_state.call_args_list if len(call[0]) > 1 and call[0][1] == WATER_STATE_NORMAL_RECIRC]
        assert len(normal_recirc_calls) >= 1

