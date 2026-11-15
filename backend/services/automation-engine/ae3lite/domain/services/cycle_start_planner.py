"""CycleStartPlanner для AE3-Lite v1."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, List, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneActuatorRef, ZoneSnapshot
from ae3lite.application.services.stage_runtime_config import StageRuntimeConfig
from ae3lite.application.services.topology_pack import subsystem_enabled_flags
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.loader import load_zone_correction
from ae3lite.config.runtime_plan_builder import (
    HL_RUN_PUMP_MAX_DURATION_MS,
    _build_day_night_config,
    assemble_pack_runtime,
)
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.dli_integral import (
    DliTickDecision,
    decide_on_tick_duty,
    parse_dli_moment,
    parse_observation_samples,
    positive_dli_target,
)
from ae3lite.infrastructure.metrics import SHADOW_CONFIG_VALIDATION, record_dli_tick_status


from ae3lite.domain.services.cycle_planning_shared import _logger, _schedule_dli_sensor_alert

from ae3lite.domain.services.cycle_planning_dispatch import CyclePlanningDispatch, CyclePlanningDispatchPorts
from ae3lite.domain.services.cycle_planning_two_tank import CyclePlanningTwoTank, CyclePlanningTwoTankPorts
from ae3lite.domain.services.cycle_planning_validation import CyclePlanningValidation, CyclePlanningValidationPorts
from ae3lite.domain.services.cycle_planning_lighting import CyclePlanningLighting, CyclePlanningLightingPorts
from ae3lite.domain.services.cycle_planning_solution import CyclePlanningSolution, CyclePlanningSolutionPorts
from ae3lite.domain.services.cycle_planning_commands import CyclePlanningCommands, CyclePlanningCommandsPorts
from ae3lite.domain.services.cycle_planning_actuators import CyclePlanningActuators, CyclePlanningActuatorsPorts


class CycleStartPlanner:
    """Строит детерминированный последовательный command plan для cycle_start."""

    SUPPORTED_SCHEMA_VERSION = 1
    _CORRECTION_PRECHECK_KEYS = ("ec", "ph_up", "ph_down")
    _SHADOW_WARNING_WINDOW_SEC = 60.0

    def __init__(
        self,
        *,
        monotonic_clock: Callable[[], float] | None = None,
        dli_alert_writer: Callable[[int, str], None] | None = None,
    ) -> None:
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._shadow_warning_last_logged_at: dict[object, float] = {}
        self._dli_alert_writer = dli_alert_writer or _schedule_dli_sensor_alert
        self._dli_alerted_local_days: set[tuple[int, str]] = set()
        self._cycle_planning_dispatch = CyclePlanningDispatch(
            CyclePlanningDispatchPorts(
                supported_schema_version=lambda: self.SUPPORTED_SCHEMA_VERSION,
                build_lighting_tick_plan=lambda *args, **kwargs: self._build_lighting_tick_plan(*args, **kwargs),
                build_solution_change_plan=lambda *args, **kwargs: self._build_solution_change_plan(*args, **kwargs),
                build_solution_topup_plan=lambda *args, **kwargs: self._build_solution_topup_plan(*args, **kwargs),
                build_two_tank_plan=lambda *args, **kwargs: self._build_two_tank_plan(*args, **kwargs),
                normalize_node_types=lambda *args, **kwargs: self._normalize_node_types(*args, **kwargs),
                resolve_actuator=lambda *args, **kwargs: self._resolve_actuator(*args, **kwargs),
                resolve_single_node_uid=lambda *args, **kwargs: self._resolve_single_node_uid(*args, **kwargs),
            )
        )
        self._cycle_planning_two_tank = CyclePlanningTwoTank(
            CyclePlanningTwoTankPorts(
                assert_required_subsystems_enabled=lambda *args, **kwargs: self._assert_required_subsystems_enabled(
                    *args, **kwargs
                ),
                build_named_step=lambda *args, **kwargs: self._build_named_step(*args, **kwargs),
                resolve_correction_actuators=lambda *args, **kwargs: self._resolve_correction_actuators(
                    *args, **kwargs
                ),
                resolve_service_commands=lambda *args, **kwargs: self._resolve_service_commands(*args, **kwargs),
                resolve_single_node_uid=lambda *args, **kwargs: self._resolve_single_node_uid(*args, **kwargs),
                shadow_validate_correction=lambda *args, **kwargs: self._shadow_validate_correction(*args, **kwargs),
                validate_required_correction_calibrations=lambda *args, **kwargs: (
                    self._validate_required_correction_calibrations(*args, **kwargs)
                ),
                global_assemble_pack_runtime=lambda *args, **kwargs: assemble_pack_runtime(*args, **kwargs),
            )
        )
        self._cycle_planning_validation = CyclePlanningValidation(
            CyclePlanningValidationPorts(
                correction_precheck_keys=lambda: self._CORRECTION_PRECHECK_KEYS,
                shadow_warning_window_sec=lambda: self._SHADOW_WARNING_WINDOW_SEC,
                monotonic_clock=lambda: self._monotonic_clock,
                shadow_warning_last_logged_at=lambda: self._shadow_warning_last_logged_at,
                global_load_zone_correction=lambda *args, **kwargs: load_zone_correction(*args, **kwargs),
            )
        )
        self._cycle_planning_lighting = CyclePlanningLighting(
            CyclePlanningLightingPorts(
                dli_alert_writer=lambda: self._dli_alert_writer,
                dli_alerted_local_days=lambda: self._dli_alerted_local_days,
            )
        )
        self._cycle_planning_solution = CyclePlanningSolution(
            CyclePlanningSolutionPorts(
                build_two_tank_plan=lambda *args, **kwargs: self._build_two_tank_plan(*args, **kwargs),
            )
        )
        self._cycle_planning_commands = CyclePlanningCommands(
            CyclePlanningCommandsPorts(
                resolve_actuator=lambda *args, **kwargs: self._resolve_actuator(*args, **kwargs),
            )
        )
        self._cycle_planning_actuators = CyclePlanningActuators(CyclePlanningActuatorsPorts())

    def build(self, *, task: AutomationTask, snapshot: ZoneSnapshot) -> CommandPlan:
        return self._cycle_planning_dispatch.build(task=task, snapshot=snapshot)

    def _assert_required_subsystems_enabled(self, *, pack: Any, snapshot: ZoneSnapshot) -> None:
        return self._cycle_planning_dispatch.assert_required_subsystems_enabled(pack=pack, snapshot=snapshot)

    def _build_two_tank_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        workflow: str,
        topology: str,
    ) -> CommandPlan:
        return self._cycle_planning_two_tank.build_two_tank_plan(
            task=task, snapshot=snapshot, workflow=workflow, topology=topology
        )

    def _shadow_validate_correction(
        self,
        *,
        snapshot: ZoneSnapshot,
        task: AutomationTask,
    ) -> None:
        return self._cycle_planning_validation.shadow_validate_correction(snapshot=snapshot, task=task)

    def _log_shadow_validation_failure(
        self,
        *,
        zone_id: object,
        invalid_namespaces: Sequence[str],
        violations: Sequence[dict[str, Any]],
    ) -> None:
        return self._cycle_planning_validation.log_shadow_validation_failure(
            zone_id=zone_id, invalid_namespaces=invalid_namespaces, violations=violations
        )

    def _build_lighting_tick_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        return self._cycle_planning_lighting.build_lighting_tick_plan(task=task, snapshot=snapshot)

    def _build_solution_topup_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        return self._cycle_planning_solution.build_solution_topup_plan(task=task, snapshot=snapshot)

    def _build_solution_change_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        return self._cycle_planning_solution.build_solution_change_plan(task=task, snapshot=snapshot)

    def _pick_lighting_actuator(self, actuators: Sequence[ZoneActuatorRef]) -> ZoneActuatorRef | None:
        return self._cycle_planning_lighting.pick_lighting_actuator(actuators=actuators)

    def _lighting_tick_intent_payload(self, task: AutomationTask) -> Mapping[str, Any]:
        return self._cycle_planning_lighting.lighting_tick_intent_payload(task=task)

    def _clamp_brightness_pct(self, raw: Any, *, default: int = 100) -> int:
        return self._cycle_planning_lighting.clamp_brightness_pct(raw=raw, default=default)

    def _pick_target_brightness(self, lighting_targets: Mapping[str, Any], *, day: bool) -> int | None:
        return self._cycle_planning_lighting.pick_target_brightness(lighting_targets=lighting_targets, day=day)

    def _apply_dli_ceiling(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        lighting_targets: Mapping[str, Any],
        requested_duty: int,
    ) -> DliTickDecision:
        return self._cycle_planning_lighting.apply_dli_ceiling(
            task=task, snapshot=snapshot, lighting_targets=lighting_targets, requested_duty=requested_duty
        )

    def _note_dli_sensor_unavailable(self, *, zone_id: int, local_date: str) -> None:
        return self._cycle_planning_lighting.note_dli_sensor_unavailable(zone_id=zone_id, local_date=local_date)

    def _resolve_lighting_on_duty(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        lighting_targets: Mapping[str, Any],
    ) -> int:
        return self._cycle_planning_lighting.resolve_lighting_on_duty(
            task=task, snapshot=snapshot, lighting_targets=lighting_targets
        )

    def _resolve_lighting_pwm_duty(self, lighting_targets: Mapping[str, Any]) -> int:
        return self._cycle_planning_lighting.resolve_lighting_pwm_duty(lighting_targets=lighting_targets)

    def _lighting_cmd_for_channel(
        self,
        *,
        channel: str,
        duty: int,
        desired_on: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        return self._cycle_planning_lighting.lighting_cmd_for_channel(channel=channel, duty=duty, desired_on=desired_on)

    def _apply_irrigation_decision_snapshot(
        self,
        *,
        task: AutomationTask,
        runtime: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._cycle_planning_two_tank.apply_irrigation_decision_snapshot(task=task, runtime=runtime)

    def _resolve_irrigation_duration_sec(self, *, task: AutomationTask, runtime: Mapping[str, Any]) -> int:
        return self._cycle_planning_two_tank.resolve_irrigation_duration_sec(task=task, runtime=runtime)

    def _apply_irrigation_start_actuation(
        self,
        *,
        task: AutomationTask,
        runtime: Mapping[str, Any],
        named_plans: dict[str, tuple[PlannedCommand, ...]],
        actuators: Sequence[ZoneActuatorRef],
    ) -> None:
        return self._cycle_planning_two_tank.apply_irrigation_start_actuation(
            task=task, runtime=runtime, named_plans=named_plans, actuators=actuators
        )

    def _build_named_step(
        self,
        *,
        raw_step: Mapping[str, Any],
        step_no: int,
        actuators: Sequence[ZoneActuatorRef],
    ) -> PlannedCommand:
        return self._cycle_planning_commands.build_named_step(raw_step=raw_step, step_no=step_no, actuators=actuators)

    def _resolve_service_commands(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        cmd: str,
        params: Mapping[str, Any],
    ) -> list[PlannedCommand]:
        return self._cycle_planning_commands.resolve_service_commands(actuators=actuators, cmd=cmd, params=params)

    def _resolve_single_node_uid(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        node_types: Sequence[str],
    ) -> str:
        return self._cycle_planning_commands.resolve_single_node_uid(actuators=actuators, node_types=node_types)

    def _normalize_node_types(self, raw_value: Any) -> List[str]:
        return self._cycle_planning_commands.normalize_node_types(raw_value=raw_value)

    def _validate_required_correction_calibrations(self, *, runtime: Mapping[str, Any]) -> None:
        return self._cycle_planning_validation.validate_required_correction_calibrations(runtime=runtime)

    def _validate_preflight_calibration(
        self,
        *,
        actuator: Any,
        actuator_key: str,
        seen_pairs: set[tuple[str, str]],
    ) -> None:
        return self._cycle_planning_validation.validate_preflight_calibration(
            actuator=actuator, actuator_key=actuator_key, seen_pairs=seen_pairs
        )

    def _resolve_correction_actuators(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        correction: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._cycle_planning_actuators.resolve_correction_actuators(actuators=actuators, correction=correction)

    def _extract_ec_component(
        self,
        *,
        role: str,
        pump_calibration: Mapping[str, Any] | None,
        channel: str = "",
    ) -> str | None:
        return self._cycle_planning_actuators.extract_ec_component(
            role=role, pump_calibration=pump_calibration, channel=channel
        )

    def _resolve_actuator(
        self,
        *,
        actuators: Iterable[ZoneActuatorRef],
        requested_channel: str,
        node_types: Sequence[str],
    ) -> ZoneActuatorRef:
        return self._cycle_planning_actuators.resolve_actuator(
            actuators=actuators, requested_channel=requested_channel, node_types=node_types
        )
