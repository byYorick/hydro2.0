"""Unit tests for application.diagnostics_task_execution helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from domain.models.decision_models import DecisionOutcome
from application.diagnostics_task_execution import execute_diagnostics_task


def _decision() -> DecisionOutcome:
    return DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")


def test_execute_diagnostics_task_returns_invalid_payload_result():
    validator = SimpleNamespace(
        validate_diagnostics=lambda **_: SimpleNamespace(
            valid=False,
            error_result=None,
            payload_contract_version="0.9",
        )
    )
    result = asyncio.run(
        execute_diagnostics_task(
            zone_id=1,
            payload={},
            context={},
            decision=_decision(),
            workflow_validator=validator,
            dispatch_diagnostics_workflow_fn=AsyncMock(),
            execute_diagnostics_fn=AsyncMock(),
            build_invalid_payload_result_fn=lambda **_: {"success": False, "error_code": "invalid_payload"},
            cycle_start_workflows={"cycle_start", "refill_check"},
            err_invalid_payload_contract_version="invalid_payload_contract_version",
        )
    )
    assert result["success"] is False


def test_execute_diagnostics_task_routes_to_workflow_when_cycle_start_without_explicit():
    validator = SimpleNamespace(
        validate_diagnostics=lambda **_: SimpleNamespace(
            valid=True,
            error_result=None,
            payload_contract_version="1.0",
            workflow="cycle_start",
            topology="two_tank",
            requires_explicit_workflow=False,
        )
    )
    route = AsyncMock(return_value={"success": True, "mode": "routed"})
    result = asyncio.run(
        execute_diagnostics_task(
            zone_id=1,
            payload={},
            context={},
            decision=_decision(),
            workflow_validator=validator,
            dispatch_diagnostics_workflow_fn=route,
            execute_diagnostics_fn=AsyncMock(return_value={"success": True, "mode": "direct"}),
            build_invalid_payload_result_fn=lambda **_: {"success": False},
            cycle_start_workflows={"cycle_start", "refill_check"},
            err_invalid_payload_contract_version="invalid_payload_contract_version",
        )
    )
    assert result["mode"] == "routed"
    route.assert_awaited_once()


def test_execute_diagnostics_task_routes_to_direct_when_no_explicit_workflow():
    validator = SimpleNamespace(
        validate_diagnostics=lambda **_: SimpleNamespace(
            valid=True,
            error_result=None,
            payload_contract_version="1.0",
            workflow="diagnostics",
            topology="two_tank",
            requires_explicit_workflow=False,
        )
    )
    direct = AsyncMock(return_value={"success": True, "mode": "direct"})
    result = asyncio.run(
        execute_diagnostics_task(
            zone_id=1,
            payload={},
            context={},
            decision=_decision(),
            workflow_validator=validator,
            dispatch_diagnostics_workflow_fn=AsyncMock(return_value={"success": True, "mode": "routed"}),
            execute_diagnostics_fn=direct,
            build_invalid_payload_result_fn=lambda **_: {"success": False},
            cycle_start_workflows={"cycle_start", "refill_check"},
            err_invalid_payload_contract_version="invalid_payload_contract_version",
        )
    )
    assert result["mode"] == "direct"
    direct.assert_awaited_once()


def test_execute_diagnostics_task_triggers_post_correction_cycle_for_active_phase():
    validator = SimpleNamespace(
        validate_diagnostics=lambda **_: SimpleNamespace(
            valid=True,
            error_result=None,
            payload_contract_version="1.0",
            workflow="manual_step",
            topology="two_tank",
            requires_explicit_workflow=True,
        )
    )
    route = AsyncMock(return_value={"success": True, "mode": "routed", "workflow_phase": "tank_filling"})
    post_cycle = AsyncMock(return_value={"success": True, "mode": "zone_service"})

    result = asyncio.run(
        execute_diagnostics_task(
            zone_id=2,
            payload={},
            context={},
            decision=_decision(),
            workflow_validator=validator,
            dispatch_diagnostics_workflow_fn=route,
            execute_diagnostics_fn=AsyncMock(return_value={"success": True, "mode": "direct"}),
            build_invalid_payload_result_fn=lambda **_: {"success": False},
            cycle_start_workflows={"cycle_start", "refill_check"},
            err_invalid_payload_contract_version="invalid_payload_contract_version",
            post_workflow_diagnostics_fn=post_cycle,
            post_workflow_phases={"tank_filling", "tank_recirc"},
        )
    )

    assert result["mode"] == "routed"
    assert result["post_correction_cycle_triggered"] is True
    assert result["post_correction_cycle_success"] is True
    assert result["post_correction_cycle_mode"] == "zone_service"
    post_cycle.assert_awaited_once()


def test_execute_diagnostics_task_skips_post_correction_cycle_for_inactive_phase():
    validator = SimpleNamespace(
        validate_diagnostics=lambda **_: SimpleNamespace(
            valid=True,
            error_result=None,
            payload_contract_version="1.0",
            workflow="manual_step",
            topology="two_tank",
            requires_explicit_workflow=True,
        )
    )
    route = AsyncMock(return_value={"success": True, "mode": "routed", "workflow_phase": "idle"})
    post_cycle = AsyncMock(return_value={"success": True, "mode": "zone_service"})

    result = asyncio.run(
        execute_diagnostics_task(
            zone_id=2,
            payload={},
            context={},
            decision=_decision(),
            workflow_validator=validator,
            dispatch_diagnostics_workflow_fn=route,
            execute_diagnostics_fn=AsyncMock(return_value={"success": True, "mode": "direct"}),
            build_invalid_payload_result_fn=lambda **_: {"success": False},
            cycle_start_workflows={"cycle_start", "refill_check"},
            err_invalid_payload_contract_version="invalid_payload_contract_version",
            post_workflow_diagnostics_fn=post_cycle,
            post_workflow_phases={"tank_filling", "tank_recirc"},
        )
    )

    assert result["mode"] == "routed"
    assert "post_correction_cycle_triggered" not in result
    post_cycle.assert_not_awaited()
