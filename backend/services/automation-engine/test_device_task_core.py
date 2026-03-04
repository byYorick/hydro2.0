from __future__ import annotations

import pytest

from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome
from executor.device_task_core import execute_device_task_core


@pytest.mark.asyncio
async def test_execute_device_task_core_blocks_run_pump_when_safety_fails(monkeypatch):
    alerts: list[dict] = []

    async def _fake_can_run_pump(zone_id, pump_channel, node_id=None):
        assert zone_id == 2
        assert pump_channel == "pump_main"
        assert node_id == 7
        return False, "Water level too low: 0.0 < 0.15"

    monkeypatch.setattr("executor.device_task_core.can_run_pump", _fake_can_run_pump)

    async def _get_zone_nodes(_zone_id, _node_types):
        return [{"id": 7, "uid": "nd-test-irrig-1", "channel": "pump_main"}]

    async def _publish_batch(**_kwargs):
        raise AssertionError("publish_batch must not be called when safety gate blocks run_pump")

    async def _send_alert(**kwargs):
        alerts.append(dict(kwargs))

    result = await execute_device_task_core(
        zone_id=2,
        payload={"config": {"execution": {}}},
        mapping=SchedulerTaskMapping(task_type="irrigation", node_types=("irrig",), cmd="run_pump"),
        context={"task_id": "st-1"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="irrigation_required", reason="run"),
        get_zone_nodes_fn=_get_zone_nodes,
        resolve_command_name_fn=lambda _payload, _mapping: "run_pump",
        resolve_command_params_fn=lambda _payload, _mapping: {"duration_ms": 60000},
        publish_batch_fn=_publish_batch,
        send_infra_alert_fn=_send_alert,
        err_mapping_not_found="mapping_not_found",
        err_no_online_nodes="no_online_nodes",
    )

    assert result["success"] is False
    assert result["error_code"] == "two_tank_pump_safety_blocked"
    assert alerts
    assert alerts[0]["code"] == "infra_irrigation_pump_blocked"


@pytest.mark.asyncio
async def test_execute_device_task_core_non_pump_command_bypasses_safety(monkeypatch):
    async def _unexpected_can_run_pump(*_args, **_kwargs):
        raise AssertionError("can_run_pump must not be called for non-pump commands")

    monkeypatch.setattr("executor.device_task_core.can_run_pump", _unexpected_can_run_pump)

    async def _get_zone_nodes(_zone_id, _node_types):
        return [{"id": 5, "uid": "nd-test-light-1", "channel": "white_light"}]

    async def _publish_batch(**kwargs):
        return {
            "success": True,
            "task_type": kwargs["task_type"],
            "commands_total": 1,
            "commands_failed": 0,
            "command_statuses": [{"status": "DONE"}],
        }

    async def _send_alert(**_kwargs):
        raise AssertionError("send_infra_alert should not be called")

    result = await execute_device_task_core(
        zone_id=2,
        payload={"desired_state": True},
        mapping=SchedulerTaskMapping(
            task_type="lighting",
            node_types=("light",),
            cmd_true="light_on",
            cmd_false="light_off",
            state_key="desired_state",
            default_state=True,
        ),
        context={"task_id": "st-2"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="lighting_required", reason="run"),
        get_zone_nodes_fn=_get_zone_nodes,
        resolve_command_name_fn=lambda _payload, _mapping: "light_on",
        resolve_command_params_fn=lambda _payload, _mapping: {},
        publish_batch_fn=_publish_batch,
        send_infra_alert_fn=_send_alert,
        err_mapping_not_found="mapping_not_found",
        err_no_online_nodes="no_online_nodes",
    )

    assert result["success"] is True
    assert result["task_type"] == "lighting"
