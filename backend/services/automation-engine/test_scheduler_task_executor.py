"""Tests for SchedulerTaskExecutor."""

from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock, Mock, patch

from scheduler_task_executor import SchedulerTaskExecutor


@pytest.mark.asyncio
async def test_execute_irrigation_success():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_fetch.return_value = [
            {"uid": "nd-irrig-1", "type": "irrigation", "channel": "pump_a"},
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
    assert result["decision"] == "execute"
    assert result["reason_code"] == "irrigation_required"
    called_kwargs = command_bus.publish_command.await_args.kwargs
    assert called_kwargs["params"]["duration_ms"] == 5000
    command_bus.publish_command.assert_awaited_once()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TASK_STARTED" in event_types
    assert "DECISION_MADE" in event_types
    assert "COMMAND_DISPATCHED" in event_types
    assert "TASK_FINISHED" in event_types


@pytest.mark.asyncio
async def test_execute_lighting_off():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

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
    assert result["decision"] == "execute"


@pytest.mark.asyncio
async def test_execute_diagnostics_zone_service_fallback():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

    zone_service = Mock()
    zone_service.process_zone = AsyncMock(return_value=None)

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)
        result = await executor.execute(
            zone_id=1,
            task_type="diagnostics",
            payload={},
        )

    assert result["success"] is True
    assert result["mode"] == "zone_service"
    assert result["decision"] == "execute"
    zone_service.process_zone.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_execute_ventilation_uses_zone_service_when_no_nodes():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)
    zone_service = Mock()
    zone_service.process_zone = AsyncMock(return_value=None)

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.return_value = []
        executor = SchedulerTaskExecutor(command_bus=command_bus, zone_service=zone_service)
        result = await executor.execute(
            zone_id=1,
            task_type="ventilation",
            payload={},
        )

    assert result["success"] is True
    assert result["mode"] == "zone_service_fallback"
    zone_service.process_zone.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_execute_irrigation_mapping_override():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        mock_fetch.return_value = [
            {"uid": "nd-custom-1", "type": "irrigation", "channel": "default"},
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
    called_kwargs = command_bus.publish_command.await_args.kwargs
    assert called_kwargs["cmd"] == "set_relay"
    assert called_kwargs["params"]["state"] is True


@pytest.mark.asyncio
async def test_execute_force_skip_returns_completed_without_commands():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

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
    command_bus.publish_command.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "DECISION_MADE" in event_types
    assert "TASK_FINISHED" in event_types


@pytest.mark.asyncio
async def test_execute_irrigation_command_failure_sets_error_code():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=False)

    with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_fetch.return_value = [{"uid": "nd-irrig-1", "type": "irrigation", "channel": "default"}]
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        result = await executor.execute(zone_id=1, task_type="irrigation", payload={})

    assert result["success"] is False
    assert result["error_code"] == "command_publish_failed"
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "COMMAND_FAILED" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_tank_already_full_skips_refill():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

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
                    "sample_ts": datetime(2026, 2, 10, 10, 0, 0),
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
            payload={"workflow": "cycle_start"},
            task_context={"task_id": "st-cycle-1", "correlation_id": "corr-cycle-1"},
        )

    assert result["success"] is True
    assert result["mode"] == "cycle_start_ready"
    assert result["action_required"] is False
    assert result["reason_code"] == "tank_refill_not_required"
    command_bus.publish_command.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "CYCLE_START_INITIATED" in event_types
    assert "NODES_AVAILABILITY_CHECKED" in event_types
    assert "TANK_LEVEL_CHECKED" in event_types


@pytest.mark.asyncio
async def test_execute_cycle_start_dispatches_refill_and_enqueues_check():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

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
                    "sample_ts": datetime(2026, 2, 10, 10, 0, 0),
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
                "config": {"execution": {"refill": {"duration_sec": 15}}},
            },
            task_context={"task_id": "st-cycle-2", "correlation_id": "corr-cycle-2"},
        )

    assert result["success"] is True
    assert result["mode"] == "cycle_start_refill_in_progress"
    assert result["reason_code"] == "tank_refill_started"
    assert result["next_check"]["enqueue_id"] == "enq-1"
    command_bus.publish_command.assert_awaited_once()
    publish_kwargs = command_bus.publish_command.await_args.kwargs
    assert publish_kwargs["node_uid"] == "nd-irrig-1"
    assert publish_kwargs["channel"] == "fill_valve"
    assert publish_kwargs["cmd"] == "run_pump"
    assert publish_kwargs["params"]["duration_ms"] == 15000
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_REFILL_STARTED" in event_types
    assert "SELF_TASK_ENQUEUED" in event_types


@pytest.mark.asyncio
async def test_execute_refill_check_timeout_emits_alert_and_fails():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)
    timeout_at = datetime.utcnow() - timedelta(seconds=5)

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
                    "sample_ts": datetime(2026, 2, 10, 10, 0, 0),
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
            },
            task_context={"task_id": "st-cycle-3", "correlation_id": "corr-cycle-3"},
        )

    assert result["success"] is False
    assert result["error_code"] == "cycle_start_refill_timeout"
    assert result["reason_code"] == "cycle_start_refill_timeout"
    command_bus.publish_command.assert_not_awaited()
    mock_alert.assert_awaited_once()
    mock_enqueue.assert_not_awaited()
    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert "TANK_REFILL_TIMEOUT" in event_types


@pytest.mark.asyncio
async def test_execute_unknown_task_type_raises():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)

    with patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock):
        executor = SchedulerTaskExecutor(command_bus=command_bus)
        with pytest.raises(ValueError):
            await executor.execute(
                zone_id=1,
                task_type="unsupported",
                payload={},
            )
