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

import logging
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import CorrectionPlanner
from ae3lite.infrastructure.metrics import CORRECTION_ATTEMPT, CORRECTION_CAP_IGNORED, CORRECTION_EXHAUSTED
from common.db import create_zone_event
from common.biz_alerts import send_biz_alert
from common.water_flow import check_water_level

_logger = logging.getLogger(__name__)


class CorrectionHandler(BaseStageHandler):
    """Handles all ``corr_*`` steps within the correction state machine."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        planner: Optional[CorrectionPlanner] = None,
        pid_state_repository: Any = None,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
        )
        self._planner = planner or CorrectionPlanner()
        self._pid_state_repository = pid_state_repository

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

        deadline_outcome = self._interrupt_for_stage_deadline(task=task, corr=corr, now=now)
        if deadline_outcome is not None:
            return deadline_outcome

        step = corr.corr_step
        if step not in {"corr_activate", "corr_wait_stable", "corr_deactivate", "corr_done"}:
            await self._assert_flow_path_active(task=task, plan=plan, now=now)
        if step == "corr_activate":
            return await self._run_activate(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_wait_stable":
            return self._run_wait_stable(corr=corr)
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
            "ae3_unknown_corr_step", f"Unknown correction step={step!r}",
        )

    # ── Step handlers ───────────────────────────────────────────────

    async def _run_activate(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        sensor_cmds = self._build_sensor_mode_commands(
            plan=plan, cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        if sensor_cmds:
            result = await self._command_gateway.run_batch(
                task=task, commands=sensor_cmds, now=now,
            )
            if not result["success"]:
                raise TaskExecutionError(
                    str(result["error_code"]), str(result["error_message"]),
                )
        next_corr = replace(corr, corr_step="corr_wait_stable")
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=corr.stabilization_sec,
        )

    def _run_wait_stable(self, *, corr: CorrectionState) -> StageOutcome:
        next_corr = replace(corr, corr_step="corr_check")
        return StageOutcome(kind="enter_correction", correction=next_corr)

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

        targets_reached = await self._targets_reached(task=task, plan=plan, now=now)
        next_stage = "solution_fill_stop_to_ready" if targets_reached else "solution_fill_stop_to_prepare"
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_INTERRUPTED_STAGE_COMPLETE",
            task=task,
            corr=corr,
            payload={
                "next_stage": next_stage,
                "targets_reached": targets_reached,
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
        target_ec = float(runtime["target_ec"])
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

        corr_wait_until = self._normalize_timestamp(corr.wait_until)
        normalized_now = self._normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
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
            ph = await self._read_decision_metric(
                zone_id=task.zone_id,
                sensor_type="PH",
                telemetry_max_age_sec=max_age,
                config=ph_cfg,
                now=now,
            )
            ec = await self._read_decision_metric(
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
                "zone %s: telemetry stale during correction check; retrying in %.1fs",
                task.zone_id,
                retry_delay_sec,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=retry_delay_sec,
            )
        if not ph["ready"] or not ec["ready"]:
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
            msg = self._format_decision_window_error(ph=ph, ec=ec)
            retry_delay_sec = self._decision_window_retry_delay_sec(
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
                    "ph_reason": ph.get("reason"),
                    "ph_sample_count": ph.get("sample_count"),
                    "ph_slope": ph.get("slope"),
                    "ph_window_min_samples": ph.get("window_min_samples"),
                    "ph_telemetry_period_sec": ph.get("telemetry_period_sec"),
                    "ph_latest_sample_ts": self._serialize_metric_ts(ph.get("latest_sample_ts")),
                    "ph_since_ts": self._serialize_metric_ts(ph.get("since_ts")),
                    "ec_reason": ec.get("reason"),
                    "ec_sample_count": ec.get("sample_count"),
                    "ec_slope": ec.get("slope"),
                    "ec_window_min_samples": ec.get("window_min_samples"),
                    "ec_telemetry_period_sec": ec.get("telemetry_period_sec"),
                    "ec_latest_sample_ts": self._serialize_metric_ts(ec.get("latest_sample_ts")),
                    "ec_since_ts": self._serialize_metric_ts(ec.get("since_ts")),
                },
            )
            _logger.warning("zone %s: %s — retrying in %.1fs", task.zone_id, msg, retry_delay_sec)
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=retry_delay_sec,
            )

        current_ph = float(ph["value"])
        current_ec = float(ec["value"])

        if not math.isfinite(current_ph) or not math.isfinite(current_ec):
            retry_delay_sec = self._correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="decision_window_retry_sec",
                default=30.0,
            )
            _logger.warning(
                "zone %s: non-finite telemetry value (ph=%s, ec=%s); retrying in %.1fs",
                task.zone_id, current_ph, current_ec, retry_delay_sec,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=retry_delay_sec,
            )

        wl_ok, wl_level = await check_water_level(task.zone_id)
        if not wl_ok:
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
                    "water_level_pct": (wl_level or 0.0) * 100.0,
                    "retry_after_sec": retry_delay_sec,
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
                },
            )
            _logger.warning(
                "zone %s: water level %.0f%% is below threshold; skipping correction for %.1fs",
                task.zone_id, (wl_level or 0.0) * 100, retry_delay_sec,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=retry_delay_sec,
            )

        if self._planner.is_within_tolerance(
            current_ph=current_ph, current_ec=current_ec,
            target_ph=target_ph, target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
            ph_min=self._coerce_float(runtime.get("target_ph_min")),
            ph_max=self._coerce_float(runtime.get("target_ph_max")),
            ec_min=self._coerce_float(runtime.get("target_ec_min")),
            ec_max=self._coerce_float(runtime.get("target_ec_max")),
        ):
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
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
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

        # Build dose plan
        actuators = self._resolve_actuators(runtime=runtime, task=task, plan=plan)
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
            ec_min=self._coerce_float(runtime.get("target_ec_min")),
            ec_max=self._coerce_float(runtime.get("target_ec_max")),
            ec_actuator=actuators.get("ec"),
            ec_actuators=actuators.get("ec_actuators"),
            ph_up_actuator=actuators.get("ph_up"),
            ph_down_actuator=actuators.get("ph_down"),
        )

        # Persist updated PID state (integral, prev_error, prev_derivative, etc.)
        # so the controller has memory across correction attempts.
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
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
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
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
                },
            )
            next_corr = replace(corr, corr_step="corr_check")
            return StageOutcome(
                kind="enter_correction",
                correction=next_corr,
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
                        "target_ec_min": runtime.get("target_ec_min"),
                        "target_ec_max": runtime.get("target_ec_max"),
                    },
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
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
                },
            )
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

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

        # Save dose plan into correction state
        next_corr = replace(
            corr,
            needs_ec=dose_plan.needs_ec,
            ec_node_uid=dose_plan.ec_node_uid,
            ec_channel=dose_plan.ec_channel,
            ec_duration_ms=dose_plan.ec_duration_ms,
            ec_component=dose_plan.ec_component or None,
            ec_amount_ml=dose_plan.ec_amount_ml if dose_plan.ec_amount_ml else None,
            needs_ph_up=dose_plan.needs_ph_up,
            needs_ph_down=dose_plan.needs_ph_down,
            ph_node_uid=dose_plan.ph_node_uid,
            ph_channel=dose_plan.ph_channel,
            ph_duration_ms=dose_plan.ph_duration_ms,
            ph_amount_ml=dose_plan.ph_amount_ml if dose_plan.ph_amount_ml else None,
        )

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
                "target_ec_min": runtime.get("target_ec_min"),
                "target_ec_max": runtime.get("target_ec_max"),
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
        return StageOutcome(kind="enter_correction", correction=next_corr)

    async def _run_dose_ec(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
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
                    "EC dose plan missing "
                    f"(node={corr.ec_node_uid}, ch={corr.ec_channel}, ms={corr.ec_duration_ms}, "
                    f"ml={corr.ec_amount_ml})"
                ),
            )
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step="corr_dose_ec").inc()
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ec_node_uid,
            channel=corr.ec_channel,
            payload={"cmd": "dose", "params": {"ml": corr.ec_amount_ml}},
        )
        result = await self._command_gateway.run_batch(task=task, commands=(cmd,), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))

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
                _logger.debug("Could not read EC pid_state for event logging", exc_info=True)
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
                "observe_seq": self._observe_seq(corr=corr, pid_type="ec", after_dose=True),
                "ec_component": corr.ec_component,
                "current_ec": current_ec,
                "target_ec": runtime.get("target_ec"),
                "target_ec_min": runtime.get("target_ec_min"),
                "target_ec_max": runtime.get("target_ec_max"),
                "source": "correction_handler",
            },
        )

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
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=int(observe_cfg["hold_window_sec"]),
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
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ph_node_uid,
            channel=corr.ph_channel,
            payload={"cmd": "dose", "params": {"ml": corr.ph_amount_ml}},
        )
        result = await self._command_gateway.run_batch(task=task, commands=(cmd,), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))

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
                _logger.debug("Could not read PH pid_state for event logging", exc_info=True)
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
        await self._persist_pid_state_updates(
            zone_id=task.zone_id,
            now=now,
            updates={
                "ph": {
                    "hold_until": wait_until,
                    "last_output_ms": corr.ph_duration_ms,
                    "last_correction_kind": "ph_up" if corr.needs_ph_up else "ph_down",
                },
            },
        )
        next_corr = replace(corr, corr_step="corr_wait_ph", ph_attempt=corr.ph_attempt + 1, wait_until=wait_until)
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=int(observe_cfg["hold_window_sec"]),
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
        if corr.activated_here:
            sensor_cmds = self._build_sensor_mode_commands(
                plan=plan, cmd="deactivate_sensor_mode", params={},
            )
            if sensor_cmds:
                result = await self._command_gateway.run_batch(
                    task=task, commands=sensor_cmds, now=now,
                )
                if not result["success"]:
                    raise TaskExecutionError(
                        str(result["error_code"]), str(result["error_message"]),
                    )

        next_corr = replace(corr, corr_step="corr_done")
        return StageOutcome(kind="enter_correction", correction=next_corr)

    def _run_done(self, *, corr: CorrectionState) -> StageOutcome:
        success = corr.outcome_success if corr.outcome_success is not None else False
        next_stage = corr.return_stage_success if success else corr.return_stage_fail
        return StageOutcome(kind="exit_correction", next_stage=next_stage, correction=corr)

    # ── Helpers ─────────────────────────────────────────────────────

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
        ph: Mapping[str, Any],
        ec: Mapping[str, Any],
    ) -> StageOutcome | None:
        if corr.activated_here:
            return None
        if not (
            self._window_empty_for_sensor_reactivation(metric=ph)
            or self._window_empty_for_sensor_reactivation(metric=ec)
        ):
            return None

        sensor_cmds = self._build_sensor_mode_commands(
            plan=plan,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        if not sensor_cmds:
            return None

        result = await self._command_gateway.run_batch(
            task=task,
            commands=sensor_cmds,
            now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]),
                str(result["error_message"]),
            )

        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_SENSOR_MODE_REACTIVATED",
            task=task,
            corr=corr,
            payload={
                "ph_reason": ph.get("reason"),
                "ph_sample_count": ph.get("sample_count"),
                "ec_reason": ec.get("reason"),
                "ec_sample_count": ec.get("sample_count"),
                "stabilization_sec": corr.stabilization_sec,
            },
        )
        _logger.warning(
            "zone %s: decision window is empty, re-activating sensor mode and waiting %ss",
            task.zone_id,
            corr.stabilization_sec,
        )
        next_corr = replace(corr, corr_step="corr_wait_stable")
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=corr.stabilization_sec,
        )

    def _window_empty_for_sensor_reactivation(self, *, metric: Mapping[str, Any]) -> bool:
        if metric.get("ready"):
            return False
        if str(metric.get("reason") or "").strip().lower() != "insufficient_samples":
            return False
        sample_count = metric.get("sample_count")
        if sample_count is None:
            return True
        try:
            return int(sample_count) <= 0
        except (TypeError, ValueError):
            return False

    def _transition_to_deactivate_or_return(
        self, *, corr: CorrectionState, success: bool,
    ) -> StageOutcome:
        next_corr = replace(corr, outcome_success=success)
        if corr.activated_here:
            next_corr = replace(next_corr, corr_step="corr_deactivate")
            return StageOutcome(kind="enter_correction", correction=next_corr)
        # Sensors not activated by us — skip deactivation
        next_stage = corr.return_stage_success if success else corr.return_stage_fail
        return StageOutcome(kind="exit_correction", next_stage=next_stage, correction=next_corr)

    async def _correction_exhausted(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
    ) -> StageOutcome:
        stage = str(task.current_stage)
        topology = str(getattr(task, "topology", "") or "")
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
        try:
            await send_biz_alert(
                code="biz_correction_exhausted",
                alert_type="AE3 Correction Exhausted",
                message="Correction cycle exhausted all configured attempts.",
                severity="error",
                zone_id=int(task.zone_id),
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": stage,
                    "topology": topology,
                    "component": f"correction:{stage}",
                    "attempt": corr.attempt,
                    "max_attempts": corr.max_attempts,
                    "ec_attempt": corr.ec_attempt,
                    "ph_attempt": corr.ph_attempt,
                    "message": "Correction cycle exhausted all dose attempts — check pH/EC dosing hardware.",
                },
                scope_parts=(f"stage:{stage}", f"topology:{topology}"),
            )
        except Exception:
            _logger.warning("Failed to send CORRECTION_EXHAUSTED infra alert zone_id=%s", task.zone_id)
        if str(task.current_stage).strip().lower() == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )
        if str(task.current_stage).strip().lower() == "solution_fill_check":
            runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_check",
                stage_retry_count=task.workflow.stage_retry_count + 1,
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )
        return self._transition_to_deactivate_or_return(corr=corr, success=False)

    def _interrupt_for_stage_deadline(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None
        if not self._deadline_reached(now=now, deadline=task.workflow.stage_deadline_at):
            return None

        current_stage = str(task.current_stage).strip().lower()
        if current_stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )
        if current_stage == "solution_fill_check":
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_timeout_stop",
            )
        return None

    def _enforce_attempt_caps(self, *, task: Any) -> bool:
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        # During solution_fill we keep a single correction window alive for the
        # whole fill stage. Attempt-based exhaustion stays enabled for
        # recirculation windows; fill stops only by no-effect or stage timeout.
        return current_stage != "solution_fill_check"

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

    async def _read_decision_metric(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        since_ts = self._decision_window_since_ts(now=now, config=config)
        window = await self._runtime_monitor.read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not window["has_sensor"] or window["is_stale"]:
            raise TaskExecutionError(
                "corr_telemetry_stale",
                f"{sensor_type} telemetry stale/unavailable during correction check",
            )
        summary = self._summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(config["window_min_samples"]),
            stability_max_slope=float(config["stability_max_slope"]),
        )
        if not summary["ready"]:
            return {
                "ready": False,
                "reason": str(summary.get("reason") or "unknown"),
                "sample_count": int(len(window["samples"])),
                "slope": summary.get("slope"),
                "latest_sample_ts": window.get("latest_sample_ts"),
                "since_ts": since_ts,
                "window_min_samples": int(config["window_min_samples"]),
                "telemetry_period_sec": int(config["telemetry_period_sec"]),
            }
        return {
            "ready": True,
            "value": summary["value"],
            "sample_count": summary["sample_count"],
            "slope": summary["slope"],
        }

    def _format_decision_window_error(
        self,
        *,
        ph: Mapping[str, Any],
        ec: Mapping[str, Any],
    ) -> str:
        details: list[str] = []
        for sensor_type, metric in (("PH", ph), ("EC", ec)):
            if metric.get("ready"):
                continue
            parts = [f"{sensor_type}={str(metric.get('reason') or 'unknown')}"]
            sample_count = metric.get("sample_count")
            if sample_count is not None:
                parts.append(f"samples={sample_count}")
            slope = metric.get("slope")
            if slope is not None:
                parts.append(f"slope={float(slope):.4f}")
            details.append(",".join(parts))
        reason = "; ".join(details) if details else "decision window unavailable"
        return f"Correction decision window not ready: {reason}"

    def _decision_window_retry_delay_sec(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        ph: Mapping[str, Any],
        ec: Mapping[str, Any],
    ) -> float:
        retry_delay_sec = self._correction_retry_delay_sec(
            correction_cfg=correction_cfg,
            key="decision_window_retry_sec",
            default=30.0,
        )
        starvation_delays = [
            self._decision_window_missing_sample_delay_sec(metric=metric)
            for metric in (ph, ec)
        ]
        starvation_delays = [delay for delay in starvation_delays if delay is not None]
        if starvation_delays:
            return min(retry_delay_sec, max(starvation_delays))
        return retry_delay_sec

    def _decision_window_missing_sample_delay_sec(self, *, metric: Mapping[str, Any]) -> float | None:
        if str(metric.get("reason") or "").strip().lower() != "insufficient_samples":
            return None
        try:
            sample_count = int(metric.get("sample_count"))
            window_min_samples = int(metric.get("window_min_samples"))
            telemetry_period_sec = float(metric.get("telemetry_period_sec") or 1.0)
        except (TypeError, ValueError):
            return None
        missing_samples = max(1, window_min_samples - sample_count)
        return max(1.0, telemetry_period_sec * missing_samples)

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
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

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

        observation_started_at = last_dose_at + timedelta(seconds=int(observe_cfg["transport_delay_sec"]))
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
                "zone %s: %s telemetry stale/unavailable during observation window; retrying in %.1fs",
                task.zone_id,
                sensor_type,
                retry_delay_sec,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
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
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=int(observe_cfg["observe_poll_sec"]),
            )

        observed_value = float(summary["value"])
        dose_amount_ml = corr.ec_amount_ml if pid_type == "ec" else corr.ph_amount_ml
        expected_effect = self._expected_effect(
            pid_type=pid_type,
            corr=corr,
            process_cfg=process_cfg,
        )
        threshold_effect = expected_effect * float(observe_cfg["min_effect_fraction"])
        response_metrics = self._analyze_observation_window(
            samples=window["samples"],
            pid_type=pid_type,
            corr=corr,
            baseline_value=float(baseline_value),
            observed_value=observed_value,
            last_dose_at=last_dose_at,
            dose_amount_ml=float(dose_amount_ml or 0.0),
            threshold_effect=threshold_effect,
            window_min_samples=int(observe_cfg["window_min_samples"]),
        )
        directional_effect = float(response_metrics["tail_effect"])
        peak_effect = float(response_metrics["peak_effect"])
        learning_effect = float(response_metrics["learning_effect"])
        is_no_effect = peak_effect < threshold_effect
        next_no_effect_count = int(pid_entry.get("no_effect_count") or 0) + 1 if is_no_effect else 0
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
                "baseline_value": float(baseline_value),
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "actual_effect": directional_effect,
                "peak_effect": peak_effect,
                "peak_observed_value": response_metrics["peak_value"],
                "retention_ratio": response_metrics["retention_ratio"],
                "wave_score": response_metrics["wave_score"],
                "wave_detected": response_metrics["wave_detected"],
                "reaction_detected": peak_effect >= threshold_effect,
                "learning_effect": learning_effect,
                "first_reaction_sec": response_metrics["first_reaction_sec"],
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
                    "stats": self._merge_adaptive_stats(
                        pid_entry=pid_entry,
                        pid_type=pid_type,
                        corr=corr,
                        dose_amount_ml=float(dose_amount_ml or 0.0),
                        learning_effect=learning_effect,
                        expected_effect=expected_effect,
                        first_reaction_sec=response_metrics["first_reaction_sec"],
                        settle_sec=response_metrics["settle_sec"],
                        wave_score=response_metrics["wave_score"],
                        retention_ratio=response_metrics["retention_ratio"],
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
                baseline_value=float(baseline_value),
                observed_value=observed_value,
                expected_effect=expected_effect,
                actual_effect=peak_effect,
                no_effect_limit=int(observe_cfg["no_effect_limit"]),
            )

        # When the dose had a measurable effect, reset all attempt counters so
        # the correction cycle can continue indefinitely as long as the dosing
        # hardware keeps responding.  Only consecutive no-reaction doses count
        # toward exhaustion (tracked via no_effect_count → no_effect_limit).
        if is_no_effect:
            next_attempt = corr.attempt + 1
            next_ec_attempt = corr.ec_attempt
            next_ph_attempt = corr.ph_attempt
        else:
            next_attempt = 0
            next_ec_attempt = 0
            next_ph_attempt = 0

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
        if pid_type == "ec":
            gain = self._coerce_float(process_cfg.get("ec_gain_per_ml"))
            amount_ml = corr.ec_amount_ml
        elif corr.needs_ph_up:
            gain = self._coerce_float(process_cfg.get("ph_up_gain_per_ml"))
            amount_ml = corr.ph_amount_ml
        else:
            gain = self._coerce_float(process_cfg.get("ph_down_gain_per_ml"))
            amount_ml = corr.ph_amount_ml
        if gain is None or gain <= 0 or amount_ml is None or amount_ml <= 0:
            raise TaskExecutionError(
                "corr_process_gain_missing",
                f"Process gain is required to evaluate {pid_type} response",
            )
        return float(gain) * float(amount_ml)

    def _directional_effect(
        self,
        *,
        pid_type: str,
        corr: CorrectionState,
        baseline_value: float,
        observed_value: float,
    ) -> float:
        if pid_type == "ec":
            return max(0.0, observed_value - baseline_value)
        if corr.needs_ph_up:
            return max(0.0, observed_value - baseline_value)
        return max(0.0, baseline_value - observed_value)

    def _analyze_observation_window(
        self,
        *,
        samples: Any,
        pid_type: str,
        corr: CorrectionState,
        baseline_value: float,
        observed_value: float,
        last_dose_at: datetime,
        dose_amount_ml: float,
        threshold_effect: float,
        window_min_samples: int,
    ) -> dict[str, Any]:
        sample_list = [item for item in (list(samples) if isinstance(samples, (list, tuple)) else []) if item.get("value") is not None]
        if not sample_list:
            tail_effect = self._directional_effect(
                pid_type=pid_type,
                corr=corr,
                baseline_value=baseline_value,
                observed_value=observed_value,
            )
            return {
                "tail_effect": tail_effect,
                "peak_effect": tail_effect,
                "peak_value": observed_value,
                "retention_ratio": 1.0 if tail_effect > 0 else 0.0,
                "wave_score": 0.0,
                "wave_detected": False,
                "learning_effect": tail_effect,
                "first_reaction_sec": None,
                "settle_sec": None,
            }

        tail_size = min(len(sample_list), max(window_min_samples, math.ceil(len(sample_list) / 2)))
        tail_values = [float(item["value"]) for item in sample_list[-tail_size:]]
        tail_value = float(median(tail_values))
        directional_effects = [
            self._directional_effect(
                pid_type=pid_type,
                corr=corr,
                baseline_value=baseline_value,
                observed_value=float(item["value"]),
            )
            for item in sample_list
        ]
        peak_index = max(range(len(directional_effects)), key=directional_effects.__getitem__)
        peak_effect = float(directional_effects[peak_index])
        peak_value = float(sample_list[peak_index]["value"])
        tail_effect = self._directional_effect(
            pid_type=pid_type,
            corr=corr,
            baseline_value=baseline_value,
            observed_value=tail_value,
        )
        retention_ratio = 0.0 if peak_effect <= 0 else max(0.0, min(1.0, tail_effect / peak_effect))
        wave_score = 0.0 if peak_effect <= 0 else max(0.0, min(1.0, 1.0 - retention_ratio))
        wave_detected = peak_effect >= threshold_effect and wave_score >= 0.35
        learning_effect = tail_effect if not wave_detected else (tail_effect + ((peak_effect - tail_effect) * 0.35))

        trigger_effect = max(threshold_effect * 0.5, 1e-6)
        first_reaction_sec: float | None = None
        settle_sec: float | None = None
        first_reaction_ts: datetime | None = None
        for sample, effect in zip(sample_list, directional_effects):
            ts = sample.get("ts")
            if effect >= trigger_effect and isinstance(ts, datetime):
                first_reaction_ts = ts
                break
        last_sample_ts = sample_list[-1].get("ts")
        if isinstance(first_reaction_ts, datetime):
            first_reaction_sec = max(0.0, (first_reaction_ts - last_dose_at).total_seconds())
            if isinstance(last_sample_ts, datetime):
                settle_sec = max(0.0, (last_sample_ts - first_reaction_ts).total_seconds())

        if dose_amount_ml <= 0:
            learning_effect = 0.0

        return {
            "tail_effect": float(tail_effect),
            "peak_effect": peak_effect,
            "peak_value": peak_value,
            "retention_ratio": retention_ratio,
            "wave_score": wave_score,
            "wave_detected": wave_detected,
            "learning_effect": float(max(0.0, learning_effect)),
            "first_reaction_sec": first_reaction_sec,
            "settle_sec": settle_sec,
        }

    def _merge_adaptive_stats(
        self,
        *,
        pid_entry: Mapping[str, Any],
        pid_type: str,
        corr: CorrectionState,
        dose_amount_ml: float,
        learning_effect: float,
        expected_effect: float,
        first_reaction_sec: float | None,
        settle_sec: float | None,
        wave_score: float,
        retention_ratio: float,
    ) -> Mapping[str, Any]:
        stats = dict(pid_entry.get("stats")) if isinstance(pid_entry.get("stats"), Mapping) else {}
        adaptive = dict(stats.get("adaptive")) if isinstance(stats.get("adaptive"), Mapping) else {}
        gains = dict(adaptive.get("gains")) if isinstance(adaptive.get("gains"), Mapping) else {}
        timing = dict(adaptive.get("timing")) if isinstance(adaptive.get("timing"), Mapping) else {}

        gain_key = "ec_gain_per_ml" if pid_type == "ec" else ("ph_up_gain_per_ml" if corr.needs_ph_up else "ph_down_gain_per_ml")
        gain_entry = dict(gains.get(gain_key)) if isinstance(gains.get(gain_key), Mapping) else {}
        gain_observations = int(gain_entry.get("observations") or 0)
        if dose_amount_ml > 0 and learning_effect > 0:
            learned_gain = learning_effect / dose_amount_ml
            gain_entry["ema"] = self._ema(gain_entry.get("ema"), learned_gain, gain_observations)
            gain_entry["observations"] = gain_observations + 1
            gains[gain_key] = gain_entry

        adaptive["gains"] = gains
        adaptive["effectiveness_ema"] = self._ema_ratio(
            adaptive.get("effectiveness_ema"),
            0.0 if expected_effect <= 0 else learning_effect / expected_effect,
            int(adaptive.get("observations") or 0),
        )
        adaptive["retention_ema"] = self._ema_ratio(
            adaptive.get("retention_ema"),
            retention_ratio,
            int(adaptive.get("observations") or 0),
        )
        adaptive["wave_score_ema"] = self._ema_ratio(
            adaptive.get("wave_score_ema"),
            wave_score,
            int(adaptive.get("observations") or 0),
        )
        adaptive["observations"] = int(adaptive.get("observations") or 0) + 1

        timing_observations = int(timing.get("observations") or 0)
        if first_reaction_sec is not None:
            timing["transport_delay_sec_ema"] = self._ema(
                timing.get("transport_delay_sec_ema"),
                first_reaction_sec,
                timing_observations,
            )
            timing_observations += 1
        if settle_sec is not None:
            timing["settle_sec_ema"] = self._ema(
                timing.get("settle_sec_ema"),
                settle_sec,
                max(0, timing_observations - 1),
            )
        timing["observations"] = max(timing_observations, int(timing.get("observations") or 0), 1)
        adaptive["timing"] = timing

        stats["adaptive"] = adaptive
        return stats

    def _ema(self, previous: Any, current: float, observations: int, alpha: float = 0.2) -> float:
        try:
            prev_value = float(previous)
        except (TypeError, ValueError):
            prev_value = current
        if observations <= 0:
            return round(current, 6)
        return round((prev_value * (1.0 - alpha)) + (current * alpha), 6)

    def _ema_ratio(self, previous: Any, current: float, observations: int) -> float:
        return max(0.0, min(1.0, self._ema(previous, current, observations)))

    def _expected_cross_coupling_ph(self, *, corr: CorrectionState, process_cfg: Mapping[str, Any]) -> float:
        gain = self._coerce_float(process_cfg.get("ph_per_ec_ml"))
        if gain is None or corr.ec_amount_ml is None:
            return 0.0
        return float(gain) * float(corr.ec_amount_ml)

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
        try:
            await send_biz_alert(
                code=f"biz_{pid_type}_correction_no_effect",
                alert_type="AE3 Correction No Effect",
                message=(
                    f"{pid_type.upper()} correction produced no observable response "
                    f"{no_effect_limit} times in a row."
                ),
                severity="error",
                zone_id=int(task.zone_id),
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "pid_type": pid_type,
                    "stage": str(getattr(task, "current_stage", "") or ""),
                    "component": f"correction:{task.current_stage}",
                    "baseline_value": baseline_value,
                    "observed_value": observed_value,
                    "expected_effect": expected_effect,
                    "actual_effect": actual_effect,
                    "no_effect_limit": no_effect_limit,
                },
                scope_parts=(f"pid_type:{pid_type}", f"stage:{task.current_stage}"),
            )
        except Exception:
            _logger.warning("Failed to send CORRECTION_NO_EFFECT infra alert zone_id=%s", task.zone_id)
        current_stage = str(task.current_stage).strip().lower()
        if current_stage == "prepare_recirculation_check":
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )
        if current_stage == "solution_fill_check":
            runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_check",
                stage_retry_count=task.workflow.stage_retry_count + 1,
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )
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
        event_payload: dict[str, Any] = dict(payload or {})
        if task is not None:
            task_id = getattr(task, "id", None)
            stage = str(getattr(task, "current_stage", "") or "").strip()
            workflow = getattr(task, "workflow", None)
            workflow_phase = str(getattr(workflow, "workflow_phase", "") or "").strip()
            stage_entered_at = self._serialize_metric_ts(getattr(workflow, "stage_entered_at", None))
            topology = str(getattr(task, "topology", "") or "").strip()
            if task_id is not None:
                event_payload.setdefault("task_id", int(task_id))
            if stage:
                event_payload.setdefault("stage", stage)
            if workflow_phase:
                event_payload.setdefault("workflow_phase", workflow_phase)
            correction_window_id = self._correction_window_id(task=task)
            if correction_window_id:
                event_payload.setdefault("correction_window_id", correction_window_id)
            if stage_entered_at:
                event_payload.setdefault("stage_entered_at", stage_entered_at)
            if topology:
                event_payload.setdefault("topology", topology)
        if corr is not None:
            if corr.corr_step:
                event_payload.setdefault("corr_step", corr.corr_step)
            event_payload.setdefault("attempt", corr.attempt)
            event_payload.setdefault("ec_attempt", corr.ec_attempt)
            event_payload.setdefault("ph_attempt", corr.ph_attempt)
            event_payload.setdefault("ec_max_attempts", corr.ec_max_attempts)
            event_payload.setdefault("ph_max_attempts", corr.ph_max_attempts)
        try:
            await create_zone_event(zone_id, event_type, event_payload)
        except Exception:
            _logger.warning("Failed to log %s zone event", event_type, exc_info=True)

    def _correction_window_id(self, *, task: Any | None) -> str | None:
        if task is None:
            return None
        task_id = getattr(task, "id", None)
        if task_id is None:
            return None
        stage = str(getattr(task, "current_stage", "") or "").strip()
        workflow = getattr(task, "workflow", None)
        workflow_phase = str(getattr(workflow, "workflow_phase", "") or "").strip()
        if not stage or not workflow_phase:
            return None
        return f"task:{int(task_id)}:{workflow_phase}:{stage}"

    def _observe_seq(self, *, corr: CorrectionState, pid_type: str, after_dose: bool = False) -> int | None:
        current = corr.ec_attempt if pid_type == "ec" else corr.ph_attempt
        observe_seq = int(current) + (1 if after_dose else 0)
        return observe_seq if observe_seq > 0 else None

    def _build_sensor_mode_commands(
        self, *, plan: Any, cmd: str, params: Mapping[str, Any],
    ) -> tuple[PlannedCommand, ...]:
        named = plan.named_plans if isinstance(plan.named_plans, Mapping) else {}
        source_key = "sensor_mode_activate" if cmd == "activate_sensor_mode" else "sensor_mode_deactivate"
        templates = named.get(source_key, ())
        return tuple(
            PlannedCommand(
                step_no=t.step_no,
                node_uid=t.node_uid,
                channel=t.channel,
                payload={"cmd": cmd, "params": dict(params)},
            )
            for t in templates
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
            _logger.warning(
                "Failed to persist PID state for zone %s; controller memory not updated",
                zone_id, exc_info=True,
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
