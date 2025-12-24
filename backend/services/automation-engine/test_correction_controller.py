"""Tests for correction_controller."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
from correction_controller import CorrectionController, CorrectionType


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_target():
    """Test pH controller when target is not set."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {}
    telemetry = {"PH": 6.5}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_current():
    """Test pH controller when current value is not available."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {}
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_small_diff():
    """Test pH controller when difference is too small."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.4}  # diff = 0.1, меньше порога 0.2
    nodes = {}
    
    telemetry_ts = {"PH": datetime.now(timezone.utc)}
    result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
    assert result is None


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_cooldown():
    """Test pH controller when in cooldown period."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.8}  # diff = 0.3, больше порога
    nodes = {
        "irrig:default": {
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "type": "irrig"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (False, "В cooldown периоде")
        with patch("correction_controller.create_zone_event") as mock_event:
            telemetry_ts = {"PH": datetime.now(timezone.utc)}
            result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
            
            assert result is None
            mock_event.assert_called_once()
            call_args = mock_event.call_args
            assert call_args[0][1] == 'PH_CORRECTION_SKIPPED'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_low_ph():
    """Test pH controller when pH is too low (add base)."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.2}  # diff = -0.3, pH слишком низкий
    nodes = {}
    actuators = {
        "ph_base_pump": {
            "node_uid": "nd-ph-1",
            "channel": "pump_base",
            "role": "ph_base_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'dose'
        assert result['params']['type'] == 'add_base'
        assert result['params']['dose_ml'] == pytest.approx(3.0, abs=0.01)  # abs(-0.3) * 10
        assert result['event_type'] == 'PH_CORRECTED'
        assert result['event_details']['correction_type'] == 'add_base'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_high_ph():
    """Test pH controller when pH is too high (add acid)."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.8}  # diff = 0.3, pH слишком высокий
    nodes = {}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-2",
            "channel": "pump_acid",
            "role": "ph_acid_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'dose'
        assert result['params']['type'] == 'add_acid'
        assert result['params']['dose_ml'] == pytest.approx(3.0, abs=0.01)  # abs(0.3) * 10
        assert result['event_type'] == 'PH_CORRECTED'


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_water():
    """Test pH controller when water level is low."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.8}
    nodes = {}
    actuators = {
        "ph_acid_pump": {
            "node_uid": "nd-ph-2",
            "channel": "pump_acid",
            "role": "ph_acid_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock):
        mock_should.return_value = (True, "Корректировка необходима")

        telemetry_ts = {"PH": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=False, actuators=actuators)
        
        assert result is None  # Не должно быть корректировки при низком уровне воды


@pytest.mark.asyncio
async def test_ph_controller_check_and_correct_no_nodes():
    """Test pH controller when no irrigation nodes available."""
    controller = CorrectionController(CorrectionType.PH)
    targets = {"ph": 6.5}
    telemetry = {"PH": 6.8}
    nodes = {}  # Нет узлов
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"PH": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True)
        
        assert result is None


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_low_ec():
    """Test EC controller when EC is too low (add nutrients)."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {"ec": 1.8}
    telemetry = {"EC": 1.5}  # diff = -0.3, EC слишком низкий
    nodes = {}
    actuators = {
        "ec_nutrient_pump": {
            "node_uid": "nd-ec-1",
            "channel": "pump_nutrient",
            "role": "ec_nutrient_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should, \
         patch("correction_controller.create_zone_event", new_callable=AsyncMock), \
         patch("correction_controller.record_correction", new_callable=AsyncMock), \
         patch("correction_controller.create_ai_log", new_callable=AsyncMock):
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        assert result is not None
        assert result['cmd'] == 'run_pump'
        assert result['params']['type'] == 'add_nutrients'
        assert result['params']['dose_ml'] == pytest.approx(30.0, abs=0.01)  # abs(-0.3) * 100
        assert result['params']['duration_ms'] > 0
        assert result['event_type'] == 'EC_DOSING'


@pytest.mark.asyncio
async def test_ec_controller_check_and_correct_high_ec():
    """Test EC controller when EC is too high (dilute)."""
    controller = CorrectionController(CorrectionType.EC)
    targets = {"ec": 1.8}
    telemetry = {"EC": 2.1}  # diff = 0.3, EC слишком высокий
    nodes = {}
    actuators = {
        "ec_nutrient_pump": {
            "node_uid": "nd-ec-1",
            "channel": "pump_nutrient",
            "role": "ec_nutrient_pump"
        }
    }
    
    with patch("correction_controller.should_apply_correction") as mock_should:
        mock_should.return_value = (True, "Корректировка необходима")
        
        telemetry_ts = {"EC": datetime.now(timezone.utc)}
        result = await controller.check_and_correct(1, targets, telemetry, telemetry_ts, nodes=nodes, water_level_ok=True, actuators=actuators)
        
        # Для dilute актюатор не выбирается, команда не отправляется
        assert result is None


@pytest.mark.asyncio
async def test_ph_controller_apply_correction():
    """Test applying pH correction (sending command and creating events)."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'dose_ml': 3.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.8,
            'target_ph': 6.5,
            'diff': 0.3,
            'dose_ml': 3.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.8,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
    with patch("correction_controller.record_correction") as mock_record, \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log") as mock_ai_log:
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что команда была отправлена
        command_bus.publish_controller_command.assert_called_once()
        
        # Проверяем, что было записано в cooldown
        mock_record.assert_called_once()
        
        # Проверяем, что были созданы события
        assert mock_event.call_count >= 2  # PH_CORRECTED, DOSING
        
        # Проверяем, что был создан AI log
        mock_ai_log.assert_called_once()


@pytest.mark.asyncio
async def test_ph_controller_apply_correction_high_ph_detected():
    """Test that PH_TOO_HIGH_DETECTED event is created for high pH."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_acid',
        'cmd': 'dose',
        'params': {'dose_ml': 4.0, 'type': 'add_acid'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_acid',
            'current_ph': 6.9,
            'target_ph': 6.5,
            'diff': 0.4,  # > 0.3, должно создать PH_TOO_HIGH_DETECTED
            'dose_ml': 4.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.9,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log"):
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что было создано событие PH_TOO_HIGH_DETECTED
        event_calls = [call[0][1] for call in mock_event.call_args_list]
        assert 'PH_TOO_HIGH_DETECTED' in event_calls


@pytest.mark.asyncio
async def test_ph_controller_apply_correction_low_ph_detected():
    """Test that PH_TOO_LOW_DETECTED event is created for low pH."""
    controller = CorrectionController(CorrectionType.PH)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ph-1',
        'channel': 'pump_base',
        'cmd': 'dose',
        'params': {'dose_ml': 4.0, 'type': 'add_base'},
        'event_type': 'PH_CORRECTED',
        'event_details': {
            'correction_type': 'add_base',
            'current_ph': 6.1,
            'target_ph': 6.5,
            'diff': -0.4,  # < -0.3, должно создать PH_TOO_LOW_DETECTED
            'dose_ml': 4.0
        },
        'zone_id': 1,
        'correction_type_str': 'ph',
        'current_value': 6.1,
        'target_value': 6.5,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
    with patch("correction_controller.record_correction"), \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log"):
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что было создано событие PH_TOO_LOW_DETECTED
        event_calls = [call[0][1] for call in mock_event.call_args_list]
        assert 'PH_TOO_LOW_DETECTED' in event_calls


@pytest.mark.asyncio
async def test_ec_controller_apply_correction():
    """Test applying EC correction (sending command and creating events)."""
    controller = CorrectionController(CorrectionType.EC)
    mqtt = Mock()
    gh_uid = "gh-1"
    
    command = {
        'node_uid': 'nd-ec-1',
        'channel': 'pump_nutrient',
        'cmd': 'run_pump',
        'params': {'dose_ml': 30.0, 'duration_ms': 1000, 'type': 'add_nutrients'},
        'event_type': 'EC_DOSING',
        'event_details': {
            'correction_type': 'add_nutrients',
            'current_ec': 1.5,
            'target_ec': 1.8,
            'diff': -0.3,
            'dose_ml': 30.0
        },
        'zone_id': 1,
        'correction_type_str': 'ec',
        'current_value': 1.5,
        'target_value': 1.8,
        'reason': 'Корректировка необходима'
    }
    
    from infrastructure.command_bus import CommandBus
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
    with patch("correction_controller.record_correction") as mock_record, \
         patch("correction_controller.create_zone_event") as mock_event, \
         patch("correction_controller.create_ai_log") as mock_ai_log:
        
        await controller.apply_correction(command, command_bus)
        
        # Проверяем, что команда была отправлена
        command_bus.publish_controller_command.assert_called_once()
        
        # Проверяем, что было записано в cooldown
        mock_record.assert_called_once()
        
        # Проверяем, что были созданы события (EC_DOSING и DOSING)
        assert mock_event.call_count >= 2
        
        # Проверяем, что был создан AI log
        mock_ai_log.assert_called_once()
