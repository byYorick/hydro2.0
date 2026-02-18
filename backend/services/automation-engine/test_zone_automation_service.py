"""Tests for zone_automation_service."""
import asyncio
import inspect
from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import Mock, AsyncMock, patch
from common.simulation_clock import SimulationClock
import services.zone_automation_service as zas_mod
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
    command_bus.publish_controller_command = AsyncMock(return_value=True)
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
        "correction_flags": {
            "flow_active": True,
            "stable": True,
            "corrections_allowed": True,
            "flow_active_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "stable_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "corrections_allowed_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        },
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
async def test_process_correction_controllers_skips_with_missing_flags_without_sensor_mode_activation():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=15,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_not_awaited()
    service.ec_controller.check_and_correct.assert_not_awaited()
    service.command_bus.publish_controller_command.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "CORRECTION_SKIPPED_MISSING_FLAGS" in event_types


@pytest.mark.asyncio
async def test_process_correction_controllers_workflow_tank_filling_bypasses_missing_flags():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=115,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes={},
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="tank_filling",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_awaited_once()
    service.ec_controller.check_and_correct.assert_awaited_once()
    skip_events = [call for call in mock_event.await_args_list if call.args[1] == "CORRECTION_SKIPPED_MISSING_FLAGS"]
    assert not skip_events
    service.command_bus.publish_controller_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_correction_controllers_workflow_tank_filling_stale_flags_fail_closed():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    stale_ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat()
    flags = {
        "flow_active": True,
        "stable": True,
        "corrections_allowed": True,
        "flow_active_ts": stale_ts,
        "stable_ts": stale_ts,
        "corrections_allowed_ts": stale_ts,
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=117,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags=flags,
            nodes={},
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="tank_filling",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_not_awaited()
    service.ec_controller.check_and_correct.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "CORRECTION_SKIPPED_STALE_FLAGS" in event_types


@pytest.mark.asyncio
async def test_process_correction_controllers_passes_ec_components_by_workflow_phase():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)

    now_ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    flags = {
        "flow_active": True,
        "stable": True,
        "corrections_allowed": True,
        "flow_active_ts": now_ts,
        "stable_ts": now_ts,
        "corrections_allowed_ts": now_ts,
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock):
        await service._process_correction_controllers(
            zone_id=116,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags=flags,
            nodes={},
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="irrigating",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    kwargs = service.ec_controller.check_and_correct.await_args.kwargs
    assert kwargs["allowed_ec_components"] == ["calcium", "magnesium", "micro"]


@pytest.mark.asyncio
async def test_process_correction_controllers_skips_when_flags_block_corrections():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=16,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": False,
                "corrections_allowed": True,
            },
            nodes={},
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_not_awaited()
    service.ec_controller.check_and_correct.assert_not_awaited()
    service.command_bus.publish_controller_command.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert (
        "CORRECTION_SKIPPED_FLAGS_GATING" in event_types
        or "CORRECTION_SKIPPED_STALE_FLAGS" in event_types
    )


@pytest.mark.asyncio
async def test_process_correction_controllers_skips_when_flags_stale_and_deactivates_sensor_mode():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    stale_ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat()
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=26,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": True,
                "corrections_allowed": True,
                "flow_active_ts": stale_ts,
                "stable_ts": stale_ts,
                "corrections_allowed_ts": stale_ts,
            },
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_not_awaited()
    service.ec_controller.check_and_correct.assert_not_awaited()
    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode", "deactivate_sensor_mode"]
    stale_events = [
        call.args[2]
        for call in mock_event.await_args_list
        if call.args[1] == "CORRECTION_SKIPPED_STALE_FLAGS"
    ]
    assert stale_events
    assert stale_events[-1]["reason_code"] == "stale_flags"
    assert set(stale_events[-1]["stale_flags"]) == {"flow_active", "stable", "corrections_allowed"}
    assert set(stale_events[-1]["flag_age_seconds"].keys()) == {"flow_active", "stable", "corrections_allowed"}


