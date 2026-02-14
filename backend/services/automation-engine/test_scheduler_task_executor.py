"""Tests for SchedulerTaskExecutor."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, Mock, patch

from scheduler_task_executor import SchedulerTaskExecutor


def _build_command_bus_mock(
    *,
    command_submitted: bool = True,
    command_effect_confirmed: bool = True,
    terminal_status: str = "DONE",
):
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=command_submitted)
    command_bus.publish_controller_command_closed_loop = AsyncMock(
        return_value={
            "command_submitted": command_submitted,
            "command_effect_confirmed": command_effect_confirmed,
            "terminal_status": terminal_status,
            "cmd_id": "cmd-test-1",
            "error_code": None if command_effect_confirmed else terminal_status,
            "error": None if command_effect_confirmed else f"terminal_{terminal_status.lower()}",
        }
    )
    return command_bus


@pytest.mark.asyncio
async def test_execute_irrigation_success():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
        patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_fetch.return_value = [
            {"uid": "nd-irrig-1", "type": "irrig", "channel": "pump_a"},
        ]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"config": {"duration_sec": 5}},
            task_context={"task_id": "st-1", "correlation_id": "corr-1"},
        )

    assert result["success"] is True
    assert result["cmd"] == "run_pump"
    assert result["commands_total"] == 1
    assert result["action_required"] is True
    assert result["decision"] == "run"
    assert result["reason_code"] == "irrigation_required"
    assert result["command_submitted"] is True
    assert result["command_effect_confirmed"] is True
    assert result["run_mode"] == "run_full"
    assert isinstance(result["executed_steps"], list)
    assert isinstance(result["safety_flags"], list)
    assert "next_due_at" in result
    called_kwargs = command_bus.publish_controller_command_closed_loop.await_args.kwargs
    assert called_kwargs["command"]["params"]["duration_ms"] == 5000
    command_bus.publish_controller_command_closed_loop.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TASK_RECEIVED" in event_types
    assert "TASK_STARTED" in event_types
    assert "DECISION_MADE" in event_types
    assert "COMMAND_DISPATCHED" in event_types
    assert "TASK_FINISHED" in event_types


@pytest.mark.asyncio
async def test_execute_irrigation_success_with_uppercase_node_type_in_db():
    command_bus = _build_command_bus_mock()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes n" in normalized and "lower(trim(coalesce(n.type, ''))) = any($2::text[])" in normalized:
            assert args[1] == ["irrig"]
            return [{"uid": "nd-irrig-uc-1", "type": "IRRIG", "channel": "pump_a"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"config": {"duration_sec": 5}},
            task_context={"task_id": "st-1-uc", "correlation_id": "corr-1-uc"},
        )

    assert result["success"] is True
    assert result["commands_total"] == 1
    command_bus.publish_controller_command_closed_loop.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_irrigation_fails_with_legacy_pump_node_type_in_db():
    command_bus = _build_command_bus_mock()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes n" in normalized and "lower(trim(coalesce(n.type, ''))) = any($2::text[])" in normalized:
            assert args[1] == ["irrig"]
            return []
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"config": {"duration_sec": 3}},
            task_context={"task_id": "st-1-pump", "correlation_id": "corr-1-pump"},
        )

    assert result["success"] is False
    assert result["error_code"] == "no_online_nodes"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_lighting_off():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.return_value = [
            {"uid": "nd-light-1", "type": "light", "channel": "default"},
        ]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="lighting",
            payload={"desired_state": False},
        )

    assert result["success"] is True
    assert result["cmd"] == "light_off"
    assert result["decision"] == "run"


@pytest.mark.asyncio
async def test_execute_diagnostics_via_zone_service():
    command_bus = _build_command_bus_mock()

    zone_service = Mock()
    zone_service.process_zone = AsyncMock(return_value=None)

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)
        result = await executor.execute(
            zone_id=1,
            task_type="diagnostics",
            payload={"workflow": "diagnostics"},
        )

    assert result["success"] is True
    assert result["mode"] == "zone_service"
    assert result["decision"] == "run"
    zone_service.process_zone.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_execute_ventilation_no_online_nodes_fails_with_alert():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.return_value = []
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="ventilation",
            payload={},
        )

    assert result["success"] is False
    assert result["error_code"] == "no_online_nodes"
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_ventilation_skips_when_wind_limit_exceeded():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors s" in normalized and "s.type = $2" in normalized:
            assert args[1] == "WIND_SPEED"
            return [
                {
                    "sensor_id": 501,
                    "sensor_label": "wind",
                    "value": 12.5,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="ventilation",
            payload={
                "config": {
                    "execution": {
                        "limits": {
                            "strong_wind_mps": 10.0,
                        }
                    }
                }
            },
        )

    assert result["success"] is True
    assert result["decision"] == "skip"
    assert result["reason_code"] == "wind_blocked"
    assert result["action_required"] is False
    assert result["commands_total"] == 0
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_ventilation_skips_when_outside_temperature_below_limit():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors s" in normalized and "s.type = $2" in normalized:
            assert args[1] == "OUTSIDE_TEMP"
            return [
                {
                    "sensor_id": 502,
                    "sensor_label": "outside_temp",
                    "value": 5.5,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="ventilation",
            payload={
                "config": {
                    "execution": {
                        "limits": {
                            "low_outside_temp_c": 8.0,
                        }
                    }
                }
            },
        )

    assert result["success"] is True
    assert result["decision"] == "skip"
    assert result["reason_code"] == "outside_temp_blocked"
    assert result["action_required"] is False
    assert result["commands_total"] == 0
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_irrigation_skips_when_soil_moisture_in_norm_and_no_heat():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "sensor_inputs": {
                    "soil_moisture_pct": 82.0,
                    "ambient_temp_c": 24.0,
                    "soil_temp_c": 22.0,
                }
            },
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "skip"
    assert result["reason_code"] == "target_already_met"
    assert result["run_mode"] == "skip"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_irrigation_skips_when_already_running():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"already_running": True},
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "skip"
    assert result["reason_code"] == "already_running"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_irrigation_skips_when_outside_window():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"outside_window": True},
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "skip"
    assert result["reason_code"] == "outside_window"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_irrigation_skips_when_safety_blocked():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={"safety": {"blocked": True}},
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "skip"
    assert result["reason_code"] == "safety_blocked"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_irrigation_returns_retry_and_enqueues_internal_retry_on_low_water():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_enqueue.return_value = {
            "enqueue_id": "enq-retry-1",
            "status": "pending",
            "scheduled_for": "2026-02-13T11:00:00",
            "task_type": "irrigation",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "low_water": True,
                "config": {"execution": {"decision": {"max_retry": 3, "backoff_sec": 60}}},
            },
            task_context={"correlation_id": "corr-retry-low-water"},
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "retry"
    assert result["reason_code"] == "low_water"
    assert result["retry_attempt"] == 1
    assert result["retry_max_attempts"] == 3
    assert result["retry_backoff_sec"] == 60
    assert result["retry_enqueued"]["enqueue_id"] == "enq-retry-1"
    assert isinstance(result["next_due_at"], str)
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_enqueue.assert_awaited_once()
    enqueue_kwargs = mock_enqueue.await_args.kwargs
    assert enqueue_kwargs["correlation_id"] != "corr-retry-low-water"
    assert enqueue_kwargs["correlation_id"].startswith("corr-retry-low-water:retry1:")
    assert enqueue_kwargs["payload"]["parent_correlation_id"] == "corr-retry-low-water"
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_irrigation_retry_chain_keeps_root_parent_and_uses_unique_correlation_ids():
    command_bus = _build_command_bus_mock()

    enqueue_calls = []

    async def _enqueue_side_effect(**kwargs):
        enqueue_calls.append(kwargs)
        return {
            "enqueue_id": f"enq-retry-{len(enqueue_calls)}",
            "status": "pending",
            "scheduled_for": kwargs["scheduled_for"],
            "task_type": kwargs["task_type"],
            "correlation_id": kwargs["correlation_id"],
        }

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock):
        mock_enqueue.side_effect = _enqueue_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)

        first_result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "low_water": True,
                "config": {"execution": {"decision": {"max_retry": 3, "backoff_sec": 60}}},
            },
            task_context={"correlation_id": "corr-retry-root"},
        )

        first_retry_correlation_id = enqueue_calls[0]["correlation_id"]
        second_result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "low_water": True,
                "retry_attempt": 1,
                "parent_correlation_id": "corr-retry-root",
                "config": {"execution": {"decision": {"max_retry": 3, "backoff_sec": 60}}},
            },
            task_context={"correlation_id": first_retry_correlation_id},
        )

    assert first_result["decision"] == "retry"
    assert second_result["decision"] == "retry"
    assert len(enqueue_calls) == 2
    assert enqueue_calls[0]["correlation_id"] != enqueue_calls[1]["correlation_id"]
    assert enqueue_calls[0]["correlation_id"].startswith("corr-retry-root:retry1:")
    assert enqueue_calls[1]["correlation_id"].startswith("corr-retry-root:retry2:")
    assert enqueue_calls[0]["payload"]["parent_correlation_id"] == "corr-retry-root"
    assert enqueue_calls[1]["payload"]["parent_correlation_id"] == "corr-retry-root"
    assert enqueue_calls[1]["payload"]["previous_correlation_id"] == first_retry_correlation_id


@pytest.mark.asyncio
async def test_execute_ventilation_marks_external_fallback_when_weather_metrics_unavailable():
    command_bus = _build_command_bus_mock()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from sensors s" in normalized and "s.type = $2" in normalized:
            return []
        if "from nodes n" in normalized and "lower(trim(coalesce(n.type, ''))) = any($2::text[])" in normalized:
            return [{"uid": "nd-vent-1", "type": "climate", "channel": "default"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="ventilation",
            payload={
                "config": {
                    "execution": {
                        "limits": {
                            "strong_wind_mps": 10.0,
                            "low_outside_temp_c": 8.0,
                        }
                    }
                }
            },
        )

    assert result["success"] is True
    assert result["decision"] == "run"
    assert result["reason_code"] == "climate_external_nodes_unavailable"
    assert "climate_external_nodes_unavailable" in result["safety_flags"]
    assert result["decision_details"]["climate_fallback"]["active"] is True
    command_bus.publish_controller_command_closed_loop.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_diagnostics_without_zone_service_fails_with_alert():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="diagnostics",
            payload={"workflow": "diagnostics"},
            task_context={"task_id": "st-diag-no-service", "correlation_id": "corr-diag-no-service"},
        )

    assert result["success"] is False
    assert result["error_code"] == "diagnostics_service_unavailable"
    mock_alert.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "DIAGNOSTICS_SERVICE_UNAVAILABLE" in event_types


@pytest.mark.asyncio
async def test_execute_irrigation_mapping_override():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
        patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.return_value = [
            {"uid": "nd-custom-1", "type": "irrig", "channel": "default"},
        ]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "config": {
                    "execution": {
                        "cmd": "set_relay",
                        "params": {"state": True},
                    }
                }
            },
        )

    assert result["success"] is True
    assert result["cmd"] == "set_relay"
    called_kwargs = command_bus.publish_controller_command_closed_loop.await_args.kwargs
    assert called_kwargs["command"]["cmd"] == "set_relay"
    assert called_kwargs["command"]["params"]["state"] is True


@pytest.mark.asyncio
async def test_execute_force_skip_returns_completed_without_commands():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event:
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="diagnostics",
            payload={"config": {"execution": {"force_skip": True}}},
            task_context={"task_id": "st-skip", "correlation_id": "corr-skip"},
        )

    assert result["success"] is True
    assert result["action_required"] is False
    assert result["decision"] == "skip"
    assert result["reason_code"] == "diagnostics_not_required"
    assert result["commands_total"] == 0
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TASK_RECEIVED" in event_types
    assert "DECISION_MADE" in event_types
    assert "TASK_FINISHED" in event_types


@pytest.mark.asyncio
async def test_execute_irrigation_command_failure_sets_error_code():
    command_bus = _build_command_bus_mock(
        command_submitted=True,
        command_effect_confirmed=False,
        terminal_status="SEND_FAILED",
    )

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_fetch.return_value = [{"uid": "nd-irrig-1", "type": "irrig", "channel": "default"}]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(zone_id=1, task_type="irrigation", payload={})

    assert result["success"] is False
    assert result["error_code"] == "command_send_failed"
    assert result["command_effect_confirmed"] is False
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "COMMAND_FAILED" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_tank_already_full_skips_refill():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 17,
                    "sensor_label": "Clean tank",
                    "level": 0.99,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {"execution": {"required_node_types": ["irrig", "climate", "light"]}},
            },
            task_context={"task_id": "st-cycle-1", "correlation_id": "corr-cycle-1"},
        )

    assert result["success"] is True
    assert result["mode"] == "cycle_start_ready"
    assert result["action_required"] is False
    assert result["reason_code"] == "tank_refill_not_required"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "CYCLE_START_INITIATED" in event_types
    assert "NODES_AVAILABILITY_CHECKED" in event_types
    assert "TANK_LEVEL_CHECKED" in event_types


@pytest.mark.asyncio
async def test_execute_three_tank_cycle_start_uses_dedicated_state_machine_branch():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 117,
                    "sensor_label": "Clean tank",
                    "level": 0.99,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {
                    "execution": {
                        "topology": "three_tank_drip_substrate_trays",
                        "required_node_types": ["irrig", "climate", "light"],
                    }
                },
            },
            task_context={"task_id": "st-cycle-3tank", "correlation_id": "corr-cycle-3tank"},
        )

    assert result["success"] is True
    assert result["mode"] == "three_tank_startup_ready"
    assert result["topology"] == "three_tank_drip_substrate_trays"
    assert result["decision"] == "skip"
    assert result["reason_code"] == "tank_refill_not_required"


@pytest.mark.asyncio
async def test_execute_cycle_start_dispatches_refill_and_enqueues_check():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 18,
                    "sensor_label": "Clean tank",
                    "level": 0.45,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        if "lower(coalesce(nc.channel, '')) = any($3::text[])" in normalized:
            return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": "fill_valve"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-1",
            "scheduled_for": "2026-02-10T10:01:00",
            "expires_at": "2026-02-10T10:10:00",
            "correlation_id": "ae:self:28:diagnostics:enq-1",
            "status": "pending",
            "zone_id": 28,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {
                    "execution": {
                        "required_node_types": ["irrig", "climate", "light"],
                        "refill": {"duration_sec": 15},
                    }
                },
            },
            task_context={"task_id": "st-cycle-2", "correlation_id": "corr-cycle-2"},
        )

    assert result["success"] is True
    assert result["mode"] == "cycle_start_refill_in_progress"
    assert result["reason_code"] == "tank_refill_started"
    assert result["next_check"]["enqueue_id"] == "enq-1"
    command_bus.publish_controller_command_closed_loop.assert_awaited_once()
    publish_kwargs = command_bus.publish_controller_command_closed_loop.await_args.kwargs
    assert publish_kwargs["command"]["node_uid"] == "nd-irrig-1"
    assert publish_kwargs["command"]["channel"] == "fill_valve"
    assert publish_kwargs["command"]["cmd"] == "run_pump"
    assert publish_kwargs["command"]["params"]["duration_ms"] == 15000
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_REFILL_STARTED" in event_types
    assert "SELF_TASK_ENQUEUED" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_clamps_next_check_to_refill_timeout():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()
    refill_timeout_at = datetime.utcnow() + timedelta(seconds=20)

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 18,
                    "sensor_label": "Clean tank",
                    "level": 0.45,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        if "lower(coalesce(nc.channel, '')) = any($3::text[])" in normalized:
            return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": "fill_valve"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-clamped",
            "scheduled_for": refill_timeout_at.isoformat(),
            "expires_at": refill_timeout_at.isoformat(),
            "correlation_id": "ae:self:28:diagnostics:enq-clamped",
            "status": "pending",
            "zone_id": 28,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "refill_timeout_at": refill_timeout_at.isoformat(),
                "config": {
                    "execution": {
                        "required_node_types": ["irrig", "climate", "light"],
                        "refill": {"duration_sec": 15},
                    }
                },
            },
            task_context={"task_id": "st-cycle-clamped", "correlation_id": "corr-cycle-clamped"},
        )

    assert result["success"] is True
    mock_enqueue.assert_awaited_once()
    enqueue_kwargs = mock_enqueue.await_args.kwargs
    assert enqueue_kwargs["scheduled_for"] == refill_timeout_at.isoformat()
    assert enqueue_kwargs["expires_at"] == refill_timeout_at.isoformat()


@pytest.mark.asyncio
async def test_execute_refill_check_timeout_emits_alert_and_fails():
    command_bus = _build_command_bus_mock()
    timeout_at = datetime.utcnow() - timedelta(seconds=5)
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 19,
                    "sensor_label": "Clean tank",
                    "level": 0.40,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert, \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        mock_alert.return_value = True
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "refill_check",
                "refill_started_at": (timeout_at - timedelta(seconds=20)).isoformat(),
                "refill_timeout_at": timeout_at.isoformat(),
                "refill_attempt": 2,
                "config": {"execution": {"required_node_types": ["irrig", "climate", "light"]}},
            },
            task_context={"task_id": "st-cycle-3", "correlation_id": "corr-cycle-3"},
        )

    assert result["success"] is False
    assert result["error_code"] == "cycle_start_refill_timeout"
    assert result["reason_code"] == "cycle_start_refill_timeout"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_alert.assert_awaited_once()
    mock_enqueue.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_REFILL_TIMEOUT" in event_types


@pytest.mark.asyncio
async def test_execute_unknown_task_type_raises():
    command_bus = _build_command_bus_mock()

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        with pytest.raises(ValueError):
            await executor.execute(
                zone_id=1,
                task_type="unsupported",
                payload={},
            )


@pytest.mark.asyncio
async def test_execute_irrigation_closed_loop_no_effect_fails():
    command_bus = _build_command_bus_mock(
        command_submitted=True,
        command_effect_confirmed=False,
        terminal_status="NO_EFFECT",
    )

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.return_value = [{"uid": "nd-irrig-1", "type": "irrig", "channel": "default"}]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(zone_id=1, task_type="irrigation", payload={})

    assert result["success"] is False
    assert result["error_code"] == "command_no_effect"
    assert result["command_effect_confirmed"] is False


@pytest.mark.asyncio
async def test_execute_irrigation_two_tank_failure_starts_recovery_workflow():
    command_bus = Mock()
    call_state = {"attempt": 0}

    async def _closed_loop_side_effect(**kwargs):
        call_state["attempt"] += 1
        command = kwargs.get("command") if isinstance(kwargs.get("command"), dict) else {}
        channel = str(command.get("channel") or "")
        if call_state["attempt"] == 1 and channel == "default":
            return {
                "command_submitted": True,
                "command_effect_confirmed": False,
                "terminal_status": "NO_EFFECT",
                "cmd_id": "cmd-irrig-fail-1",
                "error_code": "NO_EFFECT",
                "error": "terminal_no_effect",
            }
        return {
            "command_submitted": True,
            "command_effect_confirmed": True,
            "terminal_status": "DONE",
            "cmd_id": f"cmd-recovery-{call_state['attempt']}",
            "error_code": None,
            "error": None,
        }

    command_bus.publish_command = AsyncMock(return_value=True)
    command_bus.publish_controller_command_closed_loop = AsyncMock(side_effect=_closed_loop_side_effect)

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes n left join node_channels nc on nc.node_id = n.id" in normalized:
            return [{"uid": "nd-irrig-1", "type": "irrig", "channel": "default"}]
        if "join node_channels nc on nc.node_id = n.id" in normalized and "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"valve_irrigation", "valve_solution_supply", "valve_solution_fill", "pump_main"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-recovery-1",
            "scheduled_for": "2026-02-13T11:01:00",
            "expires_at": "2026-02-13T11:21:00",
            "correlation_id": "ae:self:1:diagnostics:enq-recovery-1",
            "status": "pending",
            "zone_id": 1,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=1,
            task_type="irrigation",
            payload={
                "targets": {
                    "ph": {"target": 5.8},
                    "ec": {"target": 1.6},
                    "diagnostics": {
                        "execution": {
                            "topology": "two_tank_drip_substrate_trays",
                            "startup": {"required_node_types": ["irrig"]},
                            "irrigation_recovery": {"max_continue_attempts": 5, "timeout_sec": 600},
                        }
                    },
                }
            },
            task_context={"task_id": "st-irrig-recovery", "correlation_id": "corr-irrig-recovery"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_irrigation_recovery_in_progress"
    assert result["workflow"] == "irrigation_recovery"
    assert result["task_type"] == "irrigation"
    assert result["source_reason_code"] == "online_correction_failed"
    assert result["transition_reason_code"] == "tank_to_tank_correction_started"
    assert result["online_correction_error_code"] == "command_no_effect"
    assert result["next_check"]["enqueue_id"] == "enq-recovery-1"
    assert command_bus.publish_controller_command_closed_loop.await_count == 5
    mock_enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_cycle_start_stale_tank_telemetry_fails_safe():
    command_bus = _build_command_bus_mock()
    stale_sample_ts = datetime.utcnow() - timedelta(seconds=1200)

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 21,
                    "sensor_label": "Clean tank",
                    "level": 0.45,
                    "sample_ts": stale_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert, \
         patch("scheduler_task_executor.TELEMETRY_FRESHNESS_ENFORCE", True), \
         patch("scheduler_task_executor.TELEMETRY_FRESHNESS_MAX_AGE_SEC", 300):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {"execution": {"required_node_types": ["irrig", "climate", "light"]}},
            },
            task_context={"task_id": "st-cycle-stale", "correlation_id": "corr-cycle-stale"},
        )

    assert result["success"] is False
    assert result["error_code"] == "cycle_start_tank_level_stale"
    assert result["reason_code"] == "cycle_start_tank_level_stale"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_alert.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_LEVEL_STALE" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_stale_tank_telemetry_fails_safe_with_timezone_aware_sample():
    command_bus = _build_command_bus_mock()
    stale_sample_ts = datetime.now(timezone.utc) - timedelta(seconds=1200)

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return [
                {
                    "sensor_id": 22,
                    "sensor_label": "Clean tank aware ts",
                    "level": 0.40,
                    "sample_ts": stale_sample_ts,
                }
            ]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert, \
         patch("scheduler_task_executor.TELEMETRY_FRESHNESS_ENFORCE", True), \
         patch("scheduler_task_executor.TELEMETRY_FRESHNESS_MAX_AGE_SEC", 300):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {"execution": {"required_node_types": ["irrig", "climate", "light"]}},
            },
            task_context={"task_id": "st-cycle-stale-aware", "correlation_id": "corr-cycle-stale-aware"},
        )

    assert result["success"] is False
    assert result["error_code"] == "cycle_start_tank_level_stale"
    assert result["reason_code"] == "cycle_start_tank_level_stale"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_alert.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_LEVEL_STALE" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_without_tank_telemetry_fails_with_unavailable_reason():
    command_bus = _build_command_bus_mock()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [
                {"node_type": "irrig", "online_count": 1},
                {"node_type": "climate", "online_count": 1},
                {"node_type": "light", "online_count": 1},
            ]
        if "from sensors s" in normalized and "s.type = 'water_level'" in normalized:
            return []
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event, \
         patch("scheduler_task_executor.send_infra_alert", new_callable=AsyncMock) as mock_alert:
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "cycle_start",
                "config": {"execution": {"required_node_types": ["irrig", "climate", "light"]}},
            },
            task_context={"task_id": "st-cycle-no-tank", "correlation_id": "corr-cycle-no-tank"},
        )

    assert result["success"] is False
    assert result["error_code"] == "cycle_start_tank_level_unavailable"
    assert result["reason_code"] == "cycle_start_tank_level_unavailable"
    command_bus.publish_controller_command_closed_loop.assert_not_awaited()
    mock_alert.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_LEVEL_CHECKED" in event_types
    assert "TANK_LEVEL_STALE" not in event_types


@pytest.mark.asyncio
async def test_execute_two_tank_startup_starts_clean_fill_and_enqueues_check():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from sensors s" in normalized and "lower(trim(coalesce(s.label, ''))) = any($2::text[])" in normalized:
            return [
                {
                    "sensor_id": 101,
                    "sensor_label": "level_clean_max",
                    "level": 0.0,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel == "valve_clean_fill":
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": "valve_clean_fill"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-clean-1",
            "scheduled_for": "2026-02-13T10:01:00",
            "expires_at": "2026-02-13T10:20:00",
            "correlation_id": "ae:self:28:diagnostics:enq-clean-1",
            "status": "pending",
            "zone_id": 28,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "startup",
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {
                            "required_node_types": ["irrig"],
                            "level_poll_interval_sec": 60,
                            "clean_fill_timeout_sec": 1200,
                        },
                    }
                },
            },
            task_context={"task_id": "st-two-tank-startup", "correlation_id": "corr-two-tank-startup"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_clean_fill_in_progress"
    assert result["reason_code"] == "clean_fill_started"
    assert result["next_check"]["enqueue_id"] == "enq-clean-1"
    command_bus.publish_controller_command_closed_loop.assert_awaited_once()
    cmd_kwargs = command_bus.publish_controller_command_closed_loop.await_args.kwargs
    assert cmd_kwargs["command"]["channel"] == "valve_clean_fill"
    assert cmd_kwargs["command"]["cmd"] == "set_relay"
    assert cmd_kwargs["command"]["params"]["state"] is True
    mock_enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_two_tank_clean_fill_check_event_transitions_to_solution_fill():
    command_bus = _build_command_bus_mock()
    clean_started_at = datetime.utcnow() - timedelta(seconds=60)
    clean_timeout_at = datetime.utcnow() + timedelta(seconds=300)

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return [
                {
                    "id": 9001,
                    "type": "CLEAN_FILL_COMPLETED",
                    "created_at": datetime.utcnow(),
                    "details": {"source": "node_event"},
                }
            ]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"valve_clean_fill", "valve_clean_supply", "valve_solution_fill", "pump_main"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-solution-1",
            "scheduled_for": "2026-02-13T10:02:00",
            "expires_at": "2026-02-13T10:32:00",
            "correlation_id": "ae:self:28:diagnostics:enq-solution-1",
            "status": "pending",
            "zone_id": 28,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "clean_fill_check",
                "clean_fill_started_at": clean_started_at.isoformat(),
                "clean_fill_timeout_at": clean_timeout_at.isoformat(),
                "clean_fill_cycle": 1,
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                    }
                },
            },
            task_context={"task_id": "st-clean-check", "correlation_id": "corr-clean-check"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_solution_fill_in_progress"
    assert result["reason_code"] == "solution_fill_started"
    assert result["next_check"]["enqueue_id"] == "enq-solution-1"
    assert command_bus.publish_controller_command_closed_loop.await_count == 4
    mock_enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_two_tank_solution_fill_timeout_fails_and_stops_commands():
    command_bus = _build_command_bus_mock()
    stale_timeout = datetime.utcnow() - timedelta(seconds=5)
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return []
        if "from sensors s" in normalized and "lower(trim(coalesce(s.label, ''))) = any($2::text[])" in normalized:
            return [
                {
                    "sensor_id": 202,
                    "sensor_label": "level_solution_max",
                    "level": 0.0,
                    "sample_ts": fresh_sample_ts,
                }
            ]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"pump_main", "valve_solution_fill", "valve_clean_supply"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "solution_fill_check",
                "solution_fill_started_at": (stale_timeout - timedelta(seconds=30)).isoformat(),
                "solution_fill_timeout_at": stale_timeout.isoformat(),
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                    }
                },
            },
            task_context={"task_id": "st-solution-timeout", "correlation_id": "corr-solution-timeout"},
        )

    assert result["success"] is False
    assert result["mode"] == "two_tank_solution_fill_timeout"
    assert result["reason_code"] == "solution_fill_timeout"
    assert result["error_code"] == "solution_tank_not_filled_timeout"
    assert command_bus.publish_controller_command_closed_loop.await_count == 3
    mock_enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_two_tank_prepare_recirculation_starts_and_enqueues_check():
    command_bus = _build_command_bus_mock()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"valve_solution_supply", "valve_solution_fill", "pump_main"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        mock_enqueue.return_value = {
            "enqueue_id": "enq-prepare-1",
            "scheduled_for": "2026-02-13T10:10:00",
            "expires_at": "2026-02-13T10:30:00",
            "correlation_id": "ae:self:28:diagnostics:enq-prepare-1",
            "status": "pending",
            "zone_id": 28,
            "task_type": "diagnostics",
        }
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "prepare_recirculation",
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays", "startup": {"required_node_types": ["irrig"]}}},
            },
            task_context={"task_id": "st-prepare-start", "correlation_id": "corr-prepare-start"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_prepare_recirculation_in_progress"
    assert result["reason_code"] == "prepare_recirculation_started"
    assert result["next_check"]["enqueue_id"] == "enq-prepare-1"
    assert command_bus.publish_controller_command_closed_loop.await_count == 3
    mock_enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_two_tank_prepare_recirculation_check_reaches_targets():
    command_bus = _build_command_bus_mock()
    started_at = datetime.utcnow() - timedelta(seconds=120)
    timeout_at = datetime.utcnow() + timedelta(seconds=300)
    sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return []
        if "where s.zone_id = $1 and s.type = $2 and s.is_active = true" in normalized:
            sensor_type = args[1]
            if sensor_type == "PH":
                return [{"sensor_id": 31, "sensor_label": "ph_main", "value": 5.9, "sample_ts": sample_ts}]
            if sensor_type == "EC":
                return [{"sensor_id": 32, "sensor_label": "ec_main", "value": 1.7, "sample_ts": sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"pump_main", "valve_solution_fill", "valve_solution_supply"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "prepare_recirculation_check",
                "prepare_recirculation_started_at": started_at.isoformat(),
                "prepare_recirculation_timeout_at": timeout_at.isoformat(),
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                        "target_ph": 5.8,
                        "target_ec": 1.6,
                    }
                },
            },
            task_context={"task_id": "st-prepare-check", "correlation_id": "corr-prepare-check"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_prepare_recirculation_completed"
    assert result["reason_code"] == "prepare_targets_reached"
    assert result["targets_state"]["targets_reached"] is True
    assert command_bus.publish_controller_command_closed_loop.await_count == 3


@pytest.mark.asyncio
async def test_execute_two_tank_prepare_recirculation_uses_npk_ratio_target_ec():
    command_bus = _build_command_bus_mock()
    started_at = datetime.utcnow() - timedelta(seconds=120)
    timeout_at = datetime.utcnow() + timedelta(seconds=300)
    sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return []
        if "where s.zone_id = $1 and s.type = $2 and s.is_active = true" in normalized:
            sensor_type = args[1]
            if sensor_type == "PH":
                return [{"sensor_id": 51, "sensor_label": "ph_main", "value": 5.82, "sample_ts": sample_ts}]
            if sensor_type == "EC":
                # 2.0 * 40% = 0.8, для prepare должен использоваться именно этот target.
                return [{"sensor_id": 52, "sensor_label": "ec_main", "value": 0.8, "sample_ts": sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"pump_main", "valve_solution_fill", "valve_solution_supply"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "prepare_recirculation_check",
                "prepare_recirculation_started_at": started_at.isoformat(),
                "prepare_recirculation_timeout_at": timeout_at.isoformat(),
                "targets": {
                    "ph": {"target": 5.8},
                    "ec": {"target": 2.0},
                    "nutrition": {"components": {"npk": {"ratio_pct": 40}}},
                },
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                    }
                },
            },
            task_context={"task_id": "st-prepare-check-ratio", "correlation_id": "corr-prepare-check-ratio"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_prepare_recirculation_completed"
    assert result["targets_state"]["targets_reached"] is True
    assert result["targets_state"]["target_ec"] == pytest.approx(0.8, abs=0.0001)
    assert command_bus.publish_controller_command_closed_loop.await_count == 3


@pytest.mark.asyncio
async def test_execute_two_tank_prepare_recirculation_prefers_explicit_prepare_ec_override():
    command_bus = _build_command_bus_mock()
    started_at = datetime.utcnow() - timedelta(seconds=120)
    timeout_at = datetime.utcnow() + timedelta(seconds=300)
    sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return []
        if "where s.zone_id = $1 and s.type = $2 and s.is_active = true" in normalized:
            sensor_type = args[1]
            if sensor_type == "PH":
                return [{"sensor_id": 61, "sensor_label": "ph_main", "value": 5.8, "sample_ts": sample_ts}]
            if sensor_type == "EC":
                # Должно совпасть с target_ec_prepare_npk=1.1, а не с ratio-расчётом 0.8.
                return [{"sensor_id": 62, "sensor_label": "ec_main", "value": 1.1, "sample_ts": sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"pump_main", "valve_solution_fill", "valve_solution_supply"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "prepare_recirculation_check",
                "prepare_recirculation_started_at": started_at.isoformat(),
                "prepare_recirculation_timeout_at": timeout_at.isoformat(),
                "targets": {
                    "ph": {"target": 5.8},
                    "ec": {"target": 2.0},
                    "nutrition": {"components": {"npk": {"ratio_pct": 40}}},
                },
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                        "target_ec_prepare_npk": 1.1,
                    }
                },
            },
            task_context={"task_id": "st-prepare-check-override", "correlation_id": "corr-prepare-check-override"},
        )

    assert result["success"] is True
    assert result["mode"] == "two_tank_prepare_recirculation_completed"
    assert result["targets_state"]["targets_reached"] is True
    assert result["targets_state"]["target_ec"] == pytest.approx(1.1, abs=0.0001)
    assert command_bus.publish_controller_command_closed_loop.await_count == 3


@pytest.mark.asyncio
async def test_execute_two_tank_irrigation_recovery_check_attempts_exceeded():
    command_bus = _build_command_bus_mock()
    timeout_at = datetime.utcnow() - timedelta(seconds=5)
    sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "where s.zone_id = $1 and s.type = $2 and s.is_active = true" in normalized:
            sensor_type = args[1]
            if sensor_type == "PH":
                return [{"sensor_id": 41, "sensor_label": "ph_main", "value": 7.1, "sample_ts": sample_ts}]
            if sensor_type == "EC":
                return [{"sensor_id": 42, "sensor_label": "ec_main", "value": 0.4, "sample_ts": sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
            channel = args[1]
            if channel in {"pump_main", "valve_solution_fill", "valve_solution_supply"}:
                return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "irrigation_recovery_check",
                "irrigation_recovery_attempt": 5,
                "irrigation_recovery_started_at": (timeout_at - timedelta(seconds=20)).isoformat(),
                "irrigation_recovery_timeout_at": timeout_at.isoformat(),
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                        "target_ph": 5.8,
                        "target_ec": 1.6,
                        "irrigation_recovery": {"max_continue_attempts": 5},
                    }
                },
            },
            task_context={"task_id": "st-recovery-check", "correlation_id": "corr-recovery-check"},
        )

    assert result["success"] is False
    assert result["mode"] == "two_tank_irrigation_recovery_failed"
    assert result["reason_code"] == "irrigation_recovery_failed"
    assert result["error_code"] == "irrigation_recovery_attempts_exceeded"
    assert command_bus.publish_controller_command_closed_loop.await_count == 3
    mock_enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_two_tank_startup_compensates_stop_when_enqueue_fails():
    command_bus = _build_command_bus_mock()
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from sensors s" in normalized and "lower(trim(coalesce(s.label, ''))) = any($2::text[])" in normalized:
            return [{"sensor_id": 101, "sensor_label": "level_clean_max", "level": 0.0, "sample_ts": fresh_sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized and args[1] == "valve_clean_fill":
            return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": "valve_clean_fill"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock, side_effect=ValueError("enqueue failed")), \
         patch("scheduler_task_executor.AE_TWOTANK_SAFETY_GUARDS_ENABLED", True):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "startup",
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays", "startup": {"required_node_types": ["irrig"]}}},
            },
            task_context={"task_id": "st-enqueue-fail", "correlation_id": "corr-enqueue-fail"},
        )

    assert result["success"] is False
    assert result["mode"] == "two_tank_clean_fill_enqueue_failed"
    assert "stop_result" in result
    assert result["stop_result"]["success"] is True
    assert command_bus.publish_controller_command_closed_loop.await_count == 2


@pytest.mark.asyncio
async def test_execute_two_tank_clean_fill_timeout_blocks_retry_when_stop_not_confirmed():
    command_bus = Mock()

    async def _closed_loop_side_effect(**kwargs):
        command = kwargs.get("command") if isinstance(kwargs.get("command"), dict) else {}
        params = command.get("params") if isinstance(command.get("params"), dict) else {}
        state = params.get("state")
        if state is False:
            return {
                "command_submitted": True,
                "command_effect_confirmed": False,
                "terminal_status": "NO_EFFECT",
                "cmd_id": "cmd-stop-failed",
                "error_code": "NO_EFFECT",
                "error": "terminal_no_effect",
            }
        return {
            "command_submitted": True,
            "command_effect_confirmed": True,
            "terminal_status": "DONE",
            "cmd_id": "cmd-ok",
            "error_code": None,
            "error": None,
        }

    command_bus.publish_command = AsyncMock(return_value=True)
    command_bus.publish_controller_command_closed_loop = AsyncMock(side_effect=_closed_loop_side_effect)

    stale_timeout = datetime.utcnow() - timedelta(seconds=5)
    fresh_sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "from zone_events" in normalized and "type = any($2::text[])" in normalized:
            return []
        if "from sensors s" in normalized and "lower(trim(coalesce(s.label, ''))) = any($2::text[])" in normalized:
            return [{"sensor_id": 111, "sensor_label": "level_clean_max", "level": 0.0, "sample_ts": fresh_sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized and args[1] == "valve_clean_fill":
            return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": "valve_clean_fill"}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.AE_TWOTANK_SAFETY_GUARDS_ENABLED", True):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "clean_fill_check",
                "clean_fill_started_at": (stale_timeout - timedelta(seconds=30)).isoformat(),
                "clean_fill_timeout_at": stale_timeout.isoformat(),
                "clean_fill_cycle": 1,
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays", "startup": {"required_node_types": ["irrig"]}}},
            },
            task_context={"task_id": "st-clean-timeout", "correlation_id": "corr-clean-timeout"},
        )

    assert result["success"] is False
    assert result["mode"] == "two_tank_clean_fill_timeout_stop_not_confirmed"
    assert result["feature_flag_state"] is True
    assert command_bus.publish_controller_command_closed_loop.await_count == 1


@pytest.mark.asyncio
async def test_execute_two_tank_irrigation_recovery_timeout_blocks_restart_when_stop_not_confirmed():
    command_bus = Mock()

    async def _closed_loop_side_effect(**kwargs):
        command = kwargs.get("command") if isinstance(kwargs.get("command"), dict) else {}
        params = command.get("params") if isinstance(command.get("params"), dict) else {}
        state = params.get("state")
        if state is False:
            return {
                "command_submitted": True,
                "command_effect_confirmed": False,
                "terminal_status": "NO_EFFECT",
                "cmd_id": "cmd-stop-failed",
                "error_code": "NO_EFFECT",
                "error": "terminal_no_effect",
            }
        return {
            "command_submitted": True,
            "command_effect_confirmed": True,
            "terminal_status": "DONE",
            "cmd_id": "cmd-ok",
            "error_code": None,
            "error": None,
        }

    command_bus.publish_command = AsyncMock(return_value=True)
    command_bus.publish_controller_command_closed_loop = AsyncMock(side_effect=_closed_loop_side_effect)

    timeout_at = datetime.utcnow() - timedelta(seconds=5)
    sample_ts = datetime.utcnow()

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "group by lower(coalesce(n.type, ''))" in normalized:
            return [{"node_type": "irrig", "online_count": 1}]
        if "where s.zone_id = $1 and s.type = $2 and s.is_active = true" in normalized:
            sensor_type = args[1]
            if sensor_type == "PH":
                return [{"sensor_id": 41, "sensor_label": "ph_main", "value": 7.1, "sample_ts": sample_ts}]
            if sensor_type == "EC":
                return [{"sensor_id": 42, "sensor_label": "ec_main", "value": 0.4, "sample_ts": sample_ts}]
        if "lower(coalesce(nc.channel, 'default')) = $2" in normalized and args[1] in {"pump_main", "valve_solution_fill", "valve_solution_supply"}:
            return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": args[1]}]
        return []

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
         patch("scheduler_task_executor.AE_TWOTANK_SAFETY_GUARDS_ENABLED", True):
        mock_fetch.side_effect = _fetch_side_effect
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(
            zone_id=28,
            task_type="diagnostics",
            payload={
                "workflow": "irrigation_recovery_check",
                "irrigation_recovery_attempt": 1,
                "irrigation_recovery_started_at": (timeout_at - timedelta(seconds=20)).isoformat(),
                "irrigation_recovery_timeout_at": timeout_at.isoformat(),
                "config": {
                    "execution": {
                        "topology": "two_tank_drip_substrate_trays",
                        "startup": {"required_node_types": ["irrig"]},
                        "target_ph": 5.8,
                        "target_ec": 1.6,
                        "irrigation_recovery": {"max_continue_attempts": 5},
                    }
                },
            },
            task_context={"task_id": "st-recovery-timeout", "correlation_id": "corr-recovery-timeout"},
        )

    assert result["success"] is False
    assert result["mode"] == "two_tank_irrigation_recovery_timeout_stop_not_confirmed"
    assert result["feature_flag_state"] is True
    assert command_bus.publish_controller_command_closed_loop.await_count == 3
