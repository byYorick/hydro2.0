"""CycleStartPlanner for AE3-Lite v1."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.two_tank_runtime_spec import resolve_two_tank_runtime


class CycleStartPlanner:
    """Builds a deterministic sequential command plan for cycle_start."""

    SUPPORTED_SCHEMA_VERSION = 1
    LEGACY_EC_COMPONENT_CHANNELS = {
        "npk": "dose_ec_a",
        "calcium": "dose_ec_b",
        "magnesium": "dose_ec_c",
        "micro": "dose_ec_d",
    }
    MODERN_EC_COMPONENT_ROLES = {
        "npk": "ec_npk_pump",
        "calcium": "ec_calcium_pump",
        "magnesium": "ec_magnesium_pump",
        "micro": "ec_micro_pump",
    }
    _CORRECTION_PRECHECK_KEYS = ("ec", "ph_up", "ph_down")

    def build(self, *, task: AutomationTask, snapshot: ZoneSnapshot) -> CommandPlan:
        if task.task_type not in {"cycle_start", "irrigation_start"}:
            raise PlannerConfigurationError(f"Unsupported task_type for CycleStartPlanner: {task.task_type}")
        if task.zone_id != snapshot.zone_id:
            raise PlannerConfigurationError(
                f"AutomationTask.zone_id={task.zone_id} does not match ZoneSnapshot.zone_id={snapshot.zone_id}"
            )
        if str(snapshot.automation_runtime or "").strip().lower() != "ae3":
            raise PlannerConfigurationError("CycleStartPlanner requires zone.automation_runtime='ae3'")
        if snapshot.grow_cycle_id is None or snapshot.current_phase_id is None:
            raise PlannerConfigurationError("CycleStartPlanner requires an active grow_cycle with current_phase_id")

        command_plans = snapshot.command_plans if isinstance(snapshot.command_plans, Mapping) else {}
        schema_version = int(command_plans.get("schema_version") or 0)
        if schema_version != self.SUPPORTED_SCHEMA_VERSION:
            raise PlannerConfigurationError(f"Unsupported command_plans.schema_version={schema_version}")

        plans = command_plans.get("plans")
        diagnostics = plans.get("diagnostics") if isinstance(plans, Mapping) else None
        if not isinstance(diagnostics, Mapping):
            raise PlannerConfigurationError("command_plans.plans.diagnostics is required")

        execution = snapshot.diagnostics_execution if isinstance(snapshot.diagnostics_execution, Mapping) else {}
        workflow = str(execution.get("workflow") or "").strip().lower()
        topology = str(execution.get("topology") or "").strip().lower()
        if workflow != "cycle_start":
            raise PlannerConfigurationError(f"Unsupported diagnostics workflow for cycle_start planner: {workflow or 'empty'}")
        if not topology:
            raise PlannerConfigurationError("diagnostics execution topology is required")
        if topology in {"two_tank", "two_tank_drip_substrate_trays"}:
            return self._build_two_tank_plan(task=task, snapshot=snapshot, workflow=workflow, topology=topology)

        steps = diagnostics.get("steps")
        if not isinstance(steps, Sequence) or not steps:
            raise PlannerConfigurationError("command_plans.plans.diagnostics.steps must be a non-empty array")

        default_node_types = self._normalize_node_types(execution.get("required_node_types"))
        planned_steps: List[PlannedCommand] = []
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, Mapping):
                raise PlannerConfigurationError(f"Invalid command plan step at index={index}")

            requested_channel = str(raw_step.get("channel") or "").strip().lower()
            cmd = str(raw_step.get("cmd") or "").strip()
            params = raw_step.get("params")
            if not requested_channel or not cmd or not isinstance(params, Mapping):
                raise PlannerConfigurationError(
                    f"Each command step must define channel/cmd/params (index={index})"
                )

            node_types = self._normalize_node_types(raw_step.get("node_types")) or list(default_node_types)
            actuator = self._resolve_actuator(
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

        return CommandPlan(
            task_type=task.task_type,
            workflow=workflow,
            topology=topology,
            steps=tuple(planned_steps),
            targets=snapshot.targets,
        )

    def _build_two_tank_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        workflow: str,
        topology: str,
    ) -> CommandPlan:
        runtime = resolve_two_tank_runtime(snapshot)
        runtime = dict(runtime)
        runtime["zone_workflow_phase"] = str(getattr(snapshot, "workflow_phase", "") or "idle").strip().lower()
        named_plans: dict[str, tuple[PlannedCommand, ...]] = {}

        for plan_name, raw_steps in runtime["command_specs"].items():
            named_plans[plan_name] = tuple(
                self._build_named_step(
                    raw_step=raw_step,
                    step_no=index,
                    actuators=snapshot.actuators,
                )
                for index, raw_step in enumerate(raw_steps, start=1)
            )

        system_activate = self._resolve_service_commands(
            actuators=snapshot.actuators,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": int(runtime["sensor_mode_stabilization_time_sec"])},
        )
        system_deactivate = self._resolve_service_commands(
            actuators=snapshot.actuators,
            cmd="deactivate_sensor_mode",
            params={},
        )
        irr_node_uid = self._resolve_single_node_uid(
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

        # Resolve dosing actuators for correction module.
        # Optional: if a channel is absent from snapshot.actuators the correction
        # executor will raise PlannerConfigurationError at runtime, not at plan time.
        correction = dict(runtime.get("correction") or {})
        correction["actuators"] = self._resolve_correction_actuators(
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
                phase_cfg["actuators"] = self._resolve_correction_actuators(
                    actuators=snapshot.actuators,
                    correction=phase_cfg,
                )
                phase_configs[str(phase_key)] = phase_cfg
            if phase_configs:
                runtime["correction_by_phase"] = phase_configs

        self._validate_required_correction_calibrations(runtime=runtime)

        return CommandPlan(
            task_type=task.task_type,
            workflow=workflow,
            topology=topology,
            steps=tuple(),
            targets=snapshot.targets,
            named_plans=named_plans,
            runtime=runtime,
        )

    def _build_named_step(
        self,
        *,
        raw_step: Mapping[str, Any],
        step_no: int,
        actuators: Sequence[ZoneActuatorRef],
    ) -> PlannedCommand:
        actuator = self._resolve_actuator(
            actuators=actuators,
            requested_channel=str(raw_step.get("channel") or "").strip().lower(),
            node_types=self._normalize_node_types(raw_step.get("node_types")),
        )
        return PlannedCommand(
            step_no=step_no,
            node_uid=actuator.node_uid,
            channel=actuator.channel,
            payload={
                "cmd": str(raw_step["cmd"]),
                "params": dict(raw_step["params"]),
                "complete_on_ack": bool(raw_step.get("complete_on_ack")),
            },
        )

    def _resolve_service_commands(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        cmd: str,
        params: Mapping[str, Any],
    ) -> list[PlannedCommand]:
        steps: list[PlannedCommand] = []
        for node_type in ("ph", "ec"):
            candidates = [
                actuator
                for actuator in actuators
                if str(actuator.node_type).strip().lower() == node_type
                and str(actuator.channel).strip().lower() == "system"
            ]
            if len(candidates) > 1:
                raise PlannerConfigurationError(f"Ambiguous system channel resolution for node_type={node_type}")
            if len(candidates) == 1:
                steps.append(
                    PlannedCommand(
                        step_no=len(steps) + 1,
                        node_uid=candidates[0].node_uid,
                        channel="system",
                        payload={"cmd": cmd, "params": dict(params)},
                    )
                )
        return steps

    def _resolve_single_node_uid(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        node_types: Sequence[str],
    ) -> str:
        normalized_types = {str(item or "").strip().lower() for item in node_types if str(item or "").strip()}
        candidates = sorted(
            {
                str(actuator.node_uid).strip()
                for actuator in actuators
                if str(actuator.node_uid).strip()
                and (not normalized_types or str(actuator.node_type).strip().lower() in normalized_types)
            }
        )
        if len(candidates) != 1:
            raise PlannerConfigurationError(f"Expected exactly one runtime node for node_types={sorted(normalized_types)}")
        return candidates[0]

    def _normalize_node_types(self, raw_value: Any) -> List[str]:
        if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
            return []
        result: List[str] = []
        for item in raw_value:
            normalized = str(item or "").strip().lower()
            if normalized:
                result.append(normalized)
        return result

    def _validate_required_correction_calibrations(self, *, runtime: Mapping[str, Any]) -> None:
        seen_pairs: set[tuple[str, str]] = set()
        correction_candidates = []

        correction = runtime.get("correction")
        if isinstance(correction, Mapping):
            correction_candidates.append(correction)

        correction_by_phase = runtime.get("correction_by_phase")
        if isinstance(correction_by_phase, Mapping):
            correction_candidates.extend(
                cfg for cfg in correction_by_phase.values() if isinstance(cfg, Mapping)
            )

        for correction_cfg in correction_candidates:
            actuators = correction_cfg.get("actuators")
            if not isinstance(actuators, Mapping):
                continue
            for key in self._CORRECTION_PRECHECK_KEYS:
                actuator = actuators.get(key)
                self._validate_preflight_calibration(
                    actuator=actuator,
                    actuator_key=key,
                    seen_pairs=seen_pairs,
                )

    def _validate_preflight_calibration(
        self,
        *,
        actuator: Any,
        actuator_key: str,
        seen_pairs: set[tuple[str, str]],
    ) -> None:
        if not isinstance(actuator, Mapping):
            return

        node_uid = str(actuator.get("node_uid") or "").strip()
        channel = str(actuator.get("channel") or "").strip()
        if node_uid == "" or channel == "":
            return

        pair = (node_uid, channel.lower())
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)

        calibration = actuator.get("calibration")
        if isinstance(calibration, Mapping):
            return

        kind = "EC" if actuator_key.startswith("ec") else "PH"
        raise PlannerConfigurationError(
            f"{kind} dosing pump calibration is required (channel={channel}, node={node_uid})",
            code=ErrorCodes.ZONE_DOSING_CALIBRATION_MISSING_CRITICAL,
        )

    def _resolve_correction_actuators(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        correction: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resolve optional dosing actuator refs for the correction module.

        Returns a dict with keys "ec", "ec_actuators", "ph_up", "ph_down".
        Each value is either a dict {node_uid, channel, calibration} or None.
        Missing actuators are allowed — CorrectionPlanner will raise at dose time.
        """
        def _try_resolve(channel_name: str, node_types: List[str]) -> Any:
            aliases = self._resolve_channel_aliases(channel_name=channel_name, node_types=node_types)
            for candidate in aliases:
                try:
                    actuator = self._resolve_actuator(
                        actuators=actuators,
                        requested_channel=candidate,
                        node_types=node_types,
                    )
                    return {
                        "node_uid": actuator.node_uid,
                        "channel": actuator.channel,
                        "calibration": dict(actuator.pump_calibration) if isinstance(actuator.pump_calibration, Mapping) else None,
                    }
                except PlannerConfigurationError as exc:
                    if "Ambiguous actuator resolution" in str(exc):
                        raise
                    continue
            return None

        ec_channel = str(correction.get("dose_ec_channel") or "ec_npk_pump").strip().lower()
        ph_up_channel = str(correction.get("dose_ph_up_channel") or "ph_base_pump").strip().lower()
        ph_down_channel = str(correction.get("dose_ph_down_channel") or "ph_acid_pump").strip().lower()

        ec_actuators: dict[str, Any] = {}
        for actuator in actuators:
            role = str(actuator.role or "").strip().lower()
            channel = str(actuator.channel or "").strip().lower()
            node_type = str(actuator.node_type or "").strip().lower()
            if node_type != "ec":
                continue
            aliases = self._ec_aliases_for_actuator(role=role, channel=channel, pump_calibration=actuator.pump_calibration)
            if not aliases:
                continue
            value = {
                "node_uid": actuator.node_uid,
                "channel": actuator.channel,
                "calibration": dict(actuator.pump_calibration) if isinstance(actuator.pump_calibration, Mapping) else None,
            }
            for alias in aliases:
                ec_actuators.setdefault(alias, value)

        return {
            "ec": _try_resolve(ec_channel, ["ec"]),
            "ec_actuators": ec_actuators,
            "ph_up": _try_resolve(ph_up_channel, ["ph"]),
            "ph_down": _try_resolve(ph_down_channel, ["ph"]),
        }

    def _resolve_channel_aliases(self, *, channel_name: str, node_types: Sequence[str]) -> List[str]:
        requested = str(channel_name or "").strip().lower()
        aliases: List[str] = []
        if requested:
            aliases.append(requested)

        normalized_types = {str(item or "").strip().lower() for item in node_types if str(item or "").strip()}
        if "ec" in normalized_types:
            component_by_legacy = {
                value: key for key, value in self.LEGACY_EC_COMPONENT_CHANNELS.items()
            }
            if requested.startswith("dose_ec_"):
                suffix = requested.removeprefix("dose_ec_")
                if len(suffix) == 1 and suffix.isalpha():
                    aliases.append(f"pump_{suffix}")
                component = component_by_legacy.get(requested)
                if component:
                    aliases.extend([f"ec_{component}", f"ec_{component}_pump"])
                    modern_role = self.MODERN_EC_COMPONENT_ROLES.get(component)
                    if modern_role:
                        aliases.append(modern_role)
            if requested.startswith("ec_"):
                component = requested.removeprefix("ec_")
                if component.endswith("_pump"):
                    component = component.removesuffix("_pump")
                component = component.strip().lower()
                if component:
                    legacy_channel = self.LEGACY_EC_COMPONENT_CHANNELS.get(component)
                    if legacy_channel:
                        aliases.append(legacy_channel)
                        suffix = legacy_channel.removeprefix("dose_ec_")
                        if len(suffix) == 1 and suffix.isalpha():
                            aliases.append(f"pump_{suffix}")
                    modern_role = self.MODERN_EC_COMPONENT_ROLES.get(component)
                    if modern_role:
                        aliases.append(modern_role)
            if requested.startswith("pump_"):
                suffix = requested.removeprefix("pump_")
                if len(suffix) == 1 and suffix.isalpha():
                    legacy_channel = f"dose_ec_{suffix}"
                    aliases.append(legacy_channel)
                    component = component_by_legacy.get(legacy_channel)
                    if component:
                        aliases.extend([f"ec_{component}", f"ec_{component}_pump"])
                        modern_role = self.MODERN_EC_COMPONENT_ROLES.get(component)
                        if modern_role:
                            aliases.append(modern_role)

        if "ph" in normalized_types and requested in {"dose_ph_up", "ph_base_pump", "pump_base"}:
            aliases.extend(["dose_ph_up", "ph_base_pump", "pump_base"])
        if "ph" in normalized_types and requested in {"dose_ph_down", "ph_acid_pump", "pump_acid"}:
            aliases.extend(["dose_ph_down", "ph_acid_pump", "pump_acid"])

        deduped: List[str] = []
        for alias in aliases:
            if alias and alias not in deduped:
                deduped.append(alias)
        return deduped

    def _ec_aliases_for_actuator(
        self,
        *,
        role: str,
        channel: str,
        pump_calibration: Mapping[str, Any] | None,
    ) -> List[str]:
        aliases: List[str] = []
        for value in (role, channel):
            normalized = str(value or "").strip().lower()
            if normalized:
                aliases.append(normalized)

        component_by_legacy = {
            value: key for key, value in self.LEGACY_EC_COMPONENT_CHANNELS.items()
        }
        component = self._extract_ec_component(role=role, pump_calibration=pump_calibration)
        if not component:
            component = component_by_legacy.get(role)
        if not component and channel.startswith("pump_"):
            suffix = channel.removeprefix("pump_")
            if len(suffix) == 1 and suffix.isalpha():
                component = component_by_legacy.get(f"dose_ec_{suffix}")
        if component:
            aliases.append(f"ec_{component}")
            modern_role = self.MODERN_EC_COMPONENT_ROLES.get(component)
            if modern_role:
                aliases.append(modern_role)
            legacy_channel = self.LEGACY_EC_COMPONENT_CHANNELS.get(component)
            if legacy_channel:
                aliases.append(legacy_channel)

        if channel.startswith("pump_"):
            suffix = channel.removeprefix("pump_")
            if len(suffix) == 1 and suffix.isalpha():
                aliases.append(f"dose_ec_{suffix}")

        deduped: List[str] = []
        for alias in aliases:
            if alias and alias not in deduped:
                deduped.append(alias)
        return [alias for alias in deduped if alias.startswith("dose_ec") or alias.startswith("ec_") or alias.startswith("pump_")]

    def _extract_ec_component(
        self,
        *,
        role: str,
        pump_calibration: Mapping[str, Any] | None,
    ) -> str | None:
        if isinstance(pump_calibration, Mapping):
            raw_component = str(pump_calibration.get("component") or "").strip().lower()
            if raw_component:
                return raw_component

        if role.startswith("ec_") and role.endswith("_pump"):
            component = role.removeprefix("ec_").removesuffix("_pump").strip().lower()
            return component or None

        return None

    def _resolve_actuator(
        self,
        *,
        actuators: Iterable[ZoneActuatorRef],
        requested_channel: str,
        node_types: Sequence[str],
    ) -> ZoneActuatorRef:
        normalized_types = {str(item).strip().lower() for item in node_types if str(item).strip()}
        candidates: List[tuple[tuple[int, int], ZoneActuatorRef]] = []
        for actuator in actuators:
            role = str(actuator.role or "").strip().lower()
            channel = str(actuator.channel or "").strip().lower()
            node_type = str(actuator.node_type or "").strip().lower()
            if normalized_types and node_type not in normalized_types:
                continue
            if requested_channel not in {role, channel}:
                continue
            candidates.append(
                (
                    (0 if role == requested_channel else 1, 0 if channel == requested_channel else 1),
                    actuator,
                )
            )
        if not candidates:
            raise PlannerConfigurationError(
                f"No online actuator matches requested_channel={requested_channel} node_types={sorted(normalized_types)}"
            )
        candidates.sort(key=lambda item: (item[0], item[1].node_uid, item[1].channel, item[1].node_channel_id))

        best_rank = candidates[0][0]
        equally_ranked = [item[1] for item in candidates if item[0] == best_rank]
        if len(equally_ranked) > 1:
            raise PlannerConfigurationError(
                f"Ambiguous actuator resolution for requested_channel={requested_channel}: "
                f"{[item.node_uid for item in equally_ranked]}"
            )
        return equally_ranked[0]
