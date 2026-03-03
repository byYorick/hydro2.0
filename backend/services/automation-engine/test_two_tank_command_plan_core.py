from __future__ import annotations

import pytest

from domain.models.decision_models import DecisionOutcome
from executor.two_tank_command_plan_core import dispatch_two_tank_command_plan_core
from executor.two_tank_common import resolve_primary_pump_channel


@pytest.mark.asyncio
async def test_dispatch_two_tank_command_plan_passes_dedupe_bypass_to_publish_batch():
    captured = {"dedupe_bypass": None}

    async def fake_resolve_online_node_for_channel(*, zone_id, channel, node_types):
        _ = node_types
        return {"zone_id": zone_id, "node_uid": "nd-irrig-1", "channel": channel}

    async def fake_publish_batch(**kwargs):
        captured["dedupe_bypass"] = kwargs.get("dedupe_bypass")
        return {
            "success": True,
            "commands_total": 1,
            "commands_failed": 0,
            "commands_submitted": 1,
            "commands_effect_confirmed": 1,
            "command_statuses": [],
        }

    result = await dispatch_two_tank_command_plan_core(
        zone_id=2,
        command_plan=[
            {
                "channel": "pump_main",
                "cmd": "set_relay",
                "params": {"state": True},
                "node_types": ["irrig"],
                "allow_no_effect": False,
                "dedupe_bypass": True,
            }
        ],
        context={"task_id": "st-tt-1"},
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code="solution_fill_started",
            reason="start",
        ),
        resolve_online_node_for_channel_fn=fake_resolve_online_node_for_channel,
        publish_batch_fn=fake_publish_batch,
        err_two_tank_channel_not_found="two_tank_channel_not_found",
        err_two_tank_command_failed="two_tank_command_failed",
    )

    assert result["success"] is True
    assert captured["dedupe_bypass"] is True


def test_resolve_primary_pump_channel_uses_first_pump_channel():
    channel = resolve_primary_pump_channel(
        [
            {"channel": "valve_solution_fill"},
            {"channel": "pump_aux"},
            {"channel": "pump_main"},
        ]
    )

    assert channel == "pump_aux"


def test_resolve_primary_pump_channel_falls_back_to_main():
    channel = resolve_primary_pump_channel(
        [
            {"channel": "valve_solution_fill"},
            {"channel": "valve_solution_supply"},
        ]
    )

    assert channel == "pump_main"
