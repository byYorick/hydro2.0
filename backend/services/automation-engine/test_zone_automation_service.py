"""Tests for zone_automation_service."""
import asyncio
import inspect
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import Mock, AsyncMock, patch
from common.simulation_clock import SimulationClock
from services.zone_automation_service import (
    ZoneAutomationService,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    DEGRADED_MODE_THRESHOLD,
)
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository, GrowCycleRepository, InfrastructureRepository
from infrastructure.command_bus import CommandBus
from infrastructure.circuit_breaker import CircuitBreakerOpenError


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
    
    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )
    service._emit_missing_targets_signal = AsyncMock()
    await service.process_zone(1)
    
    # Должен вернуться рано, не загружая данные зоны
    recipe_repo.get_zone_data_batch.assert_not_called()
    service._emit_missing_targets_signal.assert_awaited_once()


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
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value={
        "targets": {
            "ph": {"target": 6.5},
            "ec": {"target": 1.8},
            "climate_request": {"temp_air_target": 25.0},
        },
    })
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {
                "ph": {"target": 6.5},
                "ec": {"target": 1.8},
                "climate_request": {"temp_air_target": 25.0},
            },
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
        
        # Мокируем CorrectionController
        mock_ph_controller = Mock()
        mock_ph_controller.check_and_correct = AsyncMock(return_value=None)
        mock_ec_controller = Mock()
        mock_ec_controller.check_and_correct = AsyncMock(return_value=None)
        mock_correction.side_effect = [mock_ph_controller, mock_ec_controller]
        
        service = ZoneAutomationService(
            zone_repo,
            telemetry_repo,
            node_repo,
            recipe_repo,
            grow_cycle_repo,
            infrastructure_repo,
            command_bus,
        )
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
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value={
        "targets": {"lighting": {"photoperiod_hours": 16, "start_time": "06:00"}},
    })
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"lighting": {"photoperiod_hours": 16, "start_time": "06:00"}},
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
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value={
        "targets": {},
    })
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
    
    with patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions") as mock_phase_check:
        service = ZoneAutomationService(
            zone_repo,
            telemetry_repo,
            node_repo,
            recipe_repo,
            grow_cycle_repo,
            infrastructure_repo,
            command_bus,
        )
        service._emit_missing_targets_signal = AsyncMock()
        await service.process_zone(1)

        mock_phase_check.assert_called_once_with(1, None)
        service._emit_missing_targets_signal.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_phase_transitions_skips_for_live_simulation():
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    grow_cycle_repo.get_current_phase_timing = AsyncMock(return_value={
        "grow_cycle_id": 1,
        "phase_index": 0,
        "max_phase_index": 0,
        "duration_hours": 1,
        "phase_started_at": datetime.now(timezone.utc),
    })

    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )

    sim_clock = SimulationClock(
        real_start=datetime.now(timezone.utc),
        sim_start=datetime.now(timezone.utc),
        time_scale=60.0,
        mode="live",
    )

    await service._check_phase_transitions(1, sim_clock)

    grow_cycle_repo.get_current_phase_timing.assert_not_called()


def _build_zone_service() -> ZoneAutomationService:
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)
    return ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )


def test_calculate_backoff_seconds_is_exponential_and_capped():
    service = _build_zone_service()

    assert service._calculate_backoff_seconds(0) == 0
    assert service._calculate_backoff_seconds(1) == INITIAL_BACKOFF_SECONDS
    assert service._calculate_backoff_seconds(2) == INITIAL_BACKOFF_SECONDS * 2
    assert service._calculate_backoff_seconds(3) == INITIAL_BACKOFF_SECONDS * 4
    assert service._calculate_backoff_seconds(100) == MAX_BACKOFF_SECONDS


def test_record_zone_error_increments_streak_and_updates_next_allowed_time():
    service = _build_zone_service()
    zone_id = 77
    t0 = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 8, 12, 1, 0, tzinfo=timezone.utc)

    with patch("services.zone_automation_service.utcnow", side_effect=[t0, t1]):
        service._record_zone_error(zone_id)
        state_after_first = service._get_zone_state(zone_id).copy()
        service._record_zone_error(zone_id)
        state_after_second = service._get_zone_state(zone_id).copy()

    assert state_after_first["error_streak"] == 1
    assert state_after_first["next_allowed_run_at"] == t0 + timedelta(seconds=INITIAL_BACKOFF_SECONDS)
    assert state_after_second["error_streak"] == 2
    assert state_after_second["next_allowed_run_at"] == t1 + timedelta(seconds=INITIAL_BACKOFF_SECONDS * 2)


