from __future__ import annotations

import pytest

from domain.models.decision_models import DecisionOutcome
from domain.workflows.two_tank_core import execute_two_tank_startup_workflow_core
from domain.workflows.two_tank_deps import TwoTankDeps


class _CoreTargetsStub:
    def __init__(self) -> None:
        self.runtime_payload = {}
        self.fetch_calls = 0

    async def _fetch_profile(self, _query: str, _zone_id: int):
        self.fetch_calls += 1
        return [
            {
                "subsystems": {
                    "diagnostics": {
                        "execution": {
                            "target_ph": 5.75,
                            "target_ec": 1.05,
                            "target_ec_prepare_npk": 0.55,
                            "prepare_tolerance": {
                                "ph_pct": 25.0,
                                "ec_pct": 30.0,
                            },
                        }
                    }
                }
            }
        ]

    def _resolve_runtime_cfg(self, payload):
        self.runtime_payload = dict(payload)
        return {}

    def _normalize_workflow(self, _payload):
        return "unsupported_workflow"


def _decision() -> DecisionOutcome:
    return DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="diagnostics_required",
        reason="Требуется выполнить задачу по расписанию",
    )


@pytest.mark.asyncio
async def test_two_tank_core_injects_targets_from_active_profile_when_payload_is_wakeup_only():
    stub = _CoreTargetsStub()
    deps = TwoTankDeps(
        zone_id=2,
        fetch_fn=stub._fetch_profile,
        resolve_two_tank_runtime_config=stub._resolve_runtime_cfg,
        normalize_two_tank_workflow=stub._normalize_workflow,
    )

    result = await execute_two_tank_startup_workflow_core(
        deps,
        payload={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "config": {"execution": {"workflow": "cycle_start", "topology": "two_tank_drip_substrate_trays"}},
        },
        context={"task_id": "tt-core-targets-1"},
        decision=_decision(),
    )

    assert result["success"] is False
    assert result["reason_code"] == "unsupported_workflow"
    assert stub.fetch_calls == 1
    runtime_execution = stub.runtime_payload["config"]["execution"]
    assert runtime_execution["target_ph"] == 5.75
    assert runtime_execution["target_ec"] == 1.05
    assert runtime_execution["target_ec_prepare_npk"] == 0.55
    assert runtime_execution["prepare_tolerance"] == {"ph_pct": 25.0, "ec_pct": 30.0}


@pytest.mark.asyncio
async def test_two_tank_core_does_not_override_targets_from_payload():
    stub = _CoreTargetsStub()

    async def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("fetch_fn must not be called when payload already contains targets")

    deps = TwoTankDeps(
        zone_id=2,
        fetch_fn=_unexpected_fetch,
        resolve_two_tank_runtime_config=stub._resolve_runtime_cfg,
        normalize_two_tank_workflow=stub._normalize_workflow,
    )

    result = await execute_two_tank_startup_workflow_core(
        deps,
        payload={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "config": {
                "execution": {
                    "workflow": "cycle_start",
                    "topology": "two_tank_drip_substrate_trays",
                    "target_ph": 6.1,
                    "target_ec": 1.8,
                    "target_ec_prepare_npk": 1.2,
                    "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
                }
            },
        },
        context={"task_id": "tt-core-targets-2"},
        decision=_decision(),
    )

    assert result["success"] is False
    assert result["reason_code"] == "unsupported_workflow"
    runtime_execution = stub.runtime_payload["config"]["execution"]
    assert runtime_execution["target_ph"] == 6.1
    assert runtime_execution["target_ec"] == 1.8