@pytest.mark.asyncio
async def test_process_correction_controllers_stale_flags_alert_is_throttled():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    stale_ts = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)).isoformat()
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
    }
    stale_flags_payload = {
        "flow_active": True,
        "stable": True,
        "corrections_allowed": True,
        "flow_active_ts": stale_ts,
        "stable_ts": stale_ts,
        "corrections_allowed_ts": stale_ts,
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock), \
         patch("services.zone_automation_service.send_infra_alert", new_callable=AsyncMock, return_value=True) as mock_alert:
        await service._process_correction_controllers(
            zone_id=37,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags=stale_flags_payload,
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )
        await service._process_correction_controllers(
            zone_id=37,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags=stale_flags_payload,
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    stale_alerts = [call for call in mock_alert.await_args_list if call.kwargs.get("code") == "infra_correction_flags_stale"]
    assert len(stale_alerts) == 1


@pytest.mark.asyncio
async def test_process_correction_controllers_sensor_unstable_deactivates_sensor_mode():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock):
        await service._process_correction_controllers(
            zone_id=27,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": False,
                "corrections_allowed": True,
                "flow_active_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "stable_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "corrections_allowed_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            },
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode", "deactivate_sensor_mode"]


@pytest.mark.asyncio
async def test_process_correction_controllers_corrections_not_allowed_deactivates_sensor_mode():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock):
        await service._process_correction_controllers(
            zone_id=38,
            targets={"ph": {"target": 5.8}, "ec": {"target": 1.6}},
            telemetry={"PH": 6.1, "EC": 1.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": True,
                "corrections_allowed": False,
                "flow_active_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "stable_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "corrections_allowed_ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            },
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": True},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode", "deactivate_sensor_mode"]




@pytest.mark.asyncio
async def test_process_correction_controllers_missing_flags_events_are_throttled():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=33,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )
        await service._process_correction_controllers(
            zone_id=33,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    skip_events = [call for call in mock_event.await_args_list if call.args[1] == "CORRECTION_SKIPPED_MISSING_FLAGS"]
    assert len(skip_events) == 1
    state = service._get_zone_state(33)
    assert state["suppressed_correction_skip_events"] >= 1


@pytest.mark.asyncio
async def test_process_correction_controllers_missing_flags_change_emits_event_even_within_throttle():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=39,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )
        await service._process_correction_controllers(
            zone_id=39,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1, "FLOW_ACTIVE": True},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    missing_events = [call for call in mock_event.await_args_list if call.args[1] == "CORRECTION_SKIPPED_MISSING_FLAGS"]
    assert len(missing_events) == 2


@pytest.mark.asyncio
async def test_process_correction_controllers_throttle_flushes_suppressed_counter_on_reason_change():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        # 1) missing_flags -> emit
        await service._process_correction_controllers(
            zone_id=34,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )
        # 2) same reason quickly -> suppress
        await service._process_correction_controllers(
            zone_id=34,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={},
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )
        # 3) different reason -> emit and include suppressed count
        now_ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await service._process_correction_controllers(
            zone_id=34,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": False,
                "corrections_allowed": True,
                "flow_active_ts": now_ts,
                "stable_ts": now_ts,
                "corrections_allowed_ts": now_ts,
            },
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    gating_events = [
        call.args[2]
        for call in mock_event.await_args_list
        if call.args[1] in {"CORRECTION_SKIPPED_MISSING_FLAGS", "CORRECTION_SKIPPED_FLAGS_GATING"}
    ]
    assert len(gating_events) == 2
    assert gating_events[-1]["reason_code"] == "sensor_unstable"
    assert gating_events[-1]["suppressed_events_since_last_emit"] >= 1
    assert "flag_age_seconds" in gating_events[-1]



@pytest.mark.asyncio
async def test_process_correction_controllers_missing_timestamps_fail_closed_when_required():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_correction_controllers(
            zone_id=35,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": True,
                "corrections_allowed": True,
            },
            nodes=nodes,
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode"]
    gating_events = [
        call.args[2]
        for call in mock_event.await_args_list
        if call.args[1] == "CORRECTION_SKIPPED_STALE_FLAGS"
    ]
    assert gating_events
    assert gating_events[-1]["reason_code"] == "stale_flags"
    assert set(gating_events[-1]["stale_flags"]) == {"flow_active", "stable", "corrections_allowed"}


