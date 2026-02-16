"""Unit tests for application.device_task_core helpers."""

from unittest.mock import AsyncMock

import pytest

from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome
from application.device_task_core import execute_device_task_core


@pytest.mark.asyncio
async def test_execute_device_task_core_returns_error_when_mapping_has_no_nodes():
    mapping = SchedulerTaskMapping(task_type="irrigation", node_types=())
    result = await execute_device_task_core(
        zone_id=1,
        payload={},
        mapping=mapping,
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        get_zone_nodes_fn=AsyncMock(),
        resolve_command_name_fn=lambda *_: None,
        resolve_command_params_fn=lambda *_: {},
        publish_batch_fn=AsyncMock(),
        send_infra_alert_fn=AsyncMock(),
        err_mapping_not_found="mapping_not_found",
        err_no_online_nodes="no_online_nodes",
    )
    assert result["error_code"] == "mapping_not_found"


@pytest.mark.asyncio
async def test_execute_device_task_core_alerts_when_no_online_nodes():
    mapping = SchedulerTaskMapping(task_type="irrigation", node_types=("irrig",))
    send_alert = AsyncMock(return_value=True)
    result = await execute_device_task_core(
        zone_id=1,
        payload={},
        mapping=mapping,
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        get_zone_nodes_fn=AsyncMock(return_value=[]),
        resolve_command_name_fn=lambda *_: "set",
        resolve_command_params_fn=lambda *_: {"state": True},
        publish_batch_fn=AsyncMock(return_value={"success": True}),
        send_infra_alert_fn=send_alert,
        err_mapping_not_found="mapping_not_found",
        err_no_online_nodes="no_online_nodes",
    )
    assert result["error_code"] == "no_online_nodes"
    send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_device_task_core_publishes_when_ready():
    mapping = SchedulerTaskMapping(task_type="irrigation", node_types=("irrig",))
    publish_batch = AsyncMock(return_value={"success": True})
    result = await execute_device_task_core(
        zone_id=1,
        payload={"x": 1},
        mapping=mapping,
        context={"task_id": "st-1"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        get_zone_nodes_fn=AsyncMock(return_value=[{"node_uid": "nd-1", "channel": "pump_main"}]),
        resolve_command_name_fn=lambda *_: "set",
        resolve_command_params_fn=lambda *_: {"state": True},
        publish_batch_fn=publish_batch,
        send_infra_alert_fn=AsyncMock(return_value=True),
        err_mapping_not_found="mapping_not_found",
        err_no_online_nodes="no_online_nodes",
    )
    assert result["success"] is True
    publish_batch.assert_awaited_once()