def test_should_process_zone_respects_backoff_window():
    service = _build_zone_service()
    zone_id = 88
    next_allowed = datetime(2026, 2, 8, 12, 5, 0, tzinfo=timezone.utc)
    service._zone_states[zone_id] = {
        "error_streak": 1,
        "next_allowed_run_at": next_allowed,
    }

    with patch("services.zone_automation_service.utcnow", return_value=next_allowed - timedelta(seconds=1)):
        assert service._should_process_zone(zone_id) is False

    with patch("services.zone_automation_service.utcnow", return_value=next_allowed + timedelta(seconds=1)):
        assert service._should_process_zone(zone_id) is True


def test_is_degraded_mode_uses_threshold():
    service = _build_zone_service()
    zone_id = 99

    service._zone_states[zone_id] = {"error_streak": DEGRADED_MODE_THRESHOLD - 1, "next_allowed_run_at": None}
    assert service._is_degraded_mode(zone_id) is False

    service._zone_states[zone_id] = {"error_streak": DEGRADED_MODE_THRESHOLD, "next_allowed_run_at": None}
    assert service._is_degraded_mode(zone_id) is True


@pytest.mark.asyncio
async def test_process_zone_skips_all_work_when_in_backoff():
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)

    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={})
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})

    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )
    service._emit_backoff_skip_signal = AsyncMock()

    now = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    service._zone_states[123] = {
        "error_streak": 1,
        "next_allowed_run_at": now + timedelta(seconds=30),
    }

    with patch("services.zone_automation_service.utcnow", return_value=now):
        await service.process_zone(123)

    grow_cycle_repo.get_active_grow_cycle.assert_not_called()
    recipe_repo.get_zone_data_batch.assert_not_called()
    service._emit_backoff_skip_signal.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_process_zone_backoff_skip_emits_signal_once_per_window():
    service = _build_zone_service()
    zone_id = 144
    now = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    next_allowed = now + timedelta(seconds=30)
    service._zone_states[zone_id] = {
        "error_streak": 2,
        "next_allowed_run_at": next_allowed,
        "last_backoff_reported_until": None,
        "degraded_alert_active": False,
        "last_missing_targets_report_at": None,
    }

    with patch("services.zone_automation_service.utcnow", return_value=now), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        await service.process_zone(zone_id)
        await service.process_zone(zone_id)

    assert mock_event.await_count == 1
    assert mock_alert.await_count == 1


@pytest.mark.asyncio
async def test_process_zone_backoff_skip_retries_when_event_and_alert_fail():
    service = _build_zone_service()
    zone_id = 145
    now = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    next_allowed = now + timedelta(seconds=30)
    service._zone_states[zone_id] = {
        "error_streak": 2,
        "next_allowed_run_at": next_allowed,
        "last_backoff_reported_until": None,
        "degraded_alert_active": False,
        "last_missing_targets_report_at": None,
    }

    with patch("services.zone_automation_service.utcnow", return_value=now), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("db fail")) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=False) as mock_alert, \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_event_fail_alert:
        await service.process_zone(zone_id)
        await service.process_zone(zone_id)

    assert mock_event.await_count == 2
    assert mock_alert.await_count == 2
    assert mock_event_fail_alert.await_count == 2
    assert service._zone_states[zone_id]["last_backoff_reported_until"] is None


@pytest.mark.asyncio
async def test_process_zone_backoff_skip_marks_reported_when_alert_delivered():
    service = _build_zone_service()
    zone_id = 146
    now = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    next_allowed = now + timedelta(seconds=30)
    service._zone_states[zone_id] = {
        "error_streak": 2,
        "next_allowed_run_at": next_allowed,
        "last_backoff_reported_until": None,
        "degraded_alert_active": False,
        "last_missing_targets_report_at": None,
    }

    with patch("services.zone_automation_service.utcnow", return_value=now), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("db fail")) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=True) as mock_alert, \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_event_fail_alert:
        await service.process_zone(zone_id)
        await service.process_zone(zone_id)

    assert mock_event.await_count == 1
    assert mock_alert.await_count == 1
    assert mock_event_fail_alert.await_count == 1
    assert service._zone_states[zone_id]["last_backoff_reported_until"] == next_allowed


