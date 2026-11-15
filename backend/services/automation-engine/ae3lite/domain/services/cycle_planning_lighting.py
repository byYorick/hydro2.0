"""CycleStartPlanner lighting: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneActuatorRef, ZoneSnapshot
from ae3lite.application.services.stage_runtime_config import StageRuntimeConfig
from ae3lite.config.runtime_plan_builder import (
    _build_day_night_config,
)
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.cycle_planning_shared import _logger
from ae3lite.domain.services.dli_integral import (
    DliTickDecision,
    decide_on_tick_duty,
    parse_dli_moment,
    parse_observation_samples,
    positive_dli_target,
)
from ae3lite.infrastructure.metrics import record_dli_tick_status


@dataclass(frozen=True)
class CyclePlanningLightingPorts:
    dli_alert_writer: Callable[[], Any]
    dli_alerted_local_days: Callable[[], Any]


class CyclePlanningLighting:
    def __init__(self, ports: CyclePlanningLightingPorts) -> None:
        self._ports = ports

    def build_lighting_tick_plan(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
    ) -> CommandPlan:
        """Один MQTT command batch для scheduler-driven lighting (AE3 C1)."""
        if str(snapshot.automation_runtime or "").strip().lower() != "ae3":
            raise PlannerConfigurationError("Для lighting_tick требуется zone.automation_runtime='ae3'")
        if task.zone_id != snapshot.zone_id:
            raise PlannerConfigurationError(
                f"AutomationTask.zone_id={task.zone_id} не совпадает с ZoneSnapshot.zone_id={snapshot.zone_id}"
            )
        actuators = snapshot.actuators
        if not actuators:
            raise PlannerConfigurationError(
                "Для lighting_tick требуется хотя бы один online actuator mapping в snapshot зоны",
            )
        ref = self.pick_lighting_actuator(actuators)
        if ref is None:
            raise PlannerConfigurationError(
                "Для lighting_tick не найден lighting actuator channel, например light_main",
            )

        targets = snapshot.targets if isinstance(snapshot.targets, Mapping) else {}
        lighting_targets = targets.get("lighting") if isinstance(targets.get("lighting"), Mapping) else {}
        payload = self.lighting_tick_intent_payload(task)
        raw_desired = payload.get("desired_state")
        desired_state = str(raw_desired or "").strip().lower()
        if desired_state not in {"on", "off"}:
            raise PlannerConfigurationError(
                f"lighting_tick desired_state must be 'on' or 'off', got {raw_desired!r}",
            )
        channel = str(ref.channel or "").strip().lower()
        if desired_state == "off":
            cmd, params = self.lighting_cmd_for_channel(channel=channel, duty=0, desired_on=False)
            dli_fields: dict[str, Any] = {}
        else:
            duty = self.resolve_lighting_on_duty(
                task=task,
                snapshot=snapshot,
                lighting_targets=lighting_targets,
            )
            decision = self.apply_dli_ceiling(
                task=task,
                snapshot=snapshot,
                lighting_targets=lighting_targets,
                requested_duty=duty,
            )
            cmd, params = self.lighting_cmd_for_channel(
                channel=channel,
                duty=decision.duty,
                desired_on=decision.duty > 0,
            )
            dli_fields = {
                "dli_status": decision.status,
                "dli_mol": decision.dli_mol,
            }
        planned = PlannedCommand(
            step_no=1,
            node_uid=ref.node_uid,
            channel=ref.channel,
            payload={
                "name": "lighting_tick",
                "cmd": cmd,
                "params": params,
                "complete_on_ack": True,
                **dli_fields,
            },
        )
        plan = CommandPlan(
            task_type=task.task_type,
            workflow="lighting_tick",
            topology="lighting_tick",
            steps=(planned,),
            targets=dict(targets),
            named_plans={},
            runtime=None,
        )
        status = dli_fields.get("dli_status")
        if status is not None:
            record_dli_tick_status(str(status))
        return plan

    def pick_lighting_actuator(self, actuators: Sequence[ZoneActuatorRef]) -> ZoneActuatorRef | None:
        preferred = ("light_main", "main_light", "pwm_light", "light_pwm")
        for name in preferred:
            for a in actuators:
                if str(a.channel or "").strip().lower() == name:
                    return a
        for a in actuators:
            ch = str(a.channel or "").strip().lower()
            if "light" in ch:
                return a
        return None

    def lighting_tick_intent_payload(self, task: AutomationTask) -> Mapping[str, Any]:
        intent_meta = getattr(task, "intent_meta", None)
        if not isinstance(intent_meta, Mapping):
            return {}
        payload = intent_meta.get("intent_payload")
        return dict(payload) if isinstance(payload, Mapping) else {}

    def clamp_brightness_pct(self, raw: Any, *, default: int = 100) -> int:
        try:
            return max(0, min(100, int(float(raw))))
        except (TypeError, ValueError):
            return default

    def pick_target_brightness(self, lighting_targets: Mapping[str, Any], *, day: bool) -> int | None:
        keys = ("brightness", "brightness_pct", "pwm_duty") if day else ("brightness_night",)
        for key in keys:
            raw = lighting_targets.get(key)
            if raw is None:
                continue
            try:
                return max(0, min(100, int(float(raw))))
            except (TypeError, ValueError):
                continue
        return None

    def apply_dli_ceiling(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        lighting_targets: Mapping[str, Any],
        requested_duty: int,
    ) -> DliTickDecision:
        observation = getattr(snapshot, "dli_light_series", None)
        observation_map = observation if isinstance(observation, Mapping) else {}
        window_start = parse_dli_moment(observation_map.get("window_start"))
        window_end = parse_dli_moment(observation_map.get("as_of"))
        timezone_name = observation_map.get("timezone") or (
            snapshot.targets.get("greenhouse_timezone") if isinstance(snapshot.targets, Mapping) else None
        )
        unit = observation_map.get("unit") if observation_map else None
        decision = decide_on_tick_duty(
            requested_duty=requested_duty,
            dli_target=positive_dli_target(lighting_targets.get("dli_target")),
            unit=None if unit is None else str(unit),
            samples=parse_observation_samples(observation_map),
            window_start=window_start,
            window_end=window_end,
            timezone_name=timezone_name,
        )
        if decision.status == "sensor_unavailable":
            self.note_dli_sensor_unavailable(zone_id=int(task.zone_id), local_date=decision.local_date)
        return decision

    def note_dli_sensor_unavailable(self, *, zone_id: int, local_date: str) -> None:
        key = (int(zone_id), str(local_date))
        if key in self._ports.dli_alerted_local_days():
            return
        self._ports.dli_alerted_local_days().add(key)
        try:
            self._ports.dli_alert_writer()(int(zone_id), str(local_date))
        except Exception:
            self._ports.dli_alerted_local_days().discard(key)
            _logger.warning(
                "ae3_dli_sensor_unavailable_alert_failed",
                extra={"zone_id": int(zone_id), "local_date": str(local_date)},
                exc_info=True,
            )

    def resolve_lighting_on_duty(
        self,
        *,
        task: AutomationTask,
        snapshot: ZoneSnapshot,
        lighting_targets: Mapping[str, Any],
    ) -> int:
        payload = self.lighting_tick_intent_payload(task)
        if payload.get("brightness_pct") is not None:
            return self.clamp_brightness_pct(payload["brightness_pct"])

        day_duty = self.pick_target_brightness(lighting_targets, day=True)
        night_duty = self.pick_target_brightness(lighting_targets, day=False)
        if day_duty is not None or night_duty is not None:
            day_night_cfg = _build_day_night_config(snapshot)
            is_day = StageRuntimeConfig.is_day_now(day_night_cfg) if bool(day_night_cfg.get("enabled")) else True
            chosen = day_duty if is_day else night_duty
            if chosen is not None:
                return chosen
            fallback = night_duty if is_day else day_duty
            if fallback is not None:
                return fallback

        return self.resolve_lighting_pwm_duty(lighting_targets)

    def resolve_lighting_pwm_duty(self, lighting_targets: Mapping[str, Any]) -> int:
        raw = lighting_targets.get("pwm_duty") if isinstance(lighting_targets, Mapping) else None
        if raw is None:
            raw = lighting_targets.get("brightness") if isinstance(lighting_targets, Mapping) else None
        if raw is None:
            raw = lighting_targets.get("brightness_pct") if isinstance(lighting_targets, Mapping) else None
        try:
            v = int(float(raw))
        except (TypeError, ValueError):
            return 100
        return max(0, min(100, v))

    def lighting_cmd_for_channel(
        self,
        *,
        channel: str,
        duty: int,
        desired_on: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        is_pwm_channel = "pwm" in channel or channel in {"light_main", "main_light"}
        if not desired_on:
            if is_pwm_channel:
                return "set_pwm", {"duty": 0}
            return "set_relay", {"state": False}
        if is_pwm_channel:
            return "set_pwm", {"duty": duty}
        return "set_relay", {"state": True}
