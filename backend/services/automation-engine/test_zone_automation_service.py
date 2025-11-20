"""Tests for zone_automation_service."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from services.zone_automation_service import ZoneAutomationService
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from infrastructure.command_bus import CommandBus


@pytest.mark.asyncio
async def test_process_zone_no_recipe():
    """Test processing zone without recipe."""
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    command_bus = Mock(spec=CommandBus)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": None,
        "telemetry": {},
        "nodes": {},
        "capabilities": {}
    })
    
    service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus)
    await service.process_zone(1)
    
    # Должен вернуться рано, не вызывая контроллеры
    recipe_repo.get_zone_data_batch.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_process_zone_with_recipe():
    """Test processing zone with recipe."""
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    command_bus = Mock(spec=CommandBus)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8, "temp_air": 25.0},
            "phase_name": "Germination"
        },
        "telemetry": {"PH": 6.3, "EC": 1.7, "TEMP_AIR": 24.0},
        "nodes": {
            "irrig:default": {"node_uid": "nd-irrig-1", "channel": "default", "type": "irrig"}
        },
        "capabilities": {
            "ph_control": True,
            "ec_control": True,
            "climate_control": True,
            "light_control": True,
            "irrigation_control": True,
            "recirculation": False,
            "flow_sensor": True,
        }
    })
    
    with patch("services.zone_automation_service.calculate_current_phase") as mock_phase, \
         patch("services.zone_automation_service.check_water_level") as mock_water, \
         patch("services.zone_automation_service.check_and_control_lighting") as mock_light, \
         patch("services.zone_automation_service.check_and_control_climate") as mock_climate, \
         patch("services.zone_automation_service.check_and_control_irrigation") as mock_irrigation, \
         patch("services.zone_automation_service.check_and_control_recirculation") as mock_recirculation, \
         patch("services.zone_automation_service.calculate_zone_health") as mock_health, \
         patch("services.zone_automation_service.CorrectionController") as mock_correction:
        
        mock_phase.return_value = None
        mock_water.return_value = (True, 0.5)
        mock_light.return_value = None
        mock_climate.return_value = []
        mock_irrigation.return_value = None
        mock_recirculation.return_value = None
        mock_health.return_value = {"health_score": 85.0, "health_status": "ok"}
        
        # Мокируем CorrectionController
        mock_ph_controller = Mock()
        mock_ph_controller.check_and_correct = AsyncMock(return_value=None)
        mock_ec_controller = Mock()
        mock_ec_controller.check_and_correct = AsyncMock(return_value=None)
        mock_correction.side_effect = [mock_ph_controller, mock_ec_controller]
        
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus)
        await service.process_zone(1)
        
        # Проверяем, что все контроллеры были вызваны
        mock_light.assert_called_once()
        mock_climate.assert_called_once()
        mock_irrigation.assert_called_once()
        mock_ph_controller.check_and_correct.assert_called_once()
        mock_ec_controller.check_and_correct.assert_called_once()


@pytest.mark.asyncio
async def test_process_zone_light_controller():
    """Test processing zone with light controller command."""
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"light_hours": "06:00-22:00"},
            "phase_name": "Germination"
        },
        "telemetry": {},
        "nodes": {
            "light:default": {"node_uid": "nd-light-1", "channel": "default", "type": "light"}
        },
        "capabilities": {
            "light_control": True,
            "ph_control": False,
            "ec_control": False,
            "climate_control": False,
            "irrigation_control": False,
            "recirculation": False,
            "flow_sensor": False,
        }
    })
    
    with patch("services.zone_automation_service.calculate_current_phase") as mock_phase, \
         patch("services.zone_automation_service.check_water_level") as mock_water, \
         patch("services.zone_automation_service.check_and_control_lighting") as mock_light, \
         patch("services.zone_automation_service.create_zone_event") as mock_event, \
         patch("services.zone_automation_service.calculate_zone_health") as mock_health:
        
        mock_phase.return_value = None
        mock_water.return_value = (True, 0.5)
        mock_light.return_value = {
            'node_uid': 'nd-light-1',
            'channel': 'default',
            'cmd': 'set_relay',
            'params': {'state': True},
            'event_type': 'LIGHT_ON',
            'event_details': {}
        }
        mock_health.return_value = {"health_score": 85.0, "health_status": "ok"}
        
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus)
        await service.process_zone(1)
        
        # Проверяем, что команда была отправлена
        command_bus.publish_controller_command.assert_called_once()
        mock_event.assert_called_once()


@pytest.mark.asyncio
async def test_process_zone_phase_transition():
    """Test processing zone with phase transition."""
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    command_bus = Mock(spec=CommandBus)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {},
            "phase_name": "Germination"
        },
        "telemetry": {},
        "nodes": {},
        "capabilities": {}
    })
    
    with patch("services.zone_automation_service.calculate_current_phase") as mock_phase, \
         patch("services.zone_automation_service.advance_phase") as mock_advance, \
         patch("services.zone_automation_service.create_zone_event") as mock_event:
        
        mock_phase.return_value = {
            "phase_index": 0,
            "target_phase_index": 1,
            "should_transition": True
        }
        mock_advance.return_value = True
        
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus)
        await service.process_zone(1)
        
        # Проверяем, что фаза была переведена
        mock_advance.assert_called_once_with(1, 1)
        mock_event.assert_called_once()