@pytest.mark.asyncio
async def test_process_zone_missing_targets_emits_throttled_alert():
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)

    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value={"targets": None})

    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )

    t0 = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=30)
    with patch("services.zone_automation_service.ZoneAutomationService._check_zone_deletion", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_pid_config_updates", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions", new_callable=AsyncMock), \
         patch("services.zone_automation_service.utcnow", side_effect=[t0, t1]), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        await service.process_zone(1)
        await service.process_zone(1)

    assert mock_event.await_count == 1
    assert mock_alert.await_count == 1


@pytest.mark.asyncio
async def test_process_zone_missing_targets_retries_when_event_and_alert_fail():
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)

    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value={"targets": None})

    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )

    t0 = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=30)
    with patch("services.zone_automation_service.ZoneAutomationService._check_zone_deletion", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_pid_config_updates", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions", new_callable=AsyncMock), \
         patch("services.zone_automation_service.utcnow", side_effect=[t0, t1]), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("db fail")) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=False) as mock_alert, \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_event_fail_alert:
        await service.process_zone(1)
        await service.process_zone(1)

    assert mock_event.await_count == 2
    assert mock_alert.await_count == 2
    assert mock_event_fail_alert.await_count == 2
    assert service._zone_states[1]["last_missing_targets_report_at"] is None


@pytest.mark.asyncio
async def test_safe_process_controller_cooldown_skip_emits_throttled_signal():
    service = _build_zone_service()
    zone_id = 211
    controller = "irrigation"
    failure_time = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    service._controller_failures[(zone_id, controller)] = failure_time

    with patch("services.zone_automation_service.utcnow", return_value=failure_time + timedelta(seconds=10)), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        await service._safe_process_controller(controller, None, zone_id)
        await service._safe_process_controller(controller, None, zone_id)

    assert mock_event.await_count == 1
    assert mock_alert.await_count == 1


@pytest.mark.asyncio
async def test_safe_process_controller_closes_coro_when_in_cooldown():
    service = _build_zone_service()
    zone_id = 240
    controller = "light"
    failure_time = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    service._controller_failures[(zone_id, controller)] = failure_time
    service._emit_controller_cooldown_skip_signal = AsyncMock()
    async def controller_coro():
        await asyncio.sleep(60)

    coro_obj = controller_coro()

    with patch("services.zone_automation_service.utcnow", return_value=failure_time + timedelta(seconds=10)):
        await service._safe_process_controller(controller, coro_obj, zone_id)

    assert inspect.getcoroutinestate(coro_obj) == "CORO_CLOSED"
    service._emit_controller_cooldown_skip_signal.assert_awaited_once_with(zone_id, controller)


@pytest.mark.asyncio
async def test_safe_process_controller_cooldown_skip_retries_when_event_and_alert_fail():
    service = _build_zone_service()
    zone_id = 212
    controller = "irrigation"
    failure_time = datetime(2026, 2, 8, 12, 0, 0, tzinfo=timezone.utc)
    service._controller_failures[(zone_id, controller)] = failure_time

    with patch("services.zone_automation_service.utcnow", return_value=failure_time + timedelta(seconds=10)), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("db fail")) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=False) as mock_alert, \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_event_fail_alert:
        await service._safe_process_controller(controller, None, zone_id)
        await service._safe_process_controller(controller, None, zone_id)

    assert mock_event.await_count == 2
    assert mock_alert.await_count == 2
    assert mock_event_fail_alert.await_count == 2


@pytest.mark.asyncio
async def test_emit_degraded_mode_signal_retries_when_event_and_alert_fail():
    service = _build_zone_service()
    zone_id = 188
    service._zone_states[zone_id] = {
        "error_streak": DEGRADED_MODE_THRESHOLD,
        "next_allowed_run_at": None,
        "last_backoff_reported_until": None,
        "degraded_alert_active": False,
        "last_missing_targets_report_at": None,
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("db fail")) as mock_event, \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=False) as mock_alert, \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_event_fail_alert:
        await service._emit_degraded_mode_signal(zone_id)
        await service._emit_degraded_mode_signal(zone_id)

    assert mock_event.await_count == 2
    assert mock_alert.await_count == 2
    assert mock_event_fail_alert.await_count == 2
    assert service._zone_states[zone_id]["degraded_alert_active"] is False


