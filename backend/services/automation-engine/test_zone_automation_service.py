"""Tests for zone_automation_service."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from services.zone_automation_service import ZoneAutomationService
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository, GrowCycleRepository, InfrastructureRepository
from infrastructure.command_bus import CommandBus


@pytest.mark.asyncio
async def test_process_zone_no_recipe():
    """Test processing zone without recipe."""
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": None,
        "telemetry": {},
        "nodes": {},
        "capabilities": {}
    })
    
    with patch("services.zone_automation_service.calculate_current_phase", return_value=None):
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus)
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
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8, "temp_air": 25.0},
            "phase_name": "Germination"
        },
        "telemetry": {"PH": 6.3, "EC": 1.7, "TEMPERATURE": 24.0},
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
    
    with patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions") as mock_phase_check, \
         patch("services.zone_automation_service.check_water_level", return_value=(True, 0.5)) as mock_water, \
         patch("services.zone_automation_service.ensure_water_level_alert") as mock_water_alert, \
         patch("services.zone_automation_service.calculate_zone_health", return_value={"health_score": 85.0, "health_status": "ok"}) as mock_health, \
         patch("services.zone_automation_service.update_zone_health_in_db") as mock_update_health, \
         patch("services.zone_automation_service.check_and_control_lighting", return_value=None) as mock_light, \
         patch("services.zone_automation_service.check_and_control_climate", return_value=[]) as mock_climate, \
         patch("services.zone_automation_service.check_and_control_irrigation", return_value=None) as mock_irrigation, \
         patch("services.zone_automation_service.check_and_control_recirculation", return_value=None) as mock_recirculation, \
         patch("services.zone_automation_service.create_zone_event") as mock_event, \
         patch("correction_controller.create_zone_event") as mock_correction_event, \
         patch("correction_controller.create_ai_log") as mock_ai_log, \
         patch("correction_controller.should_apply_correction", return_value=(True, "Ready")) as mock_should_correct, \
         patch("correction_controller.CorrectionController") as mock_correction:
        
        mock_phase_check.return_value = None
        # Мокируем CorrectionController
        mock_ph_controller = Mock()
        mock_ph_controller.check_and_correct = AsyncMock(return_value=None)
        mock_ec_controller = Mock()
        mock_ec_controller.check_and_correct = AsyncMock(return_value=None)
        mock_correction.side_effect = [mock_ph_controller, mock_ec_controller]
        
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus)
        # Заменяем реальные контроллеры на моки
        service.ph_controller = mock_ph_controller
        service.ec_controller = mock_ec_controller
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
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    command_bus.publish_controller_command = AsyncMock(return_value=True)
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
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
    
    with patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions") as mock_phase_check, \
         patch("services.zone_automation_service.check_water_level", return_value=(True, 0.5)) as mock_water, \
         patch("services.zone_automation_service.ensure_water_level_alert") as mock_water_alert, \
         patch("services.zone_automation_service.calculate_zone_health", return_value={"health_score": 85.0, "health_status": "ok"}) as mock_health, \
         patch("services.zone_automation_service.update_zone_health_in_db") as mock_update_health, \
         patch("services.zone_automation_service.check_and_control_lighting", return_value={
            'node_uid': 'nd-light-1',
            'channel': 'default',
            'cmd': 'set_relay',
            'params': {'state': True},
            'event_type': 'LIGHT_ON',
            'event_details': {}
        }) as mock_light, \
         patch("services.zone_automation_service.create_zone_event") as mock_event:
        
        mock_phase_check.return_value = None
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus)
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
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
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
        
        service = ZoneAutomationService(zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus)
        await service.process_zone(1)
        
        # Проверяем, что фаза была переведена
        mock_advance.assert_called_once_with(1, 1)
        mock_event.assert_called_once()
