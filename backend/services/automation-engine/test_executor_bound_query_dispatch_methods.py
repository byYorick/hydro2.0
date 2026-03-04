from __future__ import annotations

import pytest

from domain.models.decision_models import DecisionOutcome
from executor import executor_bound_query_dispatch_methods as bound_methods


@pytest.mark.asyncio
async def test_bound_dispatch_sensor_mode_passes_stabilization_time_sec(monkeypatch):
    captured = {}

    async def fake_policy_dispatch_sensor_mode_command_for_nodes(**kwargs):
        captured.update(kwargs)
        return {"success": True, "commands_total": 0, "commands_failed": 0, "command_statuses": []}

    monkeypatch.setattr(
        bound_methods,
        "policy_dispatch_sensor_mode_command_for_nodes",
        fake_policy_dispatch_sensor_mode_command_for_nodes,
    )

    class _Executor:
        async def _resolve_online_node_for_channel(self, **_kwargs):
            return None

        async def _publish_batch(self, **_kwargs):
            return {"success": True}

    executor = _Executor()
    result = await bound_methods.bound_dispatch_sensor_mode_command_for_nodes(
        executor,
        zone_id=6,
        context={"task_id": "st-1"},
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code="solution_fill_started",
            reason="test",
        ),
        activate=True,
        reason_code="solution_fill_started",
        stabilization_time_sec=75,
    )

    assert result["success"] is True
    assert captured["stabilization_time_sec"] == 75
    assert captured["resolve_online_node_for_channel_fn"] == executor._resolve_online_node_for_channel
    assert captured["publish_batch_fn"] == executor._publish_batch
