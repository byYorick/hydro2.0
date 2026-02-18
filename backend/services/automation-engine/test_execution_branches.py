"""Unit tests for application.execution_branches helpers."""

from unittest.mock import AsyncMock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.execution_branches import execute_action_required_branch


@pytest.mark.asyncio
async def test_execute_action_required_branch_routes_diagnostics():
    diagnostics_fn = AsyncMock(return_value={"success": True, "mode": "diag"})
    result = await execute_action_required_branch(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        workflow_phase_irrigating="irrigating",
        execute_diagnostics_fn=diagnostics_fn,
        update_zone_workflow_phase_fn=AsyncMock(),
        execute_device_task_fn=AsyncMock(),
        try_start_recovery_fn=AsyncMock(),
    )
    assert result["mode"] == "diag"
    diagnostics_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_action_required_branch_runs_irrigation_recovery_override():
    update_phase = AsyncMock(return_value="irrigating")
    execute_device = AsyncMock(return_value={"success": False, "mode": "irrigation_failed"})
    try_recovery = AsyncMock(return_value={"success": True, "mode": "recovery_started"})
    result = await execute_action_required_branch(
        zone_id=2,
        task_type="irrigation",
        payload={},
        context={},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="x", reason="x"),
        workflow_phase_irrigating="irrigating",
        execute_diagnostics_fn=AsyncMock(),
        update_zone_workflow_phase_fn=update_phase,
        execute_device_task_fn=execute_device,
        try_start_recovery_fn=try_recovery,
    )
    assert result["mode"] == "recovery_started"
    update_phase.assert_awaited_once()
    execute_device.assert_awaited_once()
    try_recovery.assert_awaited_once()
