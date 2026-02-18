"""Unit tests for application.two_tank_command_plan_core helpers."""

from unittest.mock import AsyncMock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.two_tank_command_plan_core import dispatch_two_tank_command_plan_core


@pytest.mark.asyncio
async def test_dispatch_two_tank_command_plan_core_handles_missing_channel():
    result = await dispatch_two_tank_command_plan_core(
        zone_id=1,
        command_plan=[{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        resolve_online_node_for_channel_fn=AsyncMock(return_value=None),
        publish_batch_fn=AsyncMock(),
        err_two_tank_channel_not_found="two_tank_channel_not_found",
        err_two_tank_command_failed="two_tank_command_failed",
    )
    assert result["success"] is False
    assert result["error_code"] == "two_tank_channel_not_found"


@pytest.mark.asyncio
async def test_dispatch_two_tank_command_plan_core_aggregates_publish_results():
    resolve_node = AsyncMock(return_value={"node_uid": "nd-1", "channel": "pump_main"})
    publish_batch = AsyncMock(
        return_value={
            "success": True,
            "commands_total": 1,
            "commands_failed": 0,
            "commands_submitted": 1,
            "commands_effect_confirmed": 1,
            "command_statuses": [{"terminal_status": "DONE"}],
        }
    )
    result = await dispatch_two_tank_command_plan_core(
        zone_id=1,
        command_plan=[{"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}}],
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        resolve_online_node_for_channel_fn=resolve_node,
        publish_batch_fn=publish_batch,
        err_two_tank_channel_not_found="two_tank_channel_not_found",
        err_two_tank_command_failed="two_tank_command_failed",
    )
    assert result["success"] is True
    assert result["commands_total"] == 1
    publish_batch.assert_awaited_once()
