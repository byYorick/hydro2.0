"""CorrectionHandler — 8-step PH/EC correction state machine.

Replaces CorrectionExecutor v1 by reading/writing explicit CorrectionState
fields instead of payload JSONB keys.

Protocol (per CORRECTION_CYCLE_SPEC.md):
  1. corr_activate   — activate PH/EC sensor nodes
  2. corr_wait_stable — wait for sensor stabilization
  3. corr_check      — read PH/EC observation window, decide: done / dose EC / dose PH / give up
  4. corr_dose_ec    — issue EC dose pulse
  5. corr_wait_ec    — hold + observe EC response window
  6. corr_dose_ph    — issue PH dose pulse
  7. corr_wait_ph    — hold + observe PH response window, then bump attempt → corr_check
  8. corr_deactivate — deactivate sensor nodes, return to parent stage
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.level_monitor import (
    coarse_solution_tank_level_percent,
    solution_tank_has_solution,
)
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.correction_alert_service import CorrectionAlertService
from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.decision_window_reader import (
    DecisionWindowReader,
    DecisionWindowResult,
)
from ae3lite.application.services.sensor_mode_controller import SensorModeController
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import PlannerConfigurationError, TaskExecutionError
from ae3lite.domain.services.correction_planner import CorrectionPlanner, DosePlan
from ae3lite.domain.services.correction_transition_policy import (
    CorrectionTransitionPolicy,
)
from ae3lite.domain.services.observation_analyzer import ObservationAnalyzer
from ae3lite.domain.services.pid_output_event import build_pid_output_detail
from ae3lite.infrastructure.metrics import CORRECTION_ATTEMPT, CORRECTION_CAP_IGNORED, CORRECTION_EXHAUSTED
from ae3lite.infrastructure.metrics import IRRIGATION_EC_COMPONENT_DOSE
from common.db import create_zone_event
from common.biz_alerts import send_biz_alert

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MeasurementSnapshot:
    """Immutable result of ``_read_measurements_or_interrupt``.

    Carries the validated current pH / EC readings plus the derived workflow
    readiness flag and normalized ``current_stage`` used by downstream
    success-check and routing helpers. Not a domain type — purely an internal
    plumbing record to avoid a tuple-of-four positional return.
    """

    current_ph: float
    current_ec: float
    workflow_ready: bool
    current_stage: str


@dataclass(frozen=True)
class _ObservationWindow:
    """Immutable result of ``_read_observation_window_or_interrupt``.

    Packs the ready telemetry window samples plus all the context needed
    by the finalize step (baseline, dose timing, observation config, and
    the previous PID entry). Avoids an eight-item tuple return and lets
    the finalize helper take a single argument.
    """

    samples: Any
    summary_value: float
    baseline_value: float
    last_dose_at: datetime
    observe_cfg: Mapping[str, Any]
    pid_entry: Mapping[str, Any]
    process_cfg: Mapping[str, Any]


class CorrectionHandler(BaseStageHandler):
    """Handles all ``corr_*`` steps within the correction state machine."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        planner: Optional[CorrectionPlanner] = None,
        pid_state_repository: Any = None,
        observation_analyzer: Optional[ObservationAnalyzer] = None,
        decision_window_reader: Optional[DecisionWindowReader] = None,
        transition_policy: Optional[CorrectionTransitionPolicy] = None,
        event_logger: Optional[CorrectionEventLogger] = None,
        sensor_mode_controller: Optional[SensorModeController] = None,
        alert_service: Optional[CorrectionAlertService] = None,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
        )
        self._planner = planner or CorrectionPlanner()
        self._pid_state_repository = pid_state_repository
        self._observation_analyzer = observation_analyzer or ObservationAnalyzer()
        self._decision_window_reader = (
            decision_window_reader or DecisionWindowReader(runtime_monitor=runtime_monitor)
        )
        self._transition_policy = transition_policy or CorrectionTransitionPolicy()
        # Wrap create_zone_event in a lambda that resolves the symbol lazily
        # from this module's globals. Existing handler tests monkeypatch
        # ``ae3lite.application.handlers.correction.create_zone_event`` to
        # capture event payloads; a direct capture of the module-level symbol
        # at __init__ time would hide those patches from the logger.
        self._event_logger = event_logger or CorrectionEventLogger(
            create_event_fn=lambda zone_id, event_type, payload: create_zone_event(
                zone_id, event_type, payload,
            ),
            probe_snapshot_context_fn=self._probe_snapshot_context,
        )
        self._sensor_mode_controller = sensor_mode_controller or SensorModeController(
            command_gateway=command_gateway,
            event_logger=self._event_logger,
        )
        # Lazy closure over module-level send_biz_alert so existing handler
        # tests that monkeypatch ``ae3lite.application.handlers.correction.send_biz_alert``
        # remain observable (same trick as for create_zone_event above).
        self._alert_service = alert_service or CorrectionAlertService(
            alert_sink_fn=lambda **kwargs: send_biz_alert(**kwargs),
        )

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        corr = task.correction
        if corr is None:
            raise TaskExecutionError(
                "corr_state_missing",
                f"Task {task.id} in correction stage but correction state is None",
            )

        solution_fill_completion_outcome = await self._interrupt_for_solution_fill_completion(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
        )
        if solution_fill_completion_outcome is not None:
            return solution_fill_completion_outcome

        deadline_outcome = await self._interrupt_for_stage_deadline(task=task, plan=plan, corr=corr, now=now)
        if deadline_outcome is not None:
            return deadline_outcome

        step = corr.corr_step
        if step not in {"corr_activate", "corr_wait_stable", "corr_deactivate", "corr_done"}:
            imminent_probe_outcome = self._interrupt_for_imminent_flow_probe_deadline(
                task=task,
                plan=plan,
                now=now,
            )
            if imminent_probe_outcome is not None:
                return imminent_probe_outcome
            await self._assert_flow_path_active(task=task, plan=plan, now=now)
        if step == "corr_activate":
            return await self._run_activate(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_wait_stable":
            return self._run_wait_stable(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_check":
            return await self._run_check(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_dose_ec":
            return await self._run_dose_ec(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_wait_ec":
            return await self._run_wait_ec(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_dose_ph":
            return await self._run_dose_ph(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_wait_ph":
            return await self._run_wait_ph(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_deactivate":
            return await self._run_deactivate(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_done":
            return self._run_done(corr=corr)

        raise TaskExecutionError(
            "ae3_unknown_corr_step", f"Неизвестный correction step={step!r}",
        )

    # ── Step handlers ───────────────────────────────────────────────

    async def _run_activate(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        sensor_cmds = self._sensor_mode_controller.build_commands(
            plan=plan, cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        current_task = task
        if sensor_cmds:
            result = await self._command_gateway.run_batch(
                task=current_task, commands=sensor_cmds, now=now,
            )
            if not result["success"]:
                raise TaskExecutionError(
                    str(result["error_code"]), str(result["error_message"]),
                )
            current_task = result.get("task") or current_task
        next_corr = replace(corr, corr_step="corr_wait_stable")
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=corr.stabilization_sec,
            task_override=current_task if current_task is not task else None,
        )

    def _run_wait_stable(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        next_corr = replace(corr, corr_step="corr_check")
        return self._enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
        )

    async def _interrupt_for_solution_fill_completion(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        if str(task.current_stage).strip().lower() != "solution_fill_check":
            return None

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        try:
            solution_max = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["solution_max_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_solution_level_unavailable",
                stale_error="two_tank_solution_level_stale",
            )
        except TaskExecutionError:
            return None

        if not bool(solution_max.get("is_triggered")):
            return None

        try:
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="solution_min_sensor_labels",
                min_unavailable_error="two_tank_solution_min_level_unavailable",
                min_stale_error="two_tank_solution_min_level_stale",
            )
        except TaskExecutionError:
            return None

        workflow_ready = await self._workflow_ready_reached(task=task, plan=plan, now=now)
        next_stage = "solution_fill_stop_to_ready" if workflow_ready else "solution_fill_stop_to_prepare"
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_INTERRUPTED_STAGE_COMPLETE",
            task=task,
            corr=corr,
            payload={
                "next_stage": next_stage,
                "targets_reached": workflow_ready,
                "reason": "solution_tank_full",
            },
        )
        _logger.info(
            "zone %s: solution fill completed during correction; interrupting corr_step=%s -> %s",
            task.zone_id,
            corr.corr_step,
            next_stage,
        )
        return StageOutcome(kind="transition", next_stage=next_stage)

    async def _run_check(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        max_age = int(runtime.get("telemetry_max_age_sec", 300))
        target_ph = float(runtime["target_ph"])
        target_ec = self._effective_ec_target(task=task, runtime=runtime)
        tolerance = self._prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_tol_pct = float(tolerance.get("ph_pct", 15.0))
        ec_tol_pct = float(tolerance.get("ec_pct", 25.0))
        correction_cfg = self._correction_config(plan=plan, task=task)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        pid_state = runtime.get("pid_state") if isinstance(runtime.get("pid_state"), Mapping) else {}
        enforce_attempt_caps = self._enforce_attempt_caps(task=task)

        if self._should_log_limit_policy(task=task, corr=corr):
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_LIMIT_POLICY_APPLIED",
                task=task,
                corr=corr,
                payload={
                    "attempt_caps_enforced": False,
                    "stop_conditions": ["no_effect", "stage_timeout"],
                    "stage_timeout_sec": runtime.get("solution_fill_timeout_sec"),
                    "policy": "fill_continuous_until_no_effect_or_timeout",
                },
            )
            corr = replace(corr, limit_policy_logged=True)

        measurement_or_interrupt = await self._read_measurements_or_interrupt(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            runtime=runtime,
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_state=pid_state,
            target_ph=target_ph,
            target_ec=target_ec,
            max_age=max_age,
        )
        if isinstance(measurement_or_interrupt, StageOutcome):
            return measurement_or_interrupt
        measurement = measurement_or_interrupt
        current_ph = measurement.current_ph
        current_ec = measurement.current_ec
        workflow_ready = measurement.workflow_ready
        current_stage = measurement.current_stage

        correction_targets_reached = self._planner.is_within_tolerance(
            current_ph=current_ph, current_ec=current_ec,
            target_ph=target_ph, target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
            ph_min=self._coerce_float(runtime.get("target_ph_min")),
            ph_max=self._coerce_float(runtime.get("target_ph_max")),
            ec_min=self._effective_ec_min(task=task, runtime=runtime),
            ec_max=self._effective_ec_max(task=task, runtime=runtime),
        )
        success_reached = (
            correction_targets_reached and workflow_ready
            if current_stage == "prepare_recirculation_check"
            else correction_targets_reached
        )
        if success_reached:
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_COMPLETE",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                    "workflow_ready": workflow_ready,
                },
            )
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        if enforce_attempt_caps and corr.attempt >= corr.max_attempts:
            return await self._correction_exhausted(task=task, plan=plan, corr=corr)
        if not enforce_attempt_caps and corr.attempt >= corr.max_attempts:
            await self._log_attempt_cap_ignored(
                task=task,
                corr=corr,
                cap_type="overall",
                current_value=corr.attempt,
                limit_value=corr.max_attempts,
            )

        # Build dose plan. PlannerConfigurationError indicates a fail-closed
        # config issue (missing process gain, unsupported multi_sequential
        # permutation, calibration out of range, etc.) — translate it to a
        # correction-specific TaskExecutionError so execute_task maps it to
        # a typed failure instead of an anonymous Ae3LiteError surface.
        actuators = self._resolve_actuators(runtime=runtime, task=task, plan=plan)
        try:
            dose_plan = self._planner.build_dose_plan(
                current_ph=current_ph, current_ec=current_ec,
                target_ph=target_ph, target_ec=target_ec,
                ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
                correction_config=correction_cfg,
                workflow_phase=task.workflow.workflow_phase,
                process_calibrations=runtime.get("process_calibrations"),
                ec_component_policy=correction_cfg.get("ec_component_policy"),
                pid_state=pid_state,
                pid_configs=runtime.get("pid_configs"),
                now=now,
                ph_min=self._coerce_float(runtime.get("target_ph_min")),
                ph_max=self._coerce_float(runtime.get("target_ph_max")),
                ec_min=self._effective_ec_min(task=task, runtime=runtime),
                ec_max=self._effective_ec_max(task=task, runtime=runtime),
                ec_actuator=actuators.get("ec"),
                ec_actuators=actuators.get("ec_actuators"),
                ph_up_actuator=actuators.get("ph_up"),
                ph_down_actuator=actuators.get("ph_down"),
            )
        except PlannerConfigurationError as exc:
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_PLANNER_CONFIG_INVALID",
                task=task,
                corr=corr,
                payload={
                    "reason": str(exc),
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                },
            )
            raise TaskExecutionError(
                "corr_planner_config_invalid",
                f"CorrectionPlanner config invalid: {exc}",
            ) from exc

        return await self._finalize_dose_plan_routing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            dose_plan=dose_plan,
            runtime=runtime,
            pid_state=pid_state,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            current_stage=current_stage,
            workflow_ready=workflow_ready,
            enforce_attempt_caps=enforce_attempt_caps,
        )

    # ── _run_check helpers (B1 decomposition) ──────────────────────────

    async def _read_measurements_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        runtime: Mapping[str, Any],
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_state: Mapping[str, Any],
        target_ph: float,
        target_ec: float,
        max_age: int,
    ) -> _MeasurementSnapshot | StageOutcome:
        """Read current pH/EC and validate the window, or return an interrupt.

        Pipeline steps (any one of them can short-circuit with a StageOutcome):
          1. ``wait_until`` cooldown — if the previous step scheduled a wait
             that has not elapsed yet, go back to sleep.
          2. Read PH and EC decision windows via ``DecisionWindowReader``.
             Stale telemetry becomes a ``CORRECTION_SKIPPED_FRESHNESS`` event
             + retry; non-ready window becomes ``CORRECTION_SKIPPED_WINDOW_NOT_READY``
             (or a sensor-mode reactivation via ``SensorModeController``).
          3. Guard against non-finite values (sensor glitch → retry).
          4. Read the solution-min level sensor and bail if the tank is empty
             (``CORRECTION_SKIPPED_WATER_LEVEL``).

        Returns a ``_MeasurementSnapshot`` if all checks pass, otherwise a
        ``StageOutcome`` the handler returns directly.
        """
        corr_wait_until = self._normalize_timestamp(corr.wait_until)
        normalized_now = self._normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

        ph_cfg = self._observation_config(
            kind="ph",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=pid_state.get("ph") if isinstance(pid_state.get("ph"), Mapping) else None,
        )
        ec_cfg = self._observation_config(
            kind="ec",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=pid_state.get("ec") if isinstance(pid_state.get("ec"), Mapping) else None,
        )
        try:
            ph = await self._decision_window_reader.read(
                zone_id=task.zone_id,
                sensor_type="PH",
                telemetry_max_age_sec=max_age,
                config=ph_cfg,
                now=now,
            )
            ec = await self._decision_window_reader.read(
                zone_id=task.zone_id,
                sensor_type="EC",
                telemetry_max_age_sec=max_age,
                config=ec_cfg,
                now=now,
            )
        except TaskExecutionError as exc:
            if exc.code != "corr_telemetry_stale":
                raise
            retry_delay_sec = self._correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="telemetry_stale_retry_sec",
                default=30.0,
            )
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_FRESHNESS",
                task=task,
                corr=corr,
                payload={
                    "sensor_scope": "decision_window",
                    "reason": str(exc),
                    "retry_after_sec": retry_delay_sec,
                    "telemetry_max_age_sec": max_age,
                },
            )
            _logger.warning(
                "zone %s: телеметрия устарела во время correction check; повтор через %.1f с",
                task.zone_id,
                retry_delay_sec,
            )
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )
        if not ph.ready or not ec.ready:
            reactivation_outcome = await self._maybe_reactivate_sensor_mode_after_empty_window(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                ph=ph,
                ec=ec,
            )
            if reactivation_outcome is not None:
                return reactivation_outcome
            msg = self._decision_window_reader.format_error(ph=ph, ec=ec)
            retry_delay_sec = self._decision_window_reader.retry_delay_sec(
                correction_cfg=correction_cfg,
                ph=ph,
                ec=ec,
            )
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                task=task,
                corr=corr,
                payload={
                    "sensor_scope": "decision_window",
                    "reason": msg,
                    "retry_after_sec": retry_delay_sec,
                    "ph_reason": ph.reason,
                    "ph_sample_count": ph.sample_count,
                    "ph_slope": ph.slope,
                    "ph_window_min_samples": ph.window_min_samples,
                    "ph_telemetry_period_sec": ph.telemetry_period_sec,
                    "ph_latest_sample_ts": self._serialize_metric_ts(ph.latest_sample_ts),
                    "ph_since_ts": self._serialize_metric_ts(ph.since_ts),
                    "ec_reason": ec.reason,
                    "ec_sample_count": ec.sample_count,
                    "ec_slope": ec.slope,
                    "ec_window_min_samples": ec.window_min_samples,
                    "ec_telemetry_period_sec": ec.telemetry_period_sec,
                    "ec_latest_sample_ts": self._serialize_metric_ts(ec.latest_sample_ts),
                    "ec_since_ts": self._serialize_metric_ts(ec.since_ts),
                },
            )
            _logger.warning("zone %s: %s, повтор через %.1f с", task.zone_id, msg, retry_delay_sec)
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        current_ph = float(ph.value)
        current_ec = float(ec.value)
        workflow_ready = self._workflow_ready_values_match(
            task=task,
            runtime=runtime,
            current_ph=current_ph,
            current_ec=current_ec,
        )
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()

        if not math.isfinite(current_ph) or not math.isfinite(current_ec):
            retry_delay_sec = self._correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="decision_window_retry_sec",
                default=30.0,
            )
            _logger.warning(
                "zone %s: некорректное telemetry value (ph=%s, ec=%s); повтор через %.1f с",
                task.zone_id, current_ph, current_ec, retry_delay_sec,
            )
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        solution_min = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["solution_min_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=max_age,
            unavailable_error="two_tank_solution_min_level_unavailable",
            stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=0.25,
            prefer_probe_snapshot=True,
        )
        if not solution_tank_has_solution(solution_min):
            retry_delay_sec = self._correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="low_water_retry_sec",
                default=60.0,
            )
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WATER_LEVEL",
                task=task,
                corr=corr,
                payload={
                    "water_level_pct": float(
                        coarse_solution_tank_level_percent(
                            solution_max_triggered=None,
                            solution_min_triggered=bool(solution_min.get("is_triggered")),
                        )
                        or 0
                    ),
                    "retry_after_sec": retry_delay_sec,
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                },
            )
            _logger.warning(
                "zone %s: water level %.0f%% is below threshold; skipping correction for %.1fs",
                task.zone_id,
                float(
                    coarse_solution_tank_level_percent(
                        solution_max_triggered=None,
                        solution_min_triggered=bool(solution_min.get("is_triggered")),
                    )
                    or 0
                ),
                retry_delay_sec,
            )
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        return _MeasurementSnapshot(
            current_ph=current_ph,
            current_ec=current_ec,
            workflow_ready=workflow_ready,
            current_stage=current_stage,
        )

    async def _finalize_dose_plan_routing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        dose_plan: DosePlan,
        runtime: Mapping[str, Any],
        pid_state: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        current_stage: str,
        workflow_ready: bool,
        enforce_attempt_caps: bool,
    ) -> StageOutcome:
        """Persist PID state, route a built ``DosePlan`` into the next FSM step.

        Handles the post-planner tail of ``_run_check``:
        * persist PID state updates
        * log deferred action (if planner requested it)
        * handle "no dose needed" (cooldown / dead zone / discarded)
        * enforce per-direction attempt caps
        * save the dose plan into the correction state
        * decide priority (pending_ph / ec_first / ph_only)
        * log ``CORRECTION_DECISION_MADE`` + emit ``PID_OUTPUT`` event
        * return the ``enter_correction`` StageOutcome

        Extracted from ``_run_check`` as part of the B1 God-Object breakdown.
        The split cut ``_run_check`` from 559 → ~350 LOC while keeping the
        handler as orchestrator (no new class — just a cohesive private
        method that tests exercise end-to-end through handler fixtures).
        """
        # Persist updated PID state so the controller has memory across attempts.
        await self._persist_pid_state_updates(
            zone_id=task.zone_id, updates=dose_plan.pid_state_updates, now=now,
        )

        if dose_plan.deferred_action:
            selected_action = "ec" if dose_plan.needs_ec else ("ph_up" if dose_plan.needs_ph_up else "ph_down")
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_ACTION_DEFERRED",
                task=task,
                corr=corr,
                payload={
                    "selected_action": selected_action,
                    "deferred_action": dose_plan.deferred_action,
                    "reason": dose_plan.deferred_reason,
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                    **(
                        dict(dose_plan.deferred_details)
                        if isinstance(dose_plan.deferred_details, Mapping)
                        else {}
                    ),
                },
            )

        if not dose_plan.needs_any and dose_plan.retry_after_sec:
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_COOLDOWN",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    "retry_after_sec": dose_plan.retry_after_sec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                },
            )
            next_corr = replace(corr, corr_step="corr_check")
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=next_corr,
                now=now,
                due_delay_sec=dose_plan.retry_after_sec,
            )

        if not dose_plan.needs_any:
            if dose_plan.dose_discarded_reason:
                await self._log_correction_event(
                    zone_id=task.zone_id,
                    event_type="CORRECTION_SKIPPED_DOSE_DISCARDED",
                    task=task,
                    corr=corr,
                    payload={
                        "current_ph": current_ph, "current_ec": current_ec,
                        "target_ph": target_ph, "target_ec": target_ec,
                        "reason": dose_plan.dose_discarded_reason,
                        **(dict(dose_plan.dose_discarded_details) if isinstance(dose_plan.dose_discarded_details, Mapping) else {}),
                        "target_ph_min": runtime.get("target_ph_min"),
                        "target_ph_max": runtime.get("target_ph_max"),
                        "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                        "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                    },
                )
            if current_stage == "prepare_recirculation_check" and not workflow_ready:
                next_corr = replace(corr, corr_step="corr_check")
                return self._enter_correction_after_delay_or_interrupt(
                    task=task,
                    plan=plan,
                    corr=next_corr,
                    now=now,
                    due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
                )
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_DEAD_ZONE",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    **(dict(dose_plan.dead_zone_details) if isinstance(dose_plan.dead_zone_details, Mapping) else {}),
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                },
            )
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        # Per-direction attempt cap enforcement (EC + pH separately).
        if enforce_attempt_caps:
            if dose_plan.needs_ec and corr.ec_attempt >= corr.ec_max_attempts:
                return await self._correction_exhausted(task=task, plan=plan, corr=corr)
            if (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and corr.ph_attempt >= corr.ph_max_attempts:
                return await self._correction_exhausted(task=task, plan=plan, corr=corr)
        else:
            if dose_plan.needs_ec and corr.ec_attempt >= corr.ec_max_attempts:
                await self._log_attempt_cap_ignored(
                    task=task,
                    corr=corr,
                    cap_type="ec",
                    current_value=corr.ec_attempt,
                    limit_value=corr.ec_max_attempts,
                )
            if (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and corr.ph_attempt >= corr.ph_max_attempts:
                await self._log_attempt_cap_ignored(
                    task=task,
                    corr=corr,
                    cap_type="ph",
                    current_value=corr.ph_attempt,
                    limit_value=corr.ph_max_attempts,
                )

        # Save dose plan into correction state.
        ec_dose_sequence_json: str | None = None
        if dose_plan.ec_dose_sequence:
            ec_dose_sequence_json = json.dumps(
                [
                    {
                        "component": s.component,
                        "node_uid": s.node_uid,
                        "channel": s.channel,
                        "amount_ml": s.amount_ml,
                        "duration_ms": s.duration_ms,
                    }
                    for s in dose_plan.ec_dose_sequence
                ],
                separators=(",", ":"),
            )
        next_corr = replace(
            corr,
            needs_ec=dose_plan.needs_ec,
            ec_node_uid=dose_plan.ec_node_uid,
            ec_channel=dose_plan.ec_channel,
            ec_duration_ms=dose_plan.ec_duration_ms,
            ec_component=dose_plan.ec_component or None,
            ec_amount_ml=dose_plan.ec_amount_ml if dose_plan.ec_amount_ml else None,
            ec_dose_sequence_json=ec_dose_sequence_json,
            ec_current_seq_index=0,
            needs_ph_up=dose_plan.needs_ph_up,
            needs_ph_down=dose_plan.needs_ph_down,
            ph_node_uid=dose_plan.ph_node_uid,
            ph_channel=dose_plan.ph_channel,
            ph_duration_ms=dose_plan.ph_duration_ms,
            ph_amount_ml=dose_plan.ph_amount_ml if dose_plan.ph_amount_ml else None,
        )

        # Pick direction. When the previous observation window left a pending
        # pH dose (prioritize_pending_ph), we must honour it before EC so we
        # don't invalidate the EC observation by shifting pH mid-window.
        prioritize_pending_ph = (
            (corr.needs_ph_up or corr.needs_ph_down)
            and (dose_plan.needs_ph_up or dose_plan.needs_ph_down)
        )
        selected_action: str | None = None
        decision_reason: str | None = None
        if prioritize_pending_ph:
            next_corr = replace(next_corr, corr_step="corr_dose_ph")
            selected_action = "ph_up" if dose_plan.needs_ph_up else "ph_down"
            decision_reason = "prioritize_pending_ph_after_ec_observe"
        elif dose_plan.needs_ec:
            next_corr = replace(next_corr, corr_step="corr_dose_ec")
            selected_action = "ec"
            if dose_plan.needs_ph_up or dose_plan.needs_ph_down:
                decision_reason = "ec_first_in_window"
            else:
                decision_reason = "ec_only_needed"
        elif dose_plan.needs_ph_up or dose_plan.needs_ph_down:
            next_corr = replace(next_corr, corr_step="corr_dose_ph")
            selected_action = "ph_up" if dose_plan.needs_ph_up else "ph_down"
            decision_reason = "ph_raise_needed" if dose_plan.needs_ph_up else "ph_lower_needed"
        else:
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_DECISION_MADE",
            task=task,
            corr=next_corr,
            payload={
                "selected_action": selected_action,
                "decision_reason": decision_reason,
                "current_ph": current_ph,
                "current_ec": current_ec,
                "target_ph": target_ph,
                "target_ec": target_ec,
                "target_ph_min": runtime.get("target_ph_min"),
                "target_ph_max": runtime.get("target_ph_max"),
                "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                "needs_ec": dose_plan.needs_ec,
                "needs_ph_up": dose_plan.needs_ph_up,
                "needs_ph_down": dose_plan.needs_ph_down,
                "pending_ph_from_previous_step": bool(corr.needs_ph_up or corr.needs_ph_down),
                **(
                    dict(dose_plan.dead_zone_details)
                    if isinstance(dose_plan.dead_zone_details, Mapping)
                    else {}
                ),
            },
        )
        await self._maybe_emit_pid_output_zone_event(
            zone_id=int(task.zone_id),
            corr_step=str(next_corr.corr_step),
            dose_plan=dose_plan,
            pid_state_before=pid_state,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            now=now,
        )
        return self._enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
        )

    async def _run_dose_ec(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        seq: list[dict[str, Any]] = []
        if corr.ec_dose_sequence_json:
            try:
                raw = json.loads(corr.ec_dose_sequence_json)
                if not isinstance(raw, list):
                    raise TaskExecutionError("corr_dose_ec_bad_sequence", "EC dose sequence JSON должен быть списком")
                seq = list(raw)
            except Exception as exc:
                if isinstance(exc, TaskExecutionError):
                    raise
                raise TaskExecutionError("corr_dose_ec_bad_sequence", "EC dose sequence JSON некорректен")
        if seq:
            for item in seq:
                if not isinstance(item, dict):
                    raise TaskExecutionError("corr_dose_ec_bad_sequence", "Элемент EC dose sequence должен быть объектом")
                if not str(item.get("node_uid") or "").strip():
                    raise TaskExecutionError("corr_dose_ec_bad_sequence", "В EC dose sequence отсутствует node_uid")
                if not str(item.get("channel") or "").strip():
                    raise TaskExecutionError("corr_dose_ec_bad_sequence", "В EC dose sequence отсутствует channel")
                try:
                    ml = float(item.get("amount_ml"))
                except (TypeError, ValueError):
                    ml = 0.0
                if ml <= 0:
                    raise TaskExecutionError("corr_dose_ec_bad_sequence", "В EC dose sequence значение amount_ml должно быть > 0")
        else:
            if (
                not corr.ec_node_uid
                or not corr.ec_channel
                or not corr.ec_duration_ms
                or corr.ec_amount_ml is None
                or corr.ec_amount_ml <= 0.0
            ):
                raise TaskExecutionError(
                    "corr_dose_ec_missing_plan",
                    (
                        "Отсутствует EC dose plan "
                        f"(node={corr.ec_node_uid}, ch={corr.ec_channel}, ms={corr.ec_duration_ms}, "
                        f"ml={corr.ec_amount_ml})"
                    ),
                )
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step="corr_dose_ec").inc()
        current_task = await self._ensure_sensor_mode_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=corr.ec_node_uid,
            failed_channel=corr.ec_channel,
            retry_cmd="dose",
        )
        is_parallel = str(getattr(corr, "ec_component", "") or "").strip().lower() == "multi_parallel"
        if seq and is_parallel:
            # multi_parallel: отправляем ВСЕ dose-команды за один batch.
            # Все компоненты (Ca, Mg, Micro) дозируются одновременно.
            batch_cmds: list[PlannedCommand] = []
            for idx, item in enumerate(seq):
                comp = str(item.get("component") or "").strip().lower()
                if comp:
                    IRRIGATION_EC_COMPONENT_DOSE.labels(topology=task.topology, component=comp).inc()
                batch_cmds.append(PlannedCommand(
                    step_no=idx + 1,
                    node_uid=str(item["node_uid"]),
                    channel=str(item["channel"]),
                    payload={"cmd": "dose", "params": {"ml": float(item["amount_ml"])}},
                ))
            result = await self._command_gateway.run_batch(task=current_task, commands=tuple(batch_cmds), now=now)
            if not result["success"]:
                raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
            current_task = result.get("task") or current_task
            corr = replace(corr, ec_current_seq_index=len(seq))
        elif seq:
            # multi_sequential: отправляем по ОДНОМУ компоненту за вызов,
            # возобновляясь через ec_current_seq_index.
            start_idx = int(getattr(corr, "ec_current_seq_index", 0) or 0)
            if start_idx < 0:
                start_idx = 0
            if start_idx >= len(seq):
                start_idx = len(seq)

            if start_idx < len(seq):
                item = seq[start_idx]
                comp = str(item.get("component") or "").strip().lower()
                if comp:
                    IRRIGATION_EC_COMPONENT_DOSE.labels(topology=task.topology, component=comp).inc()
                cmd = PlannedCommand(
                    step_no=start_idx + 1,
                    node_uid=str(item["node_uid"]),
                    channel=str(item["channel"]),
                    payload={"cmd": "dose", "params": {"ml": float(item["amount_ml"])}},
                )
                result = await self._command_gateway.run_batch(task=current_task, commands=(cmd,), now=now)
                if not result["success"]:
                    raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
                current_task = result.get("task") or current_task

                next_idx = start_idx + 1
                if next_idx < len(seq):
                    # Persist progress and immediately continue with the next component.
                    return StageOutcome(
                        kind="enter_correction",
                        correction=replace(corr, ec_current_seq_index=next_idx),
                        due_delay_sec=0,
                        task_override=current_task if current_task is not task else None,
                    )

                # Sequence complete; continue with standard post-dose hold window below.
                corr = replace(corr, ec_current_seq_index=next_idx)
            else:
                # Already complete (resume after crash) — treat as done and proceed.
                corr = replace(corr, ec_current_seq_index=start_idx)
        else:
            cmd = PlannedCommand(
                step_no=1,
                node_uid=corr.ec_node_uid,
                channel=corr.ec_channel,
                payload={"cmd": "dose", "params": {"ml": corr.ec_amount_ml}},
            )
            result = await self._command_gateway.run_batch(task=current_task, commands=(cmd,), now=now)
            if not result["success"]:
                raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
            current_task = result.get("task") or current_task

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        # Read last_measured_value from DB (written by _persist_pid_state_updates in _run_check)
        # to avoid using the stale plan.runtime pid_state snapshot.
        current_ec: Optional[float] = None
        if self._pid_state_repository is not None:
            try:
                current_ec = await self._pid_state_repository.read_measured_value(
                    zone_id=task.zone_id, pid_type="ec"
                )
            except Exception:
                _logger.debug("Не удалось прочитать EC pid_state для логирования события", exc_info=True)
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="EC_DOSING",
            task=task,
            corr=replace(corr, ec_attempt=corr.ec_attempt + 1),
            payload={
                "node_uid": corr.ec_node_uid,
                "channel": corr.ec_channel,
                "duration_ms": corr.ec_duration_ms,
                "amount_ml": corr.ec_amount_ml,
                "dose_sequence": seq or None,
                "seq_index": int(getattr(corr, "ec_current_seq_index", 0) or 0) if seq else None,
                "observe_seq": self._observe_seq(corr=corr, pid_type="ec", after_dose=True),
                "ec_component": corr.ec_component,
                "current_ec": current_ec,
                "target_ec": self._effective_ec_target(task=task, runtime=runtime),
                "target_ec_min": self._effective_ec_min(task=task, runtime=runtime),
                "target_ec_max": self._effective_ec_max(task=task, runtime=runtime),
                "source": "correction_handler",
            },
        )
        if seq and str(getattr(task.workflow, "workflow_phase", "") or "").strip().lower() == "irrigating":
            try:
                await create_zone_event(
                    int(task.zone_id),
                    "IRRIGATION_EC_MULTI_DOSE",
                    with_runtime_event_contract({
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "topology": str(getattr(task, "topology", "") or ""),
                        "dose_sequence": seq,
                    }),
                )
            except Exception:
                _logger.debug("Не удалось создать zone event IRRIGATION_EC_MULTI_DOSE", exc_info=True)

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._correction_config(plan=plan, task=task)
        observe_cfg = self._observation_config(
            kind="ec",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=runtime.get("pid_state", {}).get("ec") if isinstance(runtime.get("pid_state"), Mapping) else None,
        )
        wait_until = now + timedelta(seconds=int(observe_cfg["hold_window_sec"]))
        await self._persist_pid_state_updates(
            zone_id=task.zone_id,
            now=now,
            updates={
                "ec": {
                    "hold_until": wait_until,
                    "last_output_ms": corr.ec_duration_ms,
                    "last_correction_kind": "ec",
                },
                "ph": {
                    "hold_until": wait_until,
                    "feedforward_bias": float(self._expected_cross_coupling_ph(corr=corr, process_cfg=process_cfg)),
                    "last_correction_kind": "ec",
                },
            },
        )
        next_corr = replace(
            corr,
            corr_step="corr_wait_ec",
            ec_attempt=corr.ec_attempt + 1,
            wait_until=wait_until,
        )
        return self._enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=int(observe_cfg["hold_window_sec"]),
            task_override=current_task if current_task is not task else None,
        )

    async def _run_wait_ec(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        return await self._run_wait_observe(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type="ec",
            sensor_type="EC",
        )

    async def _run_dose_ph(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        if (
            not corr.ph_node_uid
            or not corr.ph_channel
            or not corr.ph_duration_ms
            or corr.ph_amount_ml is None
            or corr.ph_amount_ml <= 0.0
        ):
            raise TaskExecutionError(
                "corr_dose_ph_missing_plan",
                (
                    "PH dose plan missing "
                    f"(node={corr.ph_node_uid}, ch={corr.ph_channel}, ms={corr.ph_duration_ms}, "
                    f"ml={corr.ph_amount_ml})"
                ),
            )
        ph_step = "corr_dose_ph_up" if corr.needs_ph_up else "corr_dose_ph_down"
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step=ph_step).inc()
        current_task = await self._ensure_sensor_mode_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=corr.ph_node_uid,
            failed_channel=corr.ph_channel,
            retry_cmd="dose",
        )
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ph_node_uid,
            channel=corr.ph_channel,
            payload={"cmd": "dose", "params": {"ml": corr.ph_amount_ml}},
        )
        result = await self._command_gateway.run_batch(task=current_task, commands=(cmd,), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
        current_task = result.get("task") or current_task

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        # Read last_measured_value from DB (written by _persist_pid_state_updates in _run_check)
        # to avoid using the stale plan.runtime pid_state snapshot.
        current_ph: Optional[float] = None
        if self._pid_state_repository is not None:
            try:
                current_ph = await self._pid_state_repository.read_measured_value(
                    zone_id=task.zone_id, pid_type="ph"
                )
            except Exception:
                _logger.debug("Не удалось прочитать PH pid_state для логирования события", exc_info=True)
        ph_direction = "up" if corr.needs_ph_up else "down"
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="PH_CORRECTED",
            task=task,
            corr=replace(corr, ph_attempt=corr.ph_attempt + 1),
            payload={
                "node_uid": corr.ph_node_uid,
                "channel": corr.ph_channel,
                "duration_ms": corr.ph_duration_ms,
                "amount_ml": corr.ph_amount_ml,
                "observe_seq": self._observe_seq(corr=corr, pid_type="ph", after_dose=True),
                "direction": ph_direction,
                "current_ph": current_ph,
                "target_ph": runtime.get("target_ph"),
                "target_ph_min": runtime.get("target_ph_min"),
                "target_ph_max": runtime.get("target_ph_max"),
                "source": "correction_handler",
            },
        )

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._correction_config(plan=plan, task=task)
        observe_cfg = self._observation_config(
            kind="ph",
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=runtime.get("pid_state", {}).get("ph") if isinstance(runtime.get("pid_state"), Mapping) else None,
        )
        wait_until = now + timedelta(seconds=int(observe_cfg["hold_window_sec"]))
        # Audit B5 fix: explicitly zero out the cross-coupling feedforward_bias
        # the previous EC dose may have left in this pH row. Without this
        # reset the bias would linger until the next EC observation clears
        # it, and the planner's simplified "bias != 0" predicate would
        # incorrectly apply a stale EC→pH correction to the next pH tick.
        await self._persist_pid_state_updates(
            zone_id=task.zone_id,
            now=now,
            updates={
                "ph": {
                    "hold_until": wait_until,
                    "last_output_ms": corr.ph_duration_ms,
                    "last_correction_kind": "ph_up" if corr.needs_ph_up else "ph_down",
                    "feedforward_bias": 0.0,
                },
            },
        )
        next_corr = replace(corr, corr_step="corr_wait_ph", ph_attempt=corr.ph_attempt + 1, wait_until=wait_until)
        return self._enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=int(observe_cfg["hold_window_sec"]),
            task_override=current_task if current_task is not task else None,
        )

    async def _run_wait_ph(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        return await self._run_wait_observe(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type="ph",
            sensor_type="PH",
        )

    async def _run_deactivate(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        current_task = task
        if corr.activated_here:
            sensor_cmds = self._sensor_mode_controller.build_commands(
                plan=plan, cmd="deactivate_sensor_mode", params={},
            )
            if sensor_cmds:
                result = await self._command_gateway.run_batch(
                    task=current_task, commands=sensor_cmds, now=now,
                )
                if not result["success"]:
                    raise TaskExecutionError(
                        str(result["error_code"]), str(result["error_message"]),
                    )
                current_task = result.get("task") or current_task

        next_corr = replace(corr, corr_step="corr_done")
        return self._enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
            task_override=current_task if current_task is not task else None,
        )

    def _run_done(self, *, corr: CorrectionState) -> StageOutcome:
        success = corr.outcome_success if corr.outcome_success is not None else False
        next_stage = corr.return_stage_success if success else corr.return_stage_fail
        return StageOutcome(kind="exit_correction", next_stage=next_stage, correction=corr)

    # ── Helpers ─────────────────────────────────────────────────────

    async def _ensure_sensor_mode_active_for_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        failed_node_uid: str | None,
        failed_channel: str | None,
        retry_cmd: str,
    ) -> Any:
        return await self._sensor_mode_controller.ensure_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=failed_node_uid,
            failed_channel=failed_channel,
            retry_cmd=retry_cmd,
        )

    async def _assert_flow_path_active(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        expected = self._expected_flow_path_state(current_stage=str(task.current_stage or ""))
        if expected is None:
            return
        await self._probe_irr_state(
            task=task,
            plan=plan,
            now=now,
            expected=expected,
        )

    def _expected_flow_path_state(self, *, current_stage: str) -> Mapping[str, bool] | None:
        stage = str(current_stage or "").strip().lower()
        if stage == "solution_fill_check":
            return {
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            }
        if stage == "prepare_recirculation_check":
            return {
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            }
        return None

    async def _maybe_reactivate_sensor_mode_after_empty_window(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        ph: DecisionWindowResult,
        ec: DecisionWindowResult,
    ) -> StageOutcome | None:
        return await self._sensor_mode_controller.maybe_reactivate_after_empty_window(
            task=task, plan=plan, corr=corr, now=now, ph=ph, ec=ec,
        )

    def _transition_to_deactivate_or_return(
        self, *, corr: CorrectionState, success: bool,
    ) -> StageOutcome:
        return self._transition_policy.transition_to_deactivate_or_return(
            corr=corr, success=success,
        )

    async def _correction_exhausted(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
    ) -> StageOutcome:
        stage = str(task.current_stage)
        topology = str(getattr(task, "topology", "") or "")
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        CORRECTION_EXHAUSTED.labels(topology=topology, stage=stage).inc()
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_EXHAUSTED",
            task=task,
            corr=corr,
            payload={
                "attempt": corr.attempt,
                "max_attempts": corr.max_attempts,
                "ec_attempt": corr.ec_attempt,
                "ec_max_attempts": corr.ec_max_attempts,
                "ph_attempt": corr.ph_attempt,
                "ph_max_attempts": corr.ph_max_attempts,
                "stage": stage,
            },
        )
        await self._alert_service.emit_correction_exhausted(task=task, corr=corr)
        if stage.strip().lower() == "irrigation_check":
            await self._alert_service.emit_irrigation_correction_exhausted(
                task=task, corr=corr,
            )
        policy_outcome = self._transition_policy.decide_exhausted_transition(
            current_stage=stage,
            stage_retry_count=task.workflow.stage_retry_count,
            level_poll_interval_sec=int(runtime.get("level_poll_interval_sec", 10)),
        )
        if policy_outcome is not None:
            return policy_outcome
        return self._transition_to_deactivate_or_return(corr=corr, success=False)

    async def _interrupt_for_stage_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None
        deadline_reached = self._deadline_reached(
            now=now, deadline=task.workflow.stage_deadline_at,
        )
        if not deadline_reached:
            return None
        current_stage = str(task.current_stage).strip().lower()
        # Resolve targets_reached only when we actually need it (irrigation path):
        # policy consults it just for the irrigation branch and we want to avoid
        # an unnecessary telemetry round-trip otherwise.
        targets_reached: bool | None = None
        if current_stage == "irrigation_check":
            targets_reached = await self._targets_reached(task=task, plan=plan, now=now)
        return self._transition_policy.decide_stage_deadline_transition(
            corr=corr,
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            deadline_reached=True,
            targets_reached=targets_reached,
        )

    def _interrupt_for_imminent_flow_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> StageOutcome | None:
        current_stage = str(task.current_stage).strip().lower()
        if self._expected_flow_path_state(current_stage=current_stage) is None:
            return None
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        deadline_too_close = self._deadline_too_close_for_irr_probe(
            now=now,
            deadline=task.workflow.stage_deadline_at,
            runtime=runtime,
        )
        return self._transition_policy.decide_imminent_flow_probe_transition(
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            expects_flow_path=True,
            deadline_too_close=deadline_too_close,
        )

    def _enter_correction_after_delay_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome:
        retry_deadline_outcome = self._interrupt_for_imminent_retry_then_probe_deadline(
            task=task_override or task,
            plan=plan,
            now=now,
            due_delay_sec=due_delay_sec,
            task_override=task_override,
        )
        if retry_deadline_outcome is not None:
            return retry_deadline_outcome
        return StageOutcome(
            kind="enter_correction",
            correction=corr,
            due_delay_sec=due_delay_sec,
            task_override=task_override,
        )

    def _interrupt_for_imminent_retry_then_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome | None:
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        # Short-circuit: flow-path probe protection only applies during stages
        # that drive valves/pumps; other stages' fixtures may not even carry a
        # stage_deadline_at, so we must avoid touching base helpers below.
        if self._expected_flow_path_state(current_stage=current_stage) is None:
            return None

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        remaining = self._remaining_stage_time_sec(
            now=now, deadline=task.workflow.stage_deadline_at,
        )
        required_budget = max(0.0, float(due_delay_sec)) + self._irr_probe_deadline_budget_sec(
            runtime=runtime,
        )
        return self._transition_policy.decide_imminent_retry_then_probe_transition(
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            expects_flow_path=True,
            remaining_sec=remaining,
            required_budget_sec=required_budget,
            task_override=task_override,
        )

    def _enforce_attempt_caps(self, *, task: Any) -> bool:
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        # During solution_fill we keep a single correction window alive for the
        # whole fill stage. Attempt-based exhaustion stays enabled for
        # recirculation windows; fill stops only by no-effect or stage timeout.
        return current_stage != "solution_fill_check"

    def _should_reset_attempt_counters_on_reaction(self, *, task: Any) -> bool:
        # Попытки считаются только для последовательных no-effect циклов.
        # Любая наблюдаемая реакция должна сбрасывать окно попыток, независимо от stage.
        return True

    def _should_log_limit_policy(self, *, task: Any, corr: CorrectionState) -> bool:
        if self._enforce_attempt_caps(task=task):
            return False
        return (
            not bool(getattr(corr, "limit_policy_logged", False))
            and corr.attempt == 0
            and corr.ec_attempt == 0
            and corr.ph_attempt == 0
            and corr.corr_step == "corr_check"
        )

    async def _log_attempt_cap_ignored(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        cap_type: str,
        current_value: int,
        limit_value: int,
    ) -> None:
        topology = str(getattr(task, "topology", "") or "")
        stage = str(getattr(task, "current_stage", "") or "")
        CORRECTION_CAP_IGNORED.labels(
            topology=topology,
            stage=stage,
            cap_type=cap_type,
        ).inc()
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_ATTEMPT_CAP_IGNORED",
            task=task,
            corr=corr,
            payload={
                "cap_type": cap_type,
                "current_value": current_value,
                "limit_value": limit_value,
                "policy": "fill_continuous_until_no_effect_or_timeout",
            },
        )
        _logger.info(
            "zone %s: ignoring %s attempt cap in solution_fill (%s/%s); correction remains active until no-effect or stage timeout",
            task.zone_id,
            cap_type,
            current_value,
            limit_value,
        )

    def _serialize_metric_ts(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return normalized.isoformat()
        return None

    async def _run_wait_observe(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> StageOutcome:
        corr_wait_until = self._normalize_timestamp(corr.wait_until)
        normalized_now = self._normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

        window_or_interrupt = await self._read_observation_window_or_interrupt(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type=pid_type,
            sensor_type=sensor_type,
        )
        if isinstance(window_or_interrupt, StageOutcome):
            return window_or_interrupt
        return await self._finalize_observation_result(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type=pid_type,
            sensor_type=sensor_type,
            window=window_or_interrupt,
        )

    # ── _run_wait_observe helpers (B1 decomposition) ───────────────────

    async def _read_observation_window_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> _ObservationWindow | StageOutcome:
        """Fetch and validate the post-dose observation window.

        Pipeline (any step may short-circuit with a StageOutcome):
          1. Resolve the prior PID entry, baseline value and last_dose_at.
             Missing baseline is a fail-closed config error.
          2. Read the telemetry window starting at ``last_dose_at + transport_delay``.
          3. Stale / no sensor → ``CORRECTION_SKIPPED_FRESHNESS`` + retry.
          4. Summarize (median + slope stability) → ``CORRECTION_SKIPPED_WINDOW_NOT_READY``
             + retry if not stabilised.

        Returns an ``_ObservationWindow`` with everything the finalize helper
        needs, otherwise a ``StageOutcome`` the orchestrator returns as-is.
        """
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        correction_cfg = self._correction_config(plan=plan, task=task)
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        pid_state = runtime.get("pid_state") if isinstance(runtime.get("pid_state"), Mapping) else {}
        pid_entry = pid_state.get(pid_type) if isinstance(pid_state.get(pid_type), Mapping) else {}
        observe_cfg = self._observation_config(
            kind=pid_type,
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=pid_entry,
        )
        last_dose_at = pid_entry.get("last_dose_at")
        baseline_value = pid_entry.get("last_measured_value")
        if not isinstance(last_dose_at, datetime) or baseline_value is None:
            raise TaskExecutionError(
                "corr_observation_baseline_missing",
                f"{pid_type} baseline is missing for observation window",
            )

        observation_started_at = last_dose_at + timedelta(
            seconds=int(observe_cfg["transport_delay_sec"]),
        )
        window = await self._runtime_monitor.read_metric_window(
            zone_id=task.zone_id,
            sensor_type=sensor_type,
            since_ts=observation_started_at,
            telemetry_max_age_sec=int(runtime.get("telemetry_max_age_sec", 300)),
        )
        if not window["has_sensor"] or window["is_stale"]:
            retry_delay_sec = self._correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="telemetry_stale_retry_sec",
                default=30.0,
            )
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_FRESHNESS",
                task=task,
                corr=corr,
                payload={
                    "pid_type": pid_type,
                    "sensor_type": sensor_type,
                    "sensor_scope": "observe_window",
                    "reason": f"{sensor_type} telemetry stale/unavailable during observation window",
                    "retry_after_sec": retry_delay_sec,
                    "telemetry_max_age_sec": int(runtime.get("telemetry_max_age_sec", 300)),
                },
            )
            _logger.warning(
                "zone %s: телеметрия %s устарела или недоступна во время observation window; повтор через %.1f с",
                task.zone_id,
                sensor_type,
                retry_delay_sec,
            )
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=retry_delay_sec,
            )

        summary = self._summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(observe_cfg["window_min_samples"]),
            stability_max_slope=float(observe_cfg["stability_max_slope"]),
        )
        if not summary["ready"]:
            await self._log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                task=task,
                corr=corr,
                payload={
                    "pid_type": pid_type,
                    "sensor_type": sensor_type,
                    "sensor_scope": "observe_window",
                    "reason": summary.get("reason"),
                    "sample_count": len(window["samples"]) if isinstance(window.get("samples"), (list, tuple)) else None,
                    "slope": summary.get("slope"),
                    "retry_after_sec": int(observe_cfg["observe_poll_sec"]),
                    "window_min_samples": int(observe_cfg["window_min_samples"]),
                    "stability_max_slope": float(observe_cfg["stability_max_slope"]),
                },
            )
            return self._enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=int(observe_cfg["observe_poll_sec"]),
            )

        return _ObservationWindow(
            samples=window["samples"],
            summary_value=float(summary["value"]),
            baseline_value=float(baseline_value),
            last_dose_at=last_dose_at,
            observe_cfg=observe_cfg,
            pid_entry=pid_entry,
            process_cfg=process_cfg,
        )

    async def _finalize_observation_result(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
        window: _ObservationWindow,
    ) -> StageOutcome:
        """Analyze a ready observation window and schedule the next step.

        Pipeline:
          1. Compute directional/peak/learning effects via ObservationAnalyzer.
          2. Derive ``is_no_effect`` and increment the consecutive counter.
          3. Log ``CORRECTION_OBSERVATION_EVALUATED``.
          4. Persist the updated PID state (measured value + adaptive stats).
          5. Clear EC feedforward_bias on the EC branch.
          6. If the no-effect limit is reached → ``_no_effect_limit_reached``.
          7. Otherwise: bump attempt counters (or reset on reaction), build
             the next correction state preserving the opposite-direction
             pending dose, and return ``enter_correction`` pointing back
             at ``corr_check``.
        """
        observe_cfg = window.observe_cfg
        pid_entry = window.pid_entry
        baseline_value = window.baseline_value
        observed_value = window.summary_value
        last_dose_at = window.last_dose_at
        dose_amount_ml = corr.ec_amount_ml if pid_type == "ec" else corr.ph_amount_ml
        expected_effect = self._expected_effect(
            pid_type=pid_type,
            corr=corr,
            process_cfg=window.process_cfg,
        )
        threshold_effect = expected_effect * float(observe_cfg["min_effect_fraction"])
        response = self._observation_analyzer.analyze_window(
            samples=window.samples,
            pid_type=pid_type,
            corr=corr,
            baseline_value=baseline_value,
            observed_value=observed_value,
            last_dose_at=last_dose_at,
            dose_amount_ml=float(dose_amount_ml or 0.0),
            threshold_effect=threshold_effect,
            window_min_samples=int(observe_cfg["window_min_samples"]),
        )
        directional_effect = float(response.tail_effect)
        peak_effect = float(response.peak_effect)
        learning_effect = float(response.learning_effect)
        is_no_effect = peak_effect < threshold_effect
        next_no_effect_count = (
            int(pid_entry.get("no_effect_count") or 0) + 1 if is_no_effect else 0
        )
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_OBSERVATION_EVALUATED",
            task=task,
            corr=corr,
            payload={
                "pid_type": pid_type,
                "sensor_type": sensor_type,
                "observe_seq": self._observe_seq(corr=corr, pid_type=pid_type),
                "dose_amount_ml": dose_amount_ml,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "actual_effect": directional_effect,
                "peak_effect": peak_effect,
                "peak_observed_value": response.peak_value,
                "retention_ratio": response.retention_ratio,
                "wave_score": response.wave_score,
                "wave_detected": response.wave_detected,
                "reaction_detected": peak_effect >= threshold_effect,
                "learning_effect": learning_effect,
                "first_reaction_sec": response.first_reaction_sec,
                "threshold_effect": threshold_effect,
                "min_effect_fraction": float(observe_cfg["min_effect_fraction"]),
                "transport_delay_sec": int(observe_cfg["transport_delay_sec"]),
                "settle_sec": int(observe_cfg["settle_sec"]),
                "window_min_samples": int(observe_cfg["window_min_samples"]),
                "no_effect_count_next": next_no_effect_count,
                "is_no_effect": is_no_effect,
            },
        )
        await self._persist_pid_state_updates(
            zone_id=task.zone_id,
            now=now,
            updates={
                pid_type: {
                    "last_measurement_at": now,
                    "last_measured_value": observed_value,
                    "no_effect_count": next_no_effect_count,
                    "stats": self._observation_analyzer.merge_adaptive_stats(
                        pid_entry=pid_entry,
                        pid_type=pid_type,
                        corr=corr,
                        dose_amount_ml=float(dose_amount_ml or 0.0),
                        learning_effect=learning_effect,
                        expected_effect=expected_effect,
                        first_reaction_sec=response.first_reaction_sec,
                        settle_sec=response.settle_sec,
                        wave_score=response.wave_score,
                        retention_ratio=response.retention_ratio,
                    ),
                },
            },
        )
        if pid_type == "ec" and self._pid_state_repository is not None:
            await self._pid_state_repository.clear_feedforward_bias(zone_id=int(task.zone_id))

        if next_no_effect_count >= int(observe_cfg["no_effect_limit"]):
            return await self._no_effect_limit_reached(
                task=task,
                plan=plan,
                corr=corr,
                pid_type=pid_type,
                baseline_value=baseline_value,
                observed_value=observed_value,
                expected_effect=expected_effect,
                actual_effect=peak_effect,
                no_effect_limit=int(observe_cfg["no_effect_limit"]),
            )

        # Attempt counters model consecutive no-effect observations only.
        # Any observable reaction resets the correction window counters.
        if is_no_effect:
            next_attempt = corr.attempt + 1
            next_ec_attempt = corr.ec_attempt
            next_ph_attempt = corr.ph_attempt
        elif self._should_reset_attempt_counters_on_reaction(task=task):
            next_attempt = 0
            next_ec_attempt = 0
            next_ph_attempt = 0
        else:
            next_attempt = corr.attempt
            next_ec_attempt = corr.ec_attempt
            next_ph_attempt = corr.ph_attempt

        preserve_ec_pending = pid_type != "ec" and bool(corr.needs_ec)
        preserve_ph_up_pending = pid_type != "ph" and bool(corr.needs_ph_up)
        preserve_ph_down_pending = pid_type != "ph" and bool(corr.needs_ph_down)

        next_corr = replace(
            corr,
            corr_step="corr_check",
            attempt=next_attempt,
            ec_attempt=next_ec_attempt,
            ph_attempt=next_ph_attempt,
            wait_until=None,
            needs_ec=preserve_ec_pending,
            ec_node_uid=corr.ec_node_uid if preserve_ec_pending else None,
            ec_channel=corr.ec_channel if preserve_ec_pending else None,
            ec_duration_ms=corr.ec_duration_ms if preserve_ec_pending else None,
            ec_component=corr.ec_component if preserve_ec_pending else None,
            ec_amount_ml=corr.ec_amount_ml if preserve_ec_pending else None,
            needs_ph_up=preserve_ph_up_pending,
            needs_ph_down=preserve_ph_down_pending,
            ph_node_uid=corr.ph_node_uid if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
            ph_channel=corr.ph_channel if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
            ph_duration_ms=corr.ph_duration_ms if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
            ph_amount_ml=corr.ph_amount_ml if (preserve_ph_up_pending or preserve_ph_down_pending) else None,
        )
        return StageOutcome(kind="enter_correction", correction=next_corr)

    def _expected_effect(
        self,
        *,
        pid_type: str,
        corr: CorrectionState,
        process_cfg: Mapping[str, Any],
    ) -> float:
        try:
            return self._observation_analyzer.expected_effect(
                pid_type=pid_type, corr=corr, process_cfg=process_cfg,
            )
        except ValueError:
            raise TaskExecutionError(
                "corr_process_gain_missing",
                f"Для оценки отклика {pid_type} требуется process gain",
            )

    def _expected_cross_coupling_ph(self, *, corr: CorrectionState, process_cfg: Mapping[str, Any]) -> float:
        return self._observation_analyzer.expected_cross_coupling_ph(
            corr=corr, process_cfg=process_cfg,
        )

    async def _no_effect_limit_reached(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        pid_type: str,
        baseline_value: float,
        observed_value: float,
        expected_effect: float,
        actual_effect: float,
        no_effect_limit: int,
    ) -> StageOutcome:
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_NO_EFFECT",
            task=task,
            corr=corr,
            payload={
                "pid_type": pid_type,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "actual_effect": actual_effect,
                "threshold_effect": expected_effect * 0.25,
                "no_effect_limit": no_effect_limit,
            },
        )
        await self._alert_service.emit_no_effect(
            task=task,
            pid_type=pid_type,
            baseline_value=baseline_value,
            observed_value=observed_value,
            expected_effect=expected_effect,
            actual_effect=actual_effect,
            no_effect_limit=no_effect_limit,
        )
        policy_outcome = self._transition_policy.decide_no_effect_transition(
            current_stage=str(task.current_stage),
            stage_retry_count=task.workflow.stage_retry_count,
        )
        if policy_outcome is not None:
            return policy_outcome
        return self._transition_to_deactivate_or_return(corr=corr, success=False)

    async def _log_correction_event(
        self,
        *,
        zone_id: int,
        event_type: str,
        task: Any | None = None,
        corr: CorrectionState | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        await self._event_logger.log(
            zone_id=zone_id,
            event_type=event_type,
            task=task,
            corr=corr,
            payload=payload,
        )

    def _observe_seq(self, *, corr: CorrectionState, pid_type: str, after_dose: bool = False) -> int | None:
        return CorrectionEventLogger.observe_seq(
            corr=corr, pid_type=pid_type, after_dose=after_dose,
        )


    def _correction_config(self, *, plan: Any, task: Any) -> Mapping[str, Any]:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        return self._correction_config_for_task(task=task, runtime=runtime)

    def _resolve_actuators(self, *, runtime: Mapping[str, Any], task: Any, plan: Any) -> dict:
        corr = self._correction_config(plan=plan, task=task)
        actuators = corr.get("actuators") if isinstance(corr.get("actuators"), Mapping) else {}
        return {
            "ec": actuators.get("ec"),
            "ec_actuators": actuators.get("ec_actuators"),
            "ph_up": actuators.get("ph_up"),
            "ph_down": actuators.get("ph_down"),
        }

    async def _maybe_emit_pid_output_zone_event(
        self,
        *,
        zone_id: int,
        corr_step: str,
        dose_plan: DosePlan,
        pid_state_before: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        now: datetime,
    ) -> None:
        """Пишет PID_OUTPUT в zone_events для вкладки «Логи PID» в UI."""
        try:
            detail = build_pid_output_detail(
                corr_step=corr_step,
                dose_plan=dose_plan,
                pid_state_before=pid_state_before,
                current_ph=current_ph,
                current_ec=current_ec,
                target_ph=target_ph,
                target_ec=target_ec,
                now=now,
            )
            if detail is None:
                return
            payload = with_runtime_event_contract({k: v for k, v in detail.items() if v is not None})
            await create_zone_event(zone_id, "PID_OUTPUT", payload)
        except Exception:
            _logger.debug("Не удалось записать PID_OUTPUT zone event", exc_info=True)

    async def _persist_pid_state_updates(
        self,
        *,
        zone_id: Any,
        updates: Mapping[str, Any],
        now: datetime,
    ) -> None:
        """Persist PID state updates (integral, prev_error, etc.) to the DB.

        Called after every ``_run_check`` so the I- and D-terms accumulate
        across correction attempts.  No-op if no repository is wired or the
        update dict is empty.
        """
        if not updates or self._pid_state_repository is None:
            return
        try:
            await self._pid_state_repository.upsert_states(
                zone_id=int(zone_id),
                now=now,
                updates=[
                    {"pid_type": pid_type, **state_dict}
                    for pid_type, state_dict in updates.items()
                ],
            )
        except Exception:
            raise TaskExecutionError(
                "corr_pid_state_persist_failed",
                f"Не удалось сохранить PID state для зоны {zone_id}",
            )

    def _normalize_timestamp(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value

    def _correction_retry_delay_sec(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        key: str,
        default: float,
    ) -> float:
        raw = correction_cfg.get(key)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default
