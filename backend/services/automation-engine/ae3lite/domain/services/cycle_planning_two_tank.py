"""CycleStartPlanner two tank: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneActuatorRef, ZoneSnapshot
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.config.runtime_plan_builder import (
    HL_RUN_PUMP_MAX_DURATION_MS,
)
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import PlannerConfigurationError


@dataclass(frozen=True)
class CyclePlanningTwoTankPorts:
    assert_required_subsystems_enabled: Callable[..., Any]
    build_named_step: Callable[..., Any]
    resolve_correction_actuators: Callable[..., Any]
    resolve_service_commands: Callable[..., Any]
    resolve_single_node_uid: Callable[..., Any]
    shadow_validate_correction: Callable[..., Any]
    validate_required_correction_calibrations: Callable[..., Any]
    global_assemble_pack_runtime: Callable[..., Any]


class CyclePlanningTwoTank:
    def __init__(self, ports: CyclePlanningTwoTankPorts) -> None:
        self._ports = ports

    def build_two_tank_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        workflow: str,
        topology: str,
    ) -> CommandPlan:
        pack = TopologyRegistry().pack(topology)
        self._ports.assert_required_subsystems_enabled(pack=pack, snapshot=snapshot)
        self._ports.shadow_validate_correction(snapshot=snapshot, task=task)
        runtime = self._ports.global_assemble_pack_runtime(snapshot, pack)
        runtime = self.apply_irrigation_decision_snapshot(task=task, runtime=runtime)
        runtime = dict(runtime)
        runtime["zone_workflow_phase"] = str(getattr(snapshot, "workflow_phase", "") or "idle").strip().lower()
        # Phase 5: inject zones.config_revision so `_checkpoint()` can compare
        # against DB revision to trigger hot-reload in live mode.
        snapshot_config_rev = getattr(snapshot, "config_revision", None)
        if snapshot_config_rev is not None:
            runtime["config_revision"] = int(snapshot_config_rev)
        named_plans: dict[str, tuple[PlannedCommand, ...]] = {}

        for plan_name, raw_steps in runtime["command_specs"].items():
            named_plans[plan_name] = tuple(
                self._ports.build_named_step(
                    raw_step=raw_step,
                    step_no=index,
                    actuators=snapshot.actuators,
                )
                for index, raw_step in enumerate(raw_steps, start=1)
            )

        system_activate = self._ports.resolve_service_commands(
            actuators=snapshot.actuators,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": int(runtime["sensor_mode_stabilization_time_sec"])},
        )
        system_deactivate = self._ports.resolve_service_commands(
            actuators=snapshot.actuators,
            cmd="deactivate_sensor_mode",
            params={},
        )
        irr_node_uid = self._ports.resolve_single_node_uid(
            actuators=snapshot.actuators,
            node_types=runtime["required_node_types"],
        )
        named_plans["sensor_mode_activate"] = tuple(system_activate)
        named_plans["sensor_mode_deactivate"] = tuple(system_deactivate)
        named_plans["irr_state_probe"] = (
            PlannedCommand(
                step_no=1,
                node_uid=irr_node_uid,
                channel="storage_state",
                payload={"name": "irr_state_probe", "cmd": "state", "params": {}},
            ),
        )

        self.apply_irrigation_start_actuation(
            task=task,
            runtime=runtime,
            named_plans=named_plans,
            actuators=snapshot.actuators,
        )

        # Разрешить dosing actuator'ы для модуля коррекции.
        # Это опционально: если канала нет в `snapshot.actuators`, correction executor
        # выбросит `PlannerConfigurationError` уже во время выполнения, а не на этапе планирования.
        correction = dict(runtime.get("correction") or {})
        correction["actuators"] = self._ports.resolve_correction_actuators(
            actuators=snapshot.actuators,
            correction=correction,
        )
        runtime = dict(runtime)
        runtime["correction"] = correction
        correction_by_phase = runtime.get("correction_by_phase")
        if isinstance(correction_by_phase, Mapping):
            phase_configs: dict[str, dict[str, Any]] = {}
            for phase_key, cfg in correction_by_phase.items():
                if not isinstance(cfg, Mapping):
                    continue
                phase_cfg = dict(cfg)
                phase_cfg["actuators"] = self._ports.resolve_correction_actuators(
                    actuators=snapshot.actuators,
                    correction=phase_cfg,
                )
                phase_configs[str(phase_key)] = phase_cfg
            if phase_configs:
                runtime["correction_by_phase"] = phase_configs

        self._ports.validate_required_correction_calibrations(runtime=runtime)

        # Phase 3.1 / B-5c: validate dict→RuntimePlan at the planner boundary.
        # On drift this raises ConfigValidationError; cycle_start fails closed
        # (correct: a drift between resolver and Pydantic model is a bug).
        # The legacy dict mutations above (zone_workflow_phase, actuators
        # injection, correction_by_phase rebuild) are now part of the typed
        # contract — `RuntimePlan.zone_workflow_phase` and
        # `CorrectionPhaseRuntime.actuators` cover them.
        from ae3lite.config.loader import load_runtime_plan

        typed_runtime = load_runtime_plan(
            runtime,
            zone_id=int(getattr(snapshot, "zone_id", 0) or 0) or None,
            namespace="runtime.plan:two_tank",
        )

        return CommandPlan(
            task_type=task.task_type,
            workflow=workflow,
            topology=topology,
            steps=tuple(),
            targets=snapshot.targets,
            named_plans=named_plans,
            runtime=typed_runtime,
        )

    def apply_irrigation_decision_snapshot(
        self,
        *,
        task: AutomationTask,
        runtime: Mapping[str, Any],
    ) -> dict[str, Any]:
        if str(getattr(task, "task_type", "") or "").strip().lower() != "irrigation_start":
            return dict(runtime)

        locked_strategy = str(getattr(task, "irrigation_decision_strategy", "") or "").strip().lower()
        locked_config = getattr(task, "irrigation_decision_config", None)
        locked_bundle_revision = str(getattr(task, "irrigation_bundle_revision", "") or "").strip()
        if locked_strategy == "" and not isinstance(locked_config, Mapping) and locked_bundle_revision == "":
            return dict(runtime)

        runtime_copy = dict(runtime)
        decision = runtime_copy.get("irrigation_decision")
        decision_mapping = dict(decision) if isinstance(decision, Mapping) else {}
        config = decision_mapping.get("config")
        config_mapping = dict(config) if isinstance(config, Mapping) else {}
        if isinstance(locked_config, Mapping):
            config_mapping.update(dict(locked_config))
        if locked_strategy != "":
            decision_mapping["strategy"] = locked_strategy
        decision_mapping["config"] = config_mapping
        runtime_copy["irrigation_decision"] = decision_mapping
        if locked_bundle_revision != "":
            runtime_copy["bundle_revision"] = locked_bundle_revision
        return runtime_copy

    def resolve_irrigation_duration_sec(self, *, task: AutomationTask, runtime: Mapping[str, Any]) -> int:
        raw = getattr(task, "irrigation_requested_duration_sec", None)
        if raw is None:
            irrigation = runtime.get("irrigation_execution")
            raw = irrigation.get("duration_sec") if isinstance(irrigation, Mapping) else None
        try:
            return max(1, min(3600, int(raw)))
        except (TypeError, ValueError):
            irrigation = runtime.get("irrigation_execution")
            fallback = irrigation.get("duration_sec") if isinstance(irrigation, Mapping) else None
            try:
                return max(1, min(3600, int(fallback)))
            except (TypeError, ValueError):
                return 120

    def apply_irrigation_start_actuation(
        self,
        *,
        task: AutomationTask,
        runtime: Mapping[str, Any],
        named_plans: dict[str, tuple[PlannedCommand, ...]],
        actuators: Sequence[ZoneActuatorRef],
    ) -> None:
        if str(getattr(task, "task_type", "") or "").strip().lower() != "irrigation_start":
            return

        duration_sec = self.resolve_irrigation_duration_sec(task=task, runtime=runtime)
        duration_ms = max(1000, min(3_600_000, int(duration_sec) * 1000))
        if duration_ms > HL_RUN_PUMP_MAX_DURATION_MS:
            raise PlannerConfigurationError(
                "irrigation_start run_pump duration_ms="
                f"{duration_ms} exceeds history-logger ceiling {HL_RUN_PUMP_MAX_DURATION_MS}; "
                "refusing to open valves before an INVALID pump command"
            )
        steps: list[tuple[str, str, dict[str, Any]]] = [
            ("valve_solution_supply", "set_relay", {"state": True}),
            ("valve_irrigation", "set_relay", {"state": True}),
            ("pump_main", "run_pump", {"duration_ms": duration_ms}),
        ]
        named_plans["irrigation_start"] = tuple(
            self._ports.build_named_step(
                raw_step={"channel": channel, "cmd": cmd, "params": params},
                step_no=index,
                actuators=actuators,
            )
            for index, (channel, cmd, params) in enumerate(steps, start=1)
        )
