"""Unit tests for application.sensor_mode_dispatch helpers."""

import asyncio
from unittest.mock import AsyncMock

from domain.models.decision_models import DecisionOutcome
from application.sensor_mode_dispatch import dispatch_sensor_mode_command_for_nodes


def test_dispatch_sensor_mode_command_for_nodes_returns_empty_success_without_nodes():
    resolve_node = AsyncMock(return_value=None)
    publish_batch = AsyncMock()

    result = asyncio.run(
        dispatch_sensor_mode_command_for_nodes(
            zone_id=1,
            context={"task_id": "st-1"},
            decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
            activate=False,
            reason_code="stop_done",
            resolve_online_node_for_channel_fn=resolve_node,
            publish_batch_fn=publish_batch,
        )
    )

    assert result["success"] is True
    assert result["commands_total"] == 0
    publish_batch.assert_not_awaited()


def test_dispatch_sensor_mode_command_for_nodes_publishes_activate_with_stabilization_time():
    async def _resolve(*, zone_id: int, channel: str, node_types):
        assert zone_id == 3
        assert channel == "system"
        if node_types == ["ph"]:
            return {"node_uid": "nd-ph-1", "channel": "system"}
        if node_types == ["ec"]:
            return {"node_uid": "nd-ec-1", "channel": "system"}
        return None

    publish_batch = AsyncMock(return_value={"success": True, "commands_total": 2})
    result = asyncio.run(
        dispatch_sensor_mode_command_for_nodes(
            zone_id=3,
            context={"task_id": "st-3"},
            decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
            activate=True,
            reason_code="recovery_started",
            resolve_online_node_for_channel_fn=_resolve,
            publish_batch_fn=publish_batch,
        )
    )

    assert result["success"] is True
    publish_batch.assert_awaited_once()
    kwargs = publish_batch.await_args.kwargs
    assert kwargs["cmd"] == "activate_sensor_mode"
    assert kwargs["params"]["stabilization_time_sec"] == 60
