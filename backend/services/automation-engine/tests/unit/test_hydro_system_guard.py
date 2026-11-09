"""Fail-closed: капельный граф не строится для явного не-drip типа."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.hydro_system import canonicalize, refusal_code
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from tests.unit.test_ae3lite_cycle_start_planner import _snapshot, _task


def test_aliases_follow_adr_0001() -> None:
    assert canonicalize("drip_tape") == "drip"
    assert canonicalize("drip_emitter") == "drip"
    assert canonicalize("recirc") == "nft"
    assert canonicalize("substrate_trays") == "substrate_trays"
    assert canonicalize("aeroponics") == "aeroponics"
    assert refusal_code("drip") is None
    assert refusal_code(None) is None
    assert refusal_code("nft") == "hydro_system_not_implemented"
    assert refusal_code("dwc") == "hydro_system_not_implemented"
    assert refusal_code("ebb_flow") == "hydro_system_not_implemented"
    assert refusal_code("substrate_trays") == "hydro_system_needs_review"
    assert refusal_code("not-a-system") == "hydro_system_unknown"


def test_drip_cycle_start_still_builds_plan() -> None:
    now = datetime.now(timezone.utc)
    snapshot = replace(_snapshot(), targets={"irrigation": {"system_type": "drip_tape"}, "ph": {"target": 5.9}})

    plan = CycleStartPlanner().build(task=_task(now), snapshot=snapshot)

    assert plan is not None


def test_nft_hydraulic_cycle_start_refuses_before_drip_plan() -> None:
    now = datetime.now(timezone.utc)
    task = _task(now)
    task = replace(task, topology="two_tank_drip_substrate_trays")
    snapshot = replace(
        _snapshot(),
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
        },
        targets={"irrigation": {"system_type": "nft"}},
        configured_hydroponic_system_types=("nft",),
    )

    with pytest.raises(PlannerConfigurationError) as caught:
        CycleStartPlanner().build(task=task, snapshot=snapshot)

    assert caught.value.code == "hydro_system_not_implemented"
    assert "nft" in str(caught.value)
