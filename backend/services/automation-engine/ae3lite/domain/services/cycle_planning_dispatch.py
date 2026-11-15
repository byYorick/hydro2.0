"""CycleStartPlanner dispatch: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneSnapshot
from ae3lite.application.services.topology_pack import subsystem_enabled_flags
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class CyclePlanningDispatchPorts:
    supported_schema_version: Callable[[], Any]
    build_lighting_tick_plan: Callable[..., Any]
    build_solution_change_plan: Callable[..., Any]
    build_solution_topup_plan: Callable[..., Any]
    build_two_tank_plan: Callable[..., Any]
    normalize_node_types: Callable[..., Any]
    resolve_actuator: Callable[..., Any]
    resolve_single_node_uid: Callable[..., Any]


class CyclePlanningDispatch:
    def __init__(self, ports: CyclePlanningDispatchPorts) -> None:
        self._ports = ports

    def build(self, *, task: AutomationTask, snapshot: ZoneSnapshot) -> CommandPlan:
        """Build a deterministic command plan for the task+snapshot pair.

        Contract (audit F12):
          * Pure function — no mutation of ``task`` or ``snapshot``
          * Deterministic for identical inputs — two calls with the same
            ``task`` and ``snapshot`` produce structurally-equal results
          * Not cached — ``execute_task`` calls build() at most once per
            task run, and ``snapshot`` may change between runs, so a cache
            would be both unnecessary and incorrect. Memoize only in tests
            if the same inputs are reused.
          * Fail-closed — raises ``PlannerConfigurationError`` instead of
            silently degrading on missing/invalid config
        """
        if str(getattr(task, "task_type", "") or "").strip().lower() == "lighting_tick":
            lighting_pack = TopologyRegistry().pack("lighting_tick")
            if lighting_pack.plan_profile != "lighting":
                raise PlannerConfigurationError("Пакет lighting_tick обязан быть tick-профилем света")
            if lighting_pack.entry_by_task_type.get("lighting_tick") != "apply":
                raise PlannerConfigurationError("Пакет lighting_tick должен входить в стадию apply")
            return self._ports.build_lighting_tick_plan(task=task, snapshot=snapshot)
        if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_topup":
            return self._ports.build_solution_topup_plan(task=task, snapshot=snapshot)
        if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
            return self._ports.build_solution_change_plan(task=task, snapshot=snapshot)
        if task.task_type not in {"cycle_start", "irrigation_start"}:
            raise PlannerConfigurationError(f"CycleStartPlanner не поддерживает task_type={task.task_type}")
        if task.zone_id != snapshot.zone_id:
            raise PlannerConfigurationError(
                f"AutomationTask.zone_id={task.zone_id} не совпадает с ZoneSnapshot.zone_id={snapshot.zone_id}"
            )
        if str(snapshot.automation_runtime or "").strip().lower() != "ae3":
            raise PlannerConfigurationError("CycleStartPlanner требует zone.automation_runtime='ae3'")
        if snapshot.grow_cycle_id is None or snapshot.current_phase_id is None:
            raise PlannerConfigurationError("CycleStartPlanner требует активный grow_cycle с current_phase_id")

        command_plans = snapshot.command_plans if isinstance(snapshot.command_plans, Mapping) else {}
        schema_version = int(command_plans.get("schema_version") or 0)
        if schema_version != self._ports.supported_schema_version():
            raise PlannerConfigurationError(f"Неподдерживаемая версия command_plans.schema_version={schema_version}")

        plans = command_plans.get("plans")
        diagnostics = plans.get("diagnostics") if isinstance(plans, Mapping) else None
        if not isinstance(diagnostics, Mapping):
            raise PlannerConfigurationError("Обязателен раздел command_plans.plans.diagnostics")

        execution = snapshot.diagnostics_execution if isinstance(snapshot.diagnostics_execution, Mapping) else {}
        workflow = str(execution.get("workflow") or "").strip().lower()
        topology = str(execution.get("topology") or "").strip().lower()
        if workflow != "cycle_start":
            raise PlannerConfigurationError(
                f"Неподдерживаемый diagnostics workflow для cycle_start planner: {workflow or 'empty'}"
            )
        if not topology:
            raise PlannerConfigurationError("Для diagnostics execution обязательно указать topology")
        hydraulic = TopologyRegistry().try_pack(topology)
        if hydraulic is not None and hydraulic.plan_profile in {"two_tank", "single_tank"}:
            return self._ports.build_two_tank_plan(task=task, snapshot=snapshot, workflow=workflow, topology=topology)

        steps = diagnostics.get("steps")
        if not isinstance(steps, Sequence) or not steps:
            raise PlannerConfigurationError("command_plans.plans.diagnostics.steps должен быть непустым массивом")

        default_node_types = self._ports.normalize_node_types(execution.get("required_node_types"))
        planned_steps: List[PlannedCommand] = []
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, Mapping):
                raise PlannerConfigurationError(f"Некорректный шаг command plan на позиции {index}")

            requested_channel = str(raw_step.get("channel") or "").strip().lower()
            cmd = str(raw_step.get("cmd") or "").strip()
            params = raw_step.get("params")
            if not requested_channel or not cmd or not isinstance(params, Mapping):
                raise PlannerConfigurationError(
                    f"Каждый шаг command plan должен содержать channel/cmd/params (index={index})"
                )

            node_types = self._ports.normalize_node_types(raw_step.get("node_types")) or list(default_node_types)
            actuator = self._ports.resolve_actuator(
                actuators=snapshot.actuators,
                requested_channel=requested_channel,
                node_types=node_types,
            )
            planned_steps.append(
                PlannedCommand(
                    step_no=index,
                    node_uid=actuator.node_uid,
                    channel=actuator.channel,
                    payload={
                        "name": raw_step.get("name"),
                        "cmd": cmd,
                        "params": dict(params),
                        "requested_channel": requested_channel,
                        "allow_no_effect": bool(raw_step.get("allow_no_effect")),
                        "dedupe_bypass": bool(raw_step.get("dedupe_bypass")),
                        "timeout_sec": raw_step.get("timeout_sec"),
                    },
                )
            )

        default_node_types = self._ports.normalize_node_types(execution.get("required_node_types"))
        irr_node_uid = self._ports.resolve_single_node_uid(
            actuators=snapshot.actuators,
            node_types=default_node_types,
        )
        named_plans = {
            "irr_state_probe": (
                PlannedCommand(
                    step_no=1,
                    node_uid=irr_node_uid,
                    channel="storage_state",
                    payload={"name": "irr_state_probe", "cmd": "state", "params": {}},
                ),
            ),
        }

        return CommandPlan(
            task_type=task.task_type,
            workflow=workflow,
            topology=topology,
            steps=tuple(planned_steps),
            targets=snapshot.targets,
            named_plans=named_plans,
        )

    def assert_required_subsystems_enabled(self, *, pack: Any, snapshot: ZoneSnapshot) -> None:
        flags = subsystem_enabled_flags(snapshot)
        for subsystem_id in pack.required_subsystems:
            if flags.get(subsystem_id) is False:
                raise PlannerConfigurationError(
                    f"Подсистема {subsystem_id} обязательна для topology={pack.id}, но выключена"
                )
