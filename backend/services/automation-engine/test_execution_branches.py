from __future__ import annotations

import pytest

from domain.models.decision_models import DecisionOutcome
from executor.execution_branches import execute_action_required_branch


@pytest.mark.asyncio
async def test_irrigation_branch_skips_pre_dispatch_phase_update_without_phase_hint():
    phase_updates: list[dict] = []

    async def _execute_diagnostics(**_kwargs):
        raise AssertionError("diagnostics branch must not be called")

    async def _update_phase(**kwargs):
        phase_updates.append(dict(kwargs))
        return "irrigating"

    async def _execute_device_task(**_kwargs):
        return {"success": True, "task_type": "irrigation", "decision": "run", "action_required": True}

    async def _try_recovery(**_kwargs):
        return None

    result = await execute_action_required_branch(
        zone_id=2,
        task_type="irrigation",
        payload={"config": {"execution": {}}},
        context={"task_id": "st-10"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="irrigation_required", reason="run"),
        workflow_phase_irrigating="irrigating",
        execute_diagnostics_fn=_execute_diagnostics,
        update_zone_workflow_phase_fn=_update_phase,
        execute_device_task_fn=_execute_device_task,
        try_start_recovery_fn=_try_recovery,
    )

    assert result["success"] is True
    assert phase_updates == []


@pytest.mark.asyncio
async def test_irrigation_branch_updates_phase_with_ready_hint():
    phase_updates: list[dict] = []

    async def _execute_diagnostics(**_kwargs):
        raise AssertionError("diagnostics branch must not be called")

    async def _update_phase(**kwargs):
        phase_updates.append(dict(kwargs))
        return "irrigating"

    async def _execute_device_task(**_kwargs):
        return {"success": True, "task_type": "irrigation", "decision": "run", "action_required": True}

    async def _try_recovery(**_kwargs):
        return None

    await execute_action_required_branch(
        zone_id=2,
        task_type="irrigation",
        payload={"workflow_phase": "ready"},
        context={"task_id": "st-11"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="irrigation_required", reason="run"),
        workflow_phase_irrigating="irrigating",
        execute_diagnostics_fn=_execute_diagnostics,
        update_zone_workflow_phase_fn=_update_phase,
        execute_device_task_fn=_execute_device_task,
        try_start_recovery_fn=_try_recovery,
    )

    assert len(phase_updates) == 1
    assert phase_updates[0]["workflow_phase"] == "irrigating"
