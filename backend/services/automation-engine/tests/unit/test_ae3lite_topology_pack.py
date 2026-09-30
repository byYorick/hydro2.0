"""Каркас TopologyPack: два дескриптора two-tank, свет и single_tank."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.application.services.topology_pack import subsystem_enabled_flags
from ae3lite.application.services.workflow_topology import (
    DRIP_SUBSTRATE_TRAYS_PACK,
    LIGHTING_TICK_PACK,
    SINGLE_TANK,
    SINGLE_TANK_PACK,
    TWO_TANK,
    TWO_TANK_PACK,
    TopologyRegistry,
)
from ae3lite.config.schema.runtime_plan import (
    CorrectionRuntimeSlice,
    IrrigationRuntimeSlice,
    LightingRuntimeSlice,
    RuntimePlan,
    SolutionRuntimeSlice,
)
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.services.zone_node_availability import TWO_TANK_TOPOLOGIES
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from ae3lite.hydraulics.registry import handler_dependency_map, system_by_id

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_two_tank_and_drip_are_distinct_packs_with_shared_graph() -> None:
    assert TWO_TANK_PACK.id != DRIP_SUBSTRATE_TRAYS_PACK.id
    assert TWO_TANK_PACK.stages is DRIP_SUBSTRATE_TRAYS_PACK.stages
    assert TWO_TANK_PACK.irrigation_binding == "generic"
    assert DRIP_SUBSTRATE_TRAYS_PACK.irrigation_binding == "drip_substrate_trays"
    assert TWO_TANK_PACK.required_node_types == frozenset({"irrig", "ph", "ec"})
    assert TWO_TANK_TOPOLOGIES == frozenset({"two_tank", "two_tank_drip_substrate_trays"})
    assert TWO_TANK_PACK.entry_by_task_type["cycle_start"] == "startup"
    assert TWO_TANK_PACK.entry_by_task_type["irrigation_start"] == "await_ready"


def test_registry_validate_known_packs() -> None:
    registry = TopologyRegistry()
    for pack_id in (
        "two_tank",
        "two_tank_drip_substrate_trays",
        "single_tank",
        "lighting_tick",
        "generic_cycle_start",
    ):
        assert registry.validate(pack_id) == [], pack_id


def test_single_tank_drops_clean_fill_and_keeps_solution_path() -> None:
    assert "clean_fill_start" not in SINGLE_TANK
    assert "clean_fill_check" not in SINGLE_TANK
    assert "solution_fill_start" in SINGLE_TANK
    assert "startup" in SINGLE_TANK
    assert len(SINGLE_TANK) < len(TWO_TANK)
    drain_stop = SINGLE_TANK["solution_drain_stop_to_clean_fill"]
    assert drain_stop.next_stage == "solution_fill_start"
    assert "clean_fill_start" not in SINGLE_TANK_PACK.command_plan_keys
    assert "solution_fill_start" in SINGLE_TANK_PACK.command_plan_keys
    assert SINGLE_TANK_PACK.plan_profile == "single_tank"
    assert SINGLE_TANK_PACK.execution_mode == "workflow"


def test_lighting_tick_is_a_registered_tick_pack() -> None:
    registry = TopologyRegistry()
    pack = registry.pack("lighting_tick")
    assert pack is LIGHTING_TICK_PACK
    assert pack.plan_profile == "lighting"
    assert pack.execution_mode == "command_batch"
    assert pack.entry_by_task_type["lighting_tick"] == "apply"
    assert registry.get("lighting_tick", "apply").command_plans == ("lighting_tick",)
    assert "lighting" in pack.required_subsystems
    lighting = system_by_id()["lighting"]
    assert lighting.kind == "tick"
    assert lighting.scope == "zone"
    climate = system_by_id()["climate"]
    assert climate.scope == "greenhouse"
    assert climate.kind == "tick"


def test_handler_dependencies_come_from_subsystems() -> None:
    deps = handler_dependency_map()
    assert deps["decision_gate"] == ("task_repository", "decision_controller")
    assert deps["prepare_recirc"] == ("task_repository", "pid_state_repository")
    assert deps["prepare_recirc_window"] == ("alert_repository",)
    assert deps["correction"] == ("planner", "pid_state_repository")
    assert "startup" not in deps


def test_runtime_plan_is_composed_from_subsystem_slices() -> None:
    assert issubclass(RuntimePlan, SolutionRuntimeSlice)
    assert issubclass(RuntimePlan, IrrigationRuntimeSlice)
    assert issubclass(RuntimePlan, CorrectionRuntimeSlice)
    assert issubclass(RuntimePlan, LightingRuntimeSlice)
    assert "clean_fill_timeout_sec" in SolutionRuntimeSlice.model_fields
    assert "irrigation_execution" in IrrigationRuntimeSlice.model_fields
    assert "target_ph" in CorrectionRuntimeSlice.model_fields
    assert "day_night_enabled" in LightingRuntimeSlice.model_fields
    assert "command_specs" in RuntimePlan.model_fields


def test_required_subsystem_disabled_is_fail_closed() -> None:
    snapshot = SimpleNamespace(
        targets={
            "extensions": {
                "subsystems": {
                    "solution": {"enabled": False},
                }
            }
        }
    )
    assert subsystem_enabled_flags(snapshot)["solution"] is False
    planner = CycleStartPlanner()
    with pytest.raises(PlannerConfigurationError, match="solution"):
        planner._assert_required_subsystems_enabled(pack=TWO_TANK_PACK, snapshot=snapshot)


def test_lighting_planner_requires_registered_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    planner = CycleStartPlanner()

    def _missing(_topology: str):
        raise KeyError("Неизвестная topology: 'lighting_tick'")

    monkeypatch.setattr(TopologyRegistry, "pack", lambda self, topology: _missing(topology))
    task = SimpleNamespace(task_type="lighting_tick", zone_id=1, topology="lighting_tick")
    snapshot = SimpleNamespace(zone_id=1, automation_runtime="ae3", actuators=(), targets={})
    with pytest.raises(KeyError, match="lighting_tick"):
        planner.build(task=task, snapshot=snapshot)


class _Monitor:
    def __init__(self) -> None:
        self.level_calls = 0

    async def read_latest_irr_state(self, **_kw: object) -> dict:
        return {"has_snapshot": True, "is_stale": False, "snapshot": {"pump_main": False}}

    async def read_level_switch(self, **_kw: object) -> dict:
        self.level_calls += 1
        return {"has_level": True, "is_stale": False, "is_triggered": False}


class _Gateway:
    async def run_batch(self, **_kw: object) -> dict:
        return {"success": True, "error_code": None, "error_message": None}


class _Plan:
    def __init__(self) -> None:
        self.runtime = SimpleNamespace()
        self.named_plans = {"irr_state_probe": ("probe",)}


def _task(topology: str) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 9,
        "zone_id": 4,
        "task_type": "cycle_start",
        "status": "running",
        "idempotency_key": "k",
        "scheduled_for": NOW,
        "due_at": NOW,
        "claimed_by": "w",
        "claimed_at": NOW,
        "error_code": None,
        "error_message": None,
        "created_at": NOW,
        "updated_at": NOW,
        "completed_at": None,
        "topology": topology,
        "intent_source": None,
        "intent_trigger": None,
        "intent_id": None,
        "intent_meta": {},
        "current_stage": "startup",
        "workflow_phase": "idle",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": NOW,
        "clean_fill_cycle": 0,
        "control_mode_snapshot": "auto",
        "pending_manual_step": None,
        "corr_step": None,
    })


@pytest.mark.asyncio
async def test_single_tank_startup_skips_clean_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = _Monitor()
    handler = StartupHandler(runtime_monitor=monitor, command_gateway=_Gateway())

    async def _probe(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(handler, "_probe_irr_state", _probe)
    monkeypatch.setattr(handler, "_clear_manual_to_auto_reconcile_flag", _probe)
    monkeypatch.setattr(handler, "_require_runtime_plan", lambda **_kw: SimpleNamespace())

    outcome = await handler.run(task=_task("single_tank"), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_start"
    assert monitor.level_calls == 0
