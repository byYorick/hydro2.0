"""CycleStartPlanner solution: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.application.dto import CommandPlan, ZoneSnapshot
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class CyclePlanningSolutionPorts:
    build_two_tank_plan: Callable[..., Any]


class CyclePlanningSolution:
    def __init__(self, ports: CyclePlanningSolutionPorts) -> None:
        self._ports = ports

    def build_solution_topup_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        """Two-tank command plans для автодолива в ready (reuse solution_fill hydraulics)."""
        if str(snapshot.automation_runtime or "").strip().lower() != "ae3":
            raise PlannerConfigurationError("Для solution_topup требуется zone.automation_runtime='ae3'")
        topology = str(task.topology or "two_tank").strip().lower()
        topup_pack = TopologyRegistry().try_pack(topology)
        if (
            topup_pack is None
            or topup_pack.plan_profile not in {"two_tank", "single_tank"}
            or "solution_topup_guard" not in topup_pack.stages
        ):
            raise PlannerConfigurationError(f"solution_topup не поддерживает topology={topology}")
        plan = self._ports.build_two_tank_plan(
            task=task,
            snapshot=snapshot,
            workflow="solution_topup",
            topology=topology,
        )
        named_plans = dict(plan.named_plans)
        fill_start = named_plans.get("solution_fill_start")
        fill_stop = named_plans.get("solution_fill_stop")
        if fill_start:
            named_plans["solution_topup_start"] = fill_start
        if fill_stop:
            named_plans["solution_topup_stop"] = fill_stop
        irr_probe = named_plans.get("irr_state_probe")
        if irr_probe:
            named_plans["irr_state_probe"] = irr_probe
        return CommandPlan(
            task_type=task.task_type,
            workflow="solution_topup",
            topology=topology,
            steps=plan.steps,
            targets=plan.targets,
            named_plans=named_plans,
            runtime=plan.runtime,
        )

    def build_solution_change_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        """Two-tank command plans для semi-auto подмены раствора."""
        if str(snapshot.automation_runtime or "").strip().lower() != "ae3":
            raise PlannerConfigurationError("Для solution_change требуется zone.automation_runtime='ae3'")
        topology = str(task.topology or "two_tank").strip().lower()
        change_pack = TopologyRegistry().try_pack(topology)
        if (
            change_pack is None
            or change_pack.plan_profile not in {"two_tank", "single_tank"}
            or "await_operator_drain_confirm" not in change_pack.stages
        ):
            raise PlannerConfigurationError(f"solution_change не поддерживает topology={topology}")
        plan = self._ports.build_two_tank_plan(
            task=task,
            snapshot=snapshot,
            workflow="solution_change",
            topology=topology,
        )
        named_plans = dict(plan.named_plans)
        drain_start = named_plans.get("solution_drain_start")
        drain_stop = named_plans.get("solution_drain_stop")
        if drain_start:
            named_plans["solution_drain_start"] = drain_start
        if drain_stop:
            named_plans["solution_drain_stop"] = drain_stop
        irr_probe = named_plans.get("irr_state_probe")
        if irr_probe:
            named_plans["irr_state_probe"] = irr_probe
        return CommandPlan(
            task_type=task.task_type,
            workflow="solution_change",
            topology=topology,
            steps=plan.steps,
            targets=plan.targets,
            named_plans=named_plans,
            runtime=plan.runtime,
        )
