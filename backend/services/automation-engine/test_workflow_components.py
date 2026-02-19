"""Unit tests for extracted workflow/dispatch components."""

from unittest.mock import AsyncMock

import pytest

from application.command_dispatch import CommandDispatch
from application.workflow_router import WorkflowRouter
from application.workflow_state_sync import WorkflowStateSync
from application.workflow_validator import WorkflowValidator


@pytest.mark.parametrize(
    ("contract_version", "supported", "expected_valid", "expected_reason_code"),
    [
        ("v2", True, True, None),
        ("v3", False, False, "invalid_payload_contract_version"),
    ],
)
def test_workflow_validator_contract_gate(contract_version, supported, expected_valid, expected_reason_code):
    validator = WorkflowValidator(
        extract_workflow=lambda payload: str(payload.get("workflow") or ""),
        extract_topology=lambda payload: str(payload.get("topology") or ""),
        extract_payload_contract_version=lambda payload: contract_version,
        is_supported_payload_contract_version=lambda value: supported,
        requires_explicit_workflow=lambda payload: True,
        build_invalid_payload_result=lambda **kwargs: kwargs,
        explicit_workflow_feature_enabled=lambda: True,
    )

    result = validator.validate_diagnostics(
        zone_id=1,
        payload={"workflow": "startup", "topology": "two_tank"},
        task_type="diagnostics",
        task_id="task-1",
        correlation_id="corr-1",
    )

    assert result.valid is expected_valid
    if expected_reason_code is not None:
        assert result.error_result["reason_code"] == expected_reason_code


def test_workflow_validator_requires_explicit_workflow():
    validator = WorkflowValidator(
        extract_workflow=lambda payload: "",
        extract_topology=lambda payload: "two_tank",
        extract_payload_contract_version=lambda payload: "v2",
        is_supported_payload_contract_version=lambda value: True,
        requires_explicit_workflow=lambda payload: True,
        build_invalid_payload_result=lambda **kwargs: kwargs,
        explicit_workflow_feature_enabled=lambda: True,
    )

    result = validator.validate_diagnostics(
        zone_id=2,
        payload={"topology": "two_tank"},
        task_type="diagnostics",
        task_id="task-2",
        correlation_id="corr-2",
    )

    assert result.valid is False
    assert result.error_result["reason_code"] == "invalid_payload_missing_workflow"


def test_workflow_validator_requires_topology():
    validator = WorkflowValidator(
        extract_workflow=lambda payload: "startup",
        extract_topology=lambda payload: "",
        extract_payload_contract_version=lambda payload: "v2",
        is_supported_payload_contract_version=lambda value: True,
        requires_explicit_workflow=lambda payload: True,
        build_invalid_payload_result=lambda **kwargs: kwargs,
        explicit_workflow_feature_enabled=lambda: True,
    )

    result = validator.validate_diagnostics(
        zone_id=3,
        payload={"workflow": "startup"},
        task_type="diagnostics",
        task_id="task-2-topology",
        correlation_id="corr-2-topology",
    )

    assert result.valid is False
    assert result.error_result["reason_code"] == "invalid_payload_missing_topology"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("topology", "workflow", "expected_route"),
    [
        ("two_tank", "startup", "two_tank"),
        ("three_tank", "startup", "three_tank"),
        ("", "cycle_start", "cycle_start"),
        ("", "unknown", "invalid"),
    ],
)
async def test_workflow_router_selects_route(topology, workflow, expected_route):
    calls = []

    async def _handler(name, **kwargs):
        calls.append(name)
        return {"success": True, "mode": name, "commands_total": 0, "commands_failed": 0}

    router = WorkflowRouter(
        two_tank_topologies={"two_tank"},
        three_tank_topologies={"three_tank"},
        cycle_start_workflows={"cycle_start", "refill_check"},
        execute_two_tank=lambda **kwargs: _handler("two_tank", **kwargs),
        execute_three_tank=lambda **kwargs: _handler("three_tank", **kwargs),
        execute_cycle_start=lambda **kwargs: _handler("cycle_start", **kwargs),
        execute_default=lambda *args, **kwargs: _handler("default", **kwargs),
    )

    result = await router.route_diagnostics(
        zone_id=1,
        payload={"topology": topology, "workflow": workflow},
        context={"task_id": "task-3", "correlation_id": "corr-3"},
        decision=type("Decision", (), {"decision": "run"})(),
        workflow=workflow,
        topology=topology,
        task_type="diagnostics",
    )

    if expected_route == "invalid":
        assert calls == []
        assert result["success"] is False
        assert result["error_code"] == "invalid_payload_routing"
        assert result["mode"] == "diagnostics_invalid_payload"
    else:
        assert calls == [expected_route]
        assert result["mode"] == expected_route


@pytest.mark.asyncio
async def test_command_dispatch_execute_device_task_calls_impl():
    execute_impl = AsyncMock(return_value={"success": True, "commands_total": 1, "commands_failed": 0, "decision": "run", "reason_code": "ok"})
    dispatch_impl = AsyncMock(return_value={"success": True, "commands_total": 0, "commands_failed": 0})
    component = CommandDispatch(
        execute_device_task_impl=execute_impl,
        dispatch_command_plan_impl=dispatch_impl,
    )

    result = await component.execute_device_task(
        zone_id=1,
        payload={},
        mapping=type("Mapping", (), {"task_type": "irrigation"})(),
        context={"task_id": "task-4", "correlation_id": "corr-4"},
        decision=type("Decision", (), {"decision": "run", "reason_code": "ok"})(),
        task_type="irrigation",
    )

    assert result["success"] is True
    execute_impl.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_state_sync_calls_impl():
    sync_impl = AsyncMock(return_value=None)
    component = WorkflowStateSync(sync_impl=sync_impl)

    await component.sync(
        zone_id=7,
        task_type="diagnostics",
        payload={"workflow": "startup"},
        result={"success": True, "decision": "run", "reason_code": "ok", "commands_total": 0},
        context={"task_id": "task-5", "correlation_id": "corr-5"},
    )

    sync_impl.assert_awaited_once()
