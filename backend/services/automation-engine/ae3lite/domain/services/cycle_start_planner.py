"""CycleStartPlanner для AE3-Lite v1."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable, List, Mapping, Sequence

from ae3lite.application.dto import CommandPlan, ZoneActuatorRef, ZoneSnapshot
from ae3lite.config.errors import ConfigValidationError
from ae3lite.config.loader import load_zone_correction
from ae3lite.config.runtime_plan_builder import resolve_two_tank_runtime
from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.infrastructure.metrics import SHADOW_CONFIG_VALIDATION

_logger = logging.getLogger(__name__)


class CycleStartPlanner:
    """Строит детерминированный последовательный command plan для cycle_start."""

    SUPPORTED_SCHEMA_VERSION = 1
    _CORRECTION_PRECHECK_KEYS = ("ec", "ph_up", "ph_down")
    _SHADOW_WARNING_WINDOW_SEC = 60.0

    def __init__(self, *, monotonic_clock: Callable[[], float] | None = None) -> None:
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._shadow_warning_last_logged_at: dict[object, float] = {}

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
            return self._build_lighting_tick_plan(task=task, snapshot=snapshot)
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
        if schema_version != self.SUPPORTED_SCHEMA_VERSION:
            raise PlannerConfigurationError(f"Неподдерживаемая версия command_plans.schema_version={schema_version}")

        plans = command_plans.get("plans")
        diagnostics = plans.get("diagnostics") if isinstance(plans, Mapping) else None
        if not isinstance(diagnostics, Mapping):
            raise PlannerConfigurationError("Обязателен раздел command_plans.plans.diagnostics")

        execution = snapshot.diagnostics_execution if isinstance(snapshot.diagnostics_execution, Mapping) else {}
        workflow = str(execution.get("workflow") or "").strip().lower()
        topology = str(execution.get("topology") or "").strip().lower()
        if workflow != "cycle_start":
            raise PlannerConfigurationError(f"Неподдерживаемый diagnostics workflow для cycle_start planner: {workflow or 'empty'}")
        if not topology:
            raise PlannerConfigurationError("Для diagnostics execution обязательно указать topology")
        if topology in {"two_tank", "two_tank_drip_substrate_trays"}:
            return self._build_two_tank_plan(task=task, snapshot=snapshot, workflow=workflow, topology=topology)

        steps = diagnostics.get("steps")
        if not isinstance(steps, Sequence) or not steps:
            raise PlannerConfigurationError("command_plans.plans.diagnostics.steps должен быть непустым массивом")

        default_node_types = self._normalize_node_types(execution.get("required_node_types"))
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
        self._shadow_validate_correction(snapshot=snapshot, task=task)
        runtime = resolve_two_tank_runtime(snapshot)
        runtime = self._apply_irrigation_decision_snapshot(task=task, runtime=runtime)
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

        # Разрешить dosing actuator'ы для модуля коррекции.
        # Это опционально: если канала нет в `snapshot.actuators`, correction executor
        # выбросит `PlannerConfigurationError` уже во время выполнения, а не на этапе планирования.
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

    def _shadow_validate_correction(
        self,
        *,
        snapshot: ZoneSnapshot,
        task: AutomationTask,
    ) -> None:
        """Non-blocking validation of snapshot.correction_config against
        canonical Pydantic schema (`schemas/zone_correction.v1.json`).

        Non-blocking — result is only reported to Prometheus counter
        `ae3_shadow_config_validation_total{result, namespace}` and logged
        at WARNING on failure. Runtime currently keeps this hook in shadow mode
        rather than failing task planning.
        """
        correction_config = getattr(snapshot, "correction_config", None)
        if not isinstance(correction_config, Mapping):
            SHADOW_CONFIG_VALIDATION.labels(
                result="invalid", namespace="zone.correction",
            ).inc()
            return
        # snapshot.correction_config is the compiler-merged `resolved_config`
        # (has keys `base`, `phases`, `meta`). Validate both the base and
        # each phase — all three should match the same schema after merge.
        targets: list[tuple[str, Any]] = []
        base = correction_config.get("base")
        if isinstance(base, Mapping):
            targets.append(("base", base))
        phases = correction_config.get("phases")
        if isinstance(phases, Mapping):
            for phase_name in ("solution_fill", "tank_recirc", "irrigation"):
                phase_cfg = phases.get(phase_name)
                if isinstance(phase_cfg, Mapping):
                    targets.append((f"phases.{phase_name}", phase_cfg))
        if not targets:
            SHADOW_CONFIG_VALIDATION.labels(
                result="invalid", namespace="zone.correction",
            ).inc()
            return

        zone_id = getattr(task, "zone_id", None)
        invalid_namespaces: list[str] = []
        invalid_violations: list[dict[str, Any]] = []
        for label, payload in targets:
            try:
                load_zone_correction(
                    payload,
                    zone_id=zone_id,
                    namespace=f"zone.correction:{label}",
                )
            except ConfigValidationError as exc:
                invalid_namespaces.append(exc.namespace)
                if not invalid_violations:
                    invalid_violations = exc.errors[:20]
        if invalid_namespaces:
            self._log_shadow_validation_failure(
                zone_id=zone_id,
                invalid_namespaces=invalid_namespaces,
                violations=invalid_violations,
            )
        SHADOW_CONFIG_VALIDATION.labels(
            result="invalid" if invalid_namespaces else "ok",
            namespace="zone.correction",
        ).inc()

    def _log_shadow_validation_failure(
        self,
        *,
        zone_id: object,
        invalid_namespaces: Sequence[str],
        violations: Sequence[dict[str, Any]],
    ) -> None:
        if not invalid_namespaces:
            return
        rate_limit_key = zone_id if zone_id is not None else "__unknown_zone__"
        now = self._monotonic_clock()
        last_logged_at = self._shadow_warning_last_logged_at.get(rate_limit_key)
        if last_logged_at is not None and (now - last_logged_at) < self._SHADOW_WARNING_WINDOW_SEC:
            return

        self._shadow_warning_last_logged_at[rate_limit_key] = now
        _logger.warning(
            "ae3_shadow_config_validation_failed",
            extra={
                "zone_id": zone_id,
                "namespace": invalid_namespaces[0],
                "invalid_namespaces": tuple(invalid_namespaces[:5]),
                "invalid_count": len(invalid_namespaces),
                "violations": list(violations[:20]),
                "rate_limit_window_sec": int(self._SHADOW_WARNING_WINDOW_SEC),
            },
        )

    def _build_lighting_tick_plan(
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
        ref = self._pick_lighting_actuator(actuators)
        if ref is None:
            raise PlannerConfigurationError(
                "Для lighting_tick не найден lighting actuator channel, например light_main",
            )

        targets = snapshot.targets if isinstance(snapshot.targets, Mapping) else {}
        lighting_targets = targets.get("lighting") if isinstance(targets.get("lighting"), Mapping) else {}
        duty = self._resolve_lighting_pwm_duty(lighting_targets)
        cmd, params = self._lighting_cmd_for_channel(channel=str(ref.channel or "").strip().lower(), duty=duty)
        planned = PlannedCommand(
            step_no=1,
            node_uid=ref.node_uid,
            channel=ref.channel,
            payload={
                "name": "lighting_tick",
                "cmd": cmd,
                "params": params,
                "complete_on_ack": True,
            },
        )
        return CommandPlan(
            task_type=task.task_type,
            workflow="lighting_tick",
            topology="lighting_tick",
            steps=(planned,),
            targets=dict(targets),
            named_plans={},
            runtime=None,
        )

    def _pick_lighting_actuator(self, actuators: Sequence[ZoneActuatorRef]) -> ZoneActuatorRef | None:
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

    def _resolve_lighting_pwm_duty(self, lighting_targets: Mapping[str, Any]) -> int:
        raw = lighting_targets.get("pwm_duty") if isinstance(lighting_targets, Mapping) else None
        if raw is None:
            raw = lighting_targets.get("brightness_pct") if isinstance(lighting_targets, Mapping) else None
        try:
            v = int(float(raw))
        except (TypeError, ValueError):
            return 100
        return max(0, min(100, v))

    def _lighting_cmd_for_channel(self, *, channel: str, duty: int) -> tuple[str, dict[str, Any]]:
        if "pwm" in channel or channel in {"light_main", "main_light"}:
            return "set_pwm", {"duty": duty}
        return "set_relay", {"state": True}

    def _apply_irrigation_decision_snapshot(
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
                raise PlannerConfigurationError(f"Неоднозначное разрешение system channel для node_type={node_type}")
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
            raise PlannerConfigurationError(f"Ожидался ровно один runtime node для node_types={sorted(normalized_types)}")
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
        kind = "EC" if actuator_key.startswith("ec") else "PH"
        if not isinstance(calibration, Mapping):
            raise PlannerConfigurationError(
                f"Для насоса дозирования {kind} требуется calibration (channel={channel}, node={node_uid})",
                code=ErrorCodes.ZONE_DOSING_CALIBRATION_MISSING_CRITICAL,
            )

        # Audit F6: the old check only asserted calibration was *some* Mapping,
        # so an empty dict or one missing ``ml_per_sec`` passed preflight and
        # blew up later in ``_dose_ml_to_ms`` with a non-actionable error
        # during the first dose attempt. Fail-close at cycle_start with an
        # explicit list of missing keys so operators know exactly which field
        # to fix in pump_calibrations.
        required_keys = ("ml_per_sec",)
        missing = [key for key in required_keys if calibration.get(key) in (None, "", 0)]
        if missing:
            raise PlannerConfigurationError(
                f"Для насоса дозирования {kind} calibration не содержит обязательные поля "
                f"{missing} (channel={channel}, node={node_uid})",
                code=ErrorCodes.ZONE_DOSING_CALIBRATION_MISSING_CRITICAL,
            )

    def _resolve_correction_actuators(
        self,
        *,
        actuators: Sequence[ZoneActuatorRef],
        correction: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Разрешает ссылки на dosing actuator'ы для модуля коррекции.

        Возвращает dict с ключами `"ec"`, `"ec_actuators"`, `"ph_up"`, `"ph_down"`.
        Каждое значение — либо dict вида `{node_uid, channel, calibration}`, либо `None`
        (только если `dose_*_channel` пустой). Fail-closed:
        `dose_*_channel` обязан ссылаться на канонический физический канал
        (`pump_acid`/`pump_base`/`pump_a..d`) — legacy alias'ы больше не
        резолвятся (см. `doc_ai/01_SYSTEM/PUMP_NAMING_UNIFICATION_PLAN.md`).
        """
        def _resolve(channel_name: str, node_types: List[str]) -> Any:
            requested = str(channel_name or "").strip().lower()
            if not requested:
                return None
            try:
                actuator = self._resolve_actuator(
                    actuators=actuators,
                    requested_channel=requested,
                    node_types=node_types,
                )
            except PlannerConfigurationError as exc:
                # Ambiguous actuator resolution is always fatal — ошибка конфига.
                if "Неоднозначное разрешение actuator" in str(exc):
                    raise
                # Отсутствующий actuator на этапе планирования допустим:
                # correction-handler упадёт уже в момент дозирования (см. `_validate_required_correction_calibrations`).
                return None
            return {
                "node_uid": actuator.node_uid,
                "channel": actuator.channel,
                "calibration": dict(actuator.pump_calibration) if isinstance(actuator.pump_calibration, Mapping) else None,
            }

        ec_channel = str(correction.get("dose_ec_channel") or "").strip().lower()
        ph_up_channel = str(correction.get("dose_ph_up_channel") or "").strip().lower()
        ph_down_channel = str(correction.get("dose_ph_down_channel") or "").strip().lower()

        ec_actuators: dict[str, Any] = {}
        for actuator in actuators:
            node_type = str(actuator.node_type or "").strip().lower()
            if node_type != "ec":
                continue
            channel = str(actuator.channel or "").strip().lower()
            value = {
                "node_uid": actuator.node_uid,
                "channel": actuator.channel,
                "calibration": dict(actuator.pump_calibration) if isinstance(actuator.pump_calibration, Mapping) else None,
            }
            component = self._extract_ec_component(
                role=str(actuator.role or ""),
                pump_calibration=actuator.pump_calibration,
            )
            if component:
                ec_actuators.setdefault(component, value)
            if channel:
                ec_actuators.setdefault(channel, value)

        return {
            "ec": _resolve(ec_channel, ["ec"]),
            "ec_actuators": ec_actuators,
            "ph_up": _resolve(ph_up_channel, ["ph"]),
            "ph_down": _resolve(ph_down_channel, ["ph"]),
        }

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
                f"Не найден online actuator для requested_channel={requested_channel} node_types={sorted(normalized_types)}"
            )
        candidates.sort(key=lambda item: (item[0], item[1].node_uid, item[1].channel, item[1].node_channel_id))

        best_rank = candidates[0][0]
        equally_ranked = [item[1] for item in candidates if item[0] == best_rank]
        if len(equally_ranked) > 1:
            raise PlannerConfigurationError(
                f"Неоднозначное разрешение actuator для requested_channel={requested_channel}: "
                f"{[item.node_uid for item in equally_ranked]}"
            )
        return equally_ranked[0]