@pytest.mark.asyncio
async def test_process_correction_controllers_missing_timestamps_allowed_when_requirement_disabled():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    service.ph_controller = Mock()
    service.ph_controller.check_and_correct = AsyncMock(return_value=None)
    service.ec_controller = Mock()
    service.ec_controller.check_and_correct = AsyncMock(return_value=None)

    with patch.dict(
        ZoneAutomationService._build_correction_gating_state.__globals__,
        {"CORRECTION_FLAGS_REQUIRE_TIMESTAMPS": False},
    ), patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock):
        await service._process_correction_controllers(
            zone_id=36,
            targets={"ph": {"target": 5.8}},
            telemetry={"PH": 6.1},
            telemetry_timestamps={},
            correction_flags={
                "flow_active": True,
                "stable": True,
                "corrections_allowed": True,
            },
            nodes={},
            capabilities={"ph_control": True, "ec_control": False},
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
        )

    service.ph_controller.check_and_correct.assert_awaited_once()

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
        event_types = [call.args[1] for call in mock_event.await_args_list]
        assert "LIGHT_ON" in event_types


@pytest.mark.asyncio
async def test_irrigation_event_persisted_only_after_publish_success():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)

    irrigation_cmd = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_irrigation",
        "cmd": "run_pump",
        "params": {"duration_ms": 60000},
        "event_type": "IRRIGATION_STARTED",
        "event_details": {"duration_sec": 60},
    }

    with patch("services.zone_automation_service.check_and_control_irrigation", new_callable=AsyncMock, return_value=irrigation_cmd), \
         patch("services.zone_automation_service.can_run_pump", new_callable=AsyncMock, return_value=(True, "")), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_irrigation_controller(
            zone_id=41,
            targets={"irrigation": {"interval_sec": 300}},
            telemetry={},
            capabilities={"irrigation_control": True},
            workflow_phase="ready",
            water_level_ok=True,
            bindings={},
            actuators={"irrigation_pump": {"node_uid": "nd-irrig-1", "channel": "pump_irrigation"}},
            current_time=datetime.now(timezone.utc).replace(tzinfo=None),
            time_scale=None,
            sim_clock=None,
        )

    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "IRRIGATION_STARTED" in event_types
    assert "IRRIGATION_STARTED_COMMAND_REJECTED" not in event_types
    assert "IRRIGATION_STARTED_COMMAND_UNCONFIRMED" not in event_types


@pytest.mark.asyncio
async def test_irrigation_publish_failure_creates_rejected_event_without_phantom_success():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(return_value=False)

    irrigation_cmd = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_irrigation",
        "cmd": "run_pump",
        "params": {"duration_ms": 60000},
        "event_type": "IRRIGATION_STARTED",
        "event_details": {"duration_sec": 60},
    }

    with patch("services.zone_automation_service.check_and_control_irrigation", new_callable=AsyncMock, return_value=irrigation_cmd), \
         patch("services.zone_automation_service.can_run_pump", new_callable=AsyncMock, return_value=(True, "")), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_irrigation_controller(
            zone_id=42,
            targets={"irrigation": {"interval_sec": 300}},
            telemetry={},
            capabilities={"irrigation_control": True},
            workflow_phase="ready",
            water_level_ok=True,
            bindings={},
            actuators={"irrigation_pump": {"node_uid": "nd-irrig-1", "channel": "pump_irrigation"}},
            current_time=datetime.now(timezone.utc).replace(tzinfo=None),
            time_scale=None,
            sim_clock=None,
        )

    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "IRRIGATION_STARTED" not in event_types
    assert "IRRIGATION_STARTED_COMMAND_REJECTED" in event_types


@pytest.mark.asyncio
async def test_irrigation_circuit_breaker_creates_unconfirmed_event_without_phantom_success():
    service = _build_zone_service()
    service.command_bus.publish_controller_command = AsyncMock(side_effect=CircuitBreakerOpenError("cb_open"))

    irrigation_cmd = {
        "node_uid": "nd-irrig-1",
        "channel": "pump_irrigation",
        "cmd": "run_pump",
        "params": {"duration_ms": 60000},
        "event_type": "IRRIGATION_STARTED",
        "event_details": {"duration_sec": 60},
    }

    with patch("services.zone_automation_service.check_and_control_irrigation", new_callable=AsyncMock, return_value=irrigation_cmd), \
         patch("services.zone_automation_service.can_run_pump", new_callable=AsyncMock, return_value=(True, "")), \
         patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        await service._process_irrigation_controller(
            zone_id=43,
            targets={"irrigation": {"interval_sec": 300}},
            telemetry={},
            capabilities={"irrigation_control": True},
            workflow_phase="ready",
            water_level_ok=True,
            bindings={},
            actuators={"irrigation_pump": {"node_uid": "nd-irrig-1", "channel": "pump_irrigation"}},
            current_time=datetime.now(timezone.utc).replace(tzinfo=None),
            time_scale=None,
            sim_clock=None,
        )

    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "IRRIGATION_STARTED" not in event_types
    assert "IRRIGATION_STARTED_COMMAND_UNCONFIRMED" in event_types


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
        "phase_started_at": datetime.now(timezone.utc).replace(tzinfo=None),
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
        real_start=datetime.now(timezone.utc).replace(tzinfo=None),
        sim_start=datetime.now(timezone.utc).replace(tzinfo=None),
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