@pytest.mark.asyncio
async def test_process_zone_emits_alert_when_zone_data_unavailable():
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    grow_cycle_repo = Mock(spec=GrowCycleRepository)
    infrastructure_repo = Mock(spec=InfrastructureRepository)
    command_bus = Mock(spec=CommandBus)

    grow_cycle_repo.get_active_grow_cycle = AsyncMock(side_effect=CircuitBreakerOpenError("db cb open"))

    service = ZoneAutomationService(
        zone_repo,
        telemetry_repo,
        node_repo,
        recipe_repo,
        grow_cycle_repo,
        infrastructure_repo,
        command_bus,
    )

    with patch("services.zone_automation_service.ZoneAutomationService._check_zone_deletion", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_pid_config_updates", new_callable=AsyncMock), \
         patch("services.zone_automation_service.ZoneAutomationService._check_phase_transitions", new_callable=AsyncMock), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock), \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        await service.process_zone(1)

    mock_alert.assert_awaited_once()
    kwargs = mock_alert.await_args.kwargs
    assert kwargs["code"] == "infra_zone_data_unavailable"


@pytest.mark.asyncio
async def test_emit_zone_recovered_signal_sends_resolved_alerts():
    service = _build_zone_service()

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock), \
         patch("services.zone_automation_service.send_infra_resolved_alert", new_callable=AsyncMock, return_value=True) as mock_resolved:
        await service._emit_zone_recovered_signal(zone_id=5, previous_error_streak=3)

    sent_codes = [call.kwargs["code"] for call in mock_resolved.await_args_list]
    assert sent_codes == [
        "infra_zone_degraded_mode",
        "infra_zone_data_unavailable",
        "infra_zone_backoff_skip",
        "infra_zone_targets_missing",
    ]


@pytest.mark.asyncio
async def test_process_light_controller_emits_circuit_open_alert():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(side_effect=CircuitBreakerOpenError("api cb open"))

    light_cmd = {
        "node_uid": "nd-light-1",
        "channel": "default",
        "cmd": "set_relay",
        "params": {"state": True},
        "event_type": "LIGHT_ON",
        "event_details": {},
    }
    with patch("services.zone_automation_service.check_and_control_lighting", new_callable=AsyncMock, return_value=light_cmd), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock), \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=True) as mock_alert:
        await service._process_light_controller(
            zone_id=10,
            targets={},
            capabilities={"light_control": True},
            bindings={},
            current_time=datetime.now(timezone.utc),
        )

    sent_codes = [call.kwargs["code"] for call in mock_alert.await_args_list]
    assert "infra_controller_command_skipped_circuit_open" in sent_codes


@pytest.mark.asyncio
async def test_process_irrigation_controller_emits_pump_blocked_alert():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)

    irrigation_cmd = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_irrigation",
        "cmd": "run_pump",
        "params": {"duration_ms": 1000},
        "event_type": "IRRIGATION_STARTED",
        "event_details": {},
    }
    with patch("services.zone_automation_service.check_and_control_irrigation", new_callable=AsyncMock, return_value=irrigation_cmd), \
         patch("services.zone_automation_service.can_run_pump", new_callable=AsyncMock, return_value=(False, "safety blocked")), \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=True) as mock_alert:
        await service._process_irrigation_controller(
            zone_id=11,
            targets={},
            telemetry={},
            capabilities={"irrigation_control": True},
            water_level_ok=True,
            bindings={},
            actuators={},
            current_time=datetime.now(timezone.utc),
            time_scale=None,
            sim_clock=None,
        )

    sent_codes = [call.kwargs["code"] for call in mock_alert.await_args_list]
    assert "infra_irrigation_pump_blocked" in sent_codes


@pytest.mark.asyncio
async def test_check_zone_deletion_emits_alert_on_exception():
    service = _build_zone_service()
    with patch("common.db.fetch", new=AsyncMock(side_effect=RuntimeError("db unavailable"))), \
         patch("services.zone_automation_service.send_infra_exception_alert", new_callable=AsyncMock) as mock_alert:
        await service._check_zone_deletion(12)

    mock_alert.assert_awaited_once()
    assert mock_alert.await_args.kwargs["code"] == "infra_zone_deletion_check_failed"