@pytest.mark.asyncio
async def test_workflow_phase_restore_uses_latest_zone_event_once():
    service = _build_zone_service()
    with patch("services.zone_automation_service.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"details": {"workflow_phase": "tank_recirc"}}]
        phase_first = await service._get_or_restore_workflow_phase(501)
        phase_second = await service._get_or_restore_workflow_phase(501)

    assert phase_first == "tank_recirc"
    assert phase_second == "tank_recirc"
    assert mock_fetch.await_count == 1


@pytest.mark.asyncio
async def test_update_workflow_phase_resets_pid_on_transition_to_irrigating():
    service = _build_zone_service()
    zone_id = 502
    state = service._get_zone_state(zone_id)
    state["workflow_phase"] = "tank_recirc"
    state["workflow_phase_loaded"] = True
    service.ph_controller._pid_by_zone[zone_id] = object()
    service.ec_controller._pid_by_zone[zone_id] = object()
    service.ph_controller._last_pid_tick[zone_id] = 1.0
    service.ec_controller._last_pid_tick[zone_id] = 1.0

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock) as mock_event:
        new_phase = await service.update_workflow_phase(
            zone_id=zone_id,
            workflow_phase="irrigating",
            workflow_stage="irrigation_recovery_check",
            reason_code="irrigation_recovery_recovered",
        )

    assert new_phase == "irrigating"
    assert zone_id not in service.ph_controller._pid_by_zone
    assert zone_id not in service.ec_controller._pid_by_zone
    assert zone_id not in service.ph_controller._last_pid_tick
    assert zone_id not in service.ec_controller._last_pid_tick
    mock_event.assert_awaited_once()
    event_payload = mock_event.await_args.args[2]
    assert event_payload["workflow_phase"] == "irrigating"
    assert event_payload["previous_workflow_phase"] == "tank_recirc"


@pytest.mark.asyncio
async def test_update_workflow_phase_clears_sensor_mode_cache_for_external_workflow_control():
    service = _build_zone_service()
    zone_id = 503
    service._correction_sensor_mode_state[zone_id] = False
    service.command_bus.publish_controller_command = AsyncMock(return_value=True)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    with patch("services.zone_automation_service.create_zone_event", new_callable=AsyncMock):
        new_phase = await service.update_workflow_phase(
            zone_id=zone_id,
            workflow_phase="tank_filling",
            workflow_stage="solution_fill_check",
            reason_code="solution_fill_started",
        )

    assert new_phase == "tank_filling"
    assert zone_id not in service._correction_sensor_mode_state

    await service._set_sensor_mode(
        zone_id=zone_id,
        nodes=nodes,
        activate=False,
        reason="sensor_unstable",
    )

    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode", "deactivate_sensor_mode"]
    assert service._correction_sensor_mode_state[zone_id] is False


@pytest.mark.asyncio
async def test_set_sensor_mode_does_not_update_cache_when_publish_not_confirmed():
    service = _build_zone_service()
    zone_id = 504
    service.command_bus.publish_controller_command = AsyncMock(return_value=False)
    nodes = {
        "ph:ph_main": {"node_uid": "nd-ph-1", "type": "ph", "channel": "ph_main"},
        "ec:ec_main": {"node_uid": "nd-ec-1", "type": "ec", "channel": "ec_main"},
    }

    await service._set_sensor_mode(
        zone_id=zone_id,
        nodes=nodes,
        activate=False,
        reason="sensor_unstable",
    )

    sent_cmds = [call.args[1]["cmd"] for call in service.command_bus.publish_controller_command.await_args_list]
    assert sent_cmds == ["deactivate_sensor_mode", "deactivate_sensor_mode"]
    assert zone_id not in service._correction_sensor_mode_state


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
            current_time=datetime.now(timezone.utc).replace(tzinfo=None),
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
            workflow_phase="idle",
            water_level_ok=True,
            bindings={},
            actuators={},
            current_time=datetime.now(timezone.utc).replace(tzinfo=None),
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
