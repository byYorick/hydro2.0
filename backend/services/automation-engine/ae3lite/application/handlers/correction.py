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
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import CorrectionPlanner
from ae3lite.infrastructure.metrics import CORRECTION_ATTEMPT, CORRECTION_EXHAUSTED
from common.db import create_zone_event
from common.infra_alerts import send_infra_alert
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

        deadline_outcome = self._interrupt_for_stage_deadline(task=task, corr=corr, now=now)
        if deadline_outcome is not None:
            return deadline_outcome

        step = corr.corr_step
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

        corr_wait_until = self._normalize_timestamp(corr.wait_until)
        normalized_now = self._normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

        ph_cfg = self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg)
        ec_cfg = self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg)
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
        if not ph["ready"] or not ec["ready"]:
            raise TaskExecutionError(
                "corr_decision_window_not_ready",
                self._format_decision_window_error(ph=ph, ec=ec),
            )

        current_ph = float(ph["value"])
        current_ec = float(ec["value"])

        if not math.isfinite(current_ph) or not math.isfinite(current_ec):
            _logger.warning(
                "zone %s: non-finite telemetry value (ph=%s, ec=%s); retrying in 30s",
                task.zone_id, current_ph, current_ec,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=30.0,
            )

        wl_ok, wl_level = await check_water_level(task.zone_id)
        if not wl_ok:
            _logger.warning(
                "zone %s: water level %.0f%% is below threshold; skipping correction",
                task.zone_id, (wl_level or 0.0) * 100,
            )
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=60.0,
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
            try:
                await create_zone_event(task.zone_id, "CORRECTION_COMPLETE", {
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
                    "attempt": corr.attempt,
                })
            except Exception:
                _logger.warning("Failed to log CORRECTION_COMPLETE zone event", exc_info=True)
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        if corr.attempt >= corr.max_attempts:
            return await self._correction_exhausted(task=task, plan=plan, corr=corr)

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

        if not dose_plan.needs_any and dose_plan.retry_after_sec:
            try:
                await create_zone_event(task.zone_id, "CORRECTION_SKIPPED_COOLDOWN", {
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    "retry_after_sec": dose_plan.retry_after_sec,
                    "attempt": corr.attempt,
                })
            except Exception:
                _logger.warning("Failed to log CORRECTION_SKIPPED_COOLDOWN zone event", exc_info=True)
            next_corr = replace(corr, corr_step="corr_check")
            return StageOutcome(
                kind="enter_correction",
                correction=next_corr,
                due_delay_sec=dose_plan.retry_after_sec,
            )

        if not dose_plan.needs_any:
            if dose_plan.dose_discarded_reason:
                try:
                    await create_zone_event(task.zone_id, "CORRECTION_SKIPPED_DOSE_DISCARDED", {
                        "current_ph": current_ph, "current_ec": current_ec,
                        "target_ph": target_ph, "target_ec": target_ec,
                        "reason": dose_plan.dose_discarded_reason,
                        "attempt": corr.attempt,
                    })
                except Exception:
                    _logger.warning("Failed to log CORRECTION_SKIPPED_DOSE_DISCARDED zone event", exc_info=True)
            try:
                await create_zone_event(task.zone_id, "CORRECTION_SKIPPED_DEAD_ZONE", {
                    "current_ph": current_ph, "current_ec": current_ec,
                    "target_ph": target_ph, "target_ec": target_ec,
                    "attempt": corr.attempt,
                })
            except Exception:
                _logger.warning("Failed to log CORRECTION_SKIPPED_DEAD_ZONE zone event", exc_info=True)
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        if dose_plan.needs_ec and corr.ec_attempt >= corr.ec_max_attempts:
            return await self._correction_exhausted(task=task, plan=plan, corr=corr)
        if (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and corr.ph_attempt >= corr.ph_max_attempts:
            return await self._correction_exhausted(task=task, plan=plan, corr=corr)

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

        if dose_plan.needs_ec:
            next_corr = replace(next_corr, corr_step="corr_dose_ec")
        elif dose_plan.needs_ph_up or dose_plan.needs_ph_down:
            next_corr = replace(next_corr, corr_step="corr_dose_ph")
        else:
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        return StageOutcome(kind="enter_correction", correction=next_corr)

    async def _run_dose_ec(
        self, *, task: Any, plan: Any, corr: CorrectionState, now: datetime,
    ) -> StageOutcome:
        if not corr.ec_node_uid or not corr.ec_channel or not corr.ec_duration_ms:
            raise TaskExecutionError(
                "corr_dose_ec_missing_plan",
                f"EC dose plan missing (node={corr.ec_node_uid}, ch={corr.ec_channel}, ms={corr.ec_duration_ms})",
            )
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step="corr_dose_ec").inc()
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ec_node_uid,
            channel=corr.ec_channel,
            payload={"cmd": "run_pump", "params": {"duration_ms": corr.ec_duration_ms}},
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
        try:
            await create_zone_event(
                task.zone_id,
                "EC_DOSING",
                {
                    "node_uid": corr.ec_node_uid,
                    "channel": corr.ec_channel,
                    "duration_ms": corr.ec_duration_ms,
                    "amount_ml": corr.ec_amount_ml,
                    "ec_component": corr.ec_component,
                    "current_ec": current_ec,
                    "target_ec": runtime.get("target_ec"),
                    "target_ec_min": runtime.get("target_ec_min"),
                    "target_ec_max": runtime.get("target_ec_max"),
                    "attempt": corr.ec_attempt + 1,
                    "source": "correction_handler",
                },
            )
        except Exception:
            _logger.warning("Failed to log EC_DOSING zone event", exc_info=True)

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._correction_config(plan=plan, task=task)
        observe_cfg = self._observation_config(kind="ec", correction_cfg=correction_cfg, process_cfg=process_cfg)
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
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
            ph_amount_ml=None,
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
        if not corr.ph_node_uid or not corr.ph_channel or not corr.ph_duration_ms:
            raise TaskExecutionError(
                "corr_dose_ph_missing_plan",
                f"PH dose plan missing (node={corr.ph_node_uid}, ch={corr.ph_channel}, ms={corr.ph_duration_ms})",
            )
        ph_step = "corr_dose_ph_up" if corr.needs_ph_up else "corr_dose_ph_down"
        CORRECTION_ATTEMPT.labels(topology=task.topology, corr_step=ph_step).inc()
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ph_node_uid,
            channel=corr.ph_channel,
            payload={"cmd": "run_pump", "params": {"duration_ms": corr.ph_duration_ms}},
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
        try:
            await create_zone_event(
                task.zone_id,
                "PH_CORRECTED",
                {
                    "node_uid": corr.ph_node_uid,
                    "channel": corr.ph_channel,
                    "duration_ms": corr.ph_duration_ms,
                    "amount_ml": corr.ph_amount_ml,
                    "direction": ph_direction,
                    "current_ph": current_ph,
                    "target_ph": runtime.get("target_ph"),
                    "target_ph_min": runtime.get("target_ph_min"),
                    "target_ph_max": runtime.get("target_ph_max"),
                    "attempt": corr.ph_attempt + 1,
                    "source": "correction_handler",
                },
            )
        except Exception:
            _logger.warning("Failed to log PH_CORRECTED zone event", exc_info=True)

        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        process_cfg = self._process_cfg_for_task(task=task, runtime=runtime)
        correction_cfg = self._correction_config(plan=plan, task=task)
        observe_cfg = self._observation_config(kind="ph", correction_cfg=correction_cfg, process_cfg=process_cfg)
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
        try:
            await create_zone_event(task.zone_id, "CORRECTION_EXHAUSTED", {
                "attempt": corr.attempt,
                "max_attempts": corr.max_attempts,
                "ec_attempt": corr.ec_attempt,
                "ec_max_attempts": corr.ec_max_attempts,
                "ph_attempt": corr.ph_attempt,
                "ph_max_attempts": corr.ph_max_attempts,
                "stage": stage,
            })
        except Exception:
            _logger.warning("Failed to log CORRECTION_EXHAUSTED zone event", exc_info=True)
        try:
            await send_infra_alert(
                code="biz_correction_exhausted",
                alert_type="AE3 Correction Exhausted",
                message="Correction cycle exhausted all configured attempts.",
                severity="error",
                zone_id=int(task.zone_id),
                service="automation-engine",
                component=f"correction:{stage}",
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": stage,
                    "topology": topology,
                    "attempt": corr.attempt,
                    "max_attempts": corr.max_attempts,
                    "ec_attempt": corr.ec_attempt,
                    "ph_attempt": corr.ph_attempt,
                    "message": "Correction cycle exhausted all dose attempts — check pH/EC dosing hardware.",
                },
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
        observe_cfg = self._observation_config(kind=pid_type, correction_cfg=correction_cfg, process_cfg=process_cfg)
        pid_state = runtime.get("pid_state") if isinstance(runtime.get("pid_state"), Mapping) else {}
        pid_entry = pid_state.get(pid_type) if isinstance(pid_state.get(pid_type), Mapping) else {}
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
            raise TaskExecutionError(
                "corr_telemetry_stale",
                f"{sensor_type} telemetry stale/unavailable during observation window",
            )

        summary = self._summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(observe_cfg["window_min_samples"]),
            stability_max_slope=float(observe_cfg["stability_max_slope"]),
        )
        if not summary["ready"]:
            return StageOutcome(
                kind="enter_correction",
                correction=corr,
                due_delay_sec=int(observe_cfg["observe_poll_sec"]),
            )

        observed_value = float(summary["value"])
        expected_effect = self._expected_effect(
            pid_type=pid_type,
            corr=corr,
            process_cfg=process_cfg,
        )
        directional_effect = self._directional_effect(
            pid_type=pid_type,
            corr=corr,
            baseline_value=float(baseline_value),
            observed_value=observed_value,
        )
        is_no_effect = directional_effect < (expected_effect * float(observe_cfg["min_effect_fraction"]))
        next_no_effect_count = int(pid_entry.get("no_effect_count") or 0) + 1 if is_no_effect else 0
        await self._persist_pid_state_updates(
            zone_id=task.zone_id,
            now=now,
            updates={
                pid_type: {
                    "last_measurement_at": now,
                    "last_measured_value": observed_value,
                    "no_effect_count": next_no_effect_count,
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
            )

        next_corr = replace(
            corr,
            corr_step="corr_check",
            attempt=corr.attempt + 1,
            wait_until=None,
            needs_ec=False,
            ec_node_uid=None,
            ec_channel=None,
            ec_duration_ms=None,
            ec_component=None,
            ec_amount_ml=None,
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
            ph_amount_ml=None,
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
    ) -> StageOutcome:
        try:
            await create_zone_event(task.zone_id, "CORRECTION_NO_EFFECT", {
                "pid_type": pid_type,
                "baseline_value": baseline_value,
                "observed_value": observed_value,
                "expected_effect": expected_effect,
                "attempt": corr.attempt,
            })
        except Exception:
            _logger.warning("Failed to log CORRECTION_NO_EFFECT zone event", exc_info=True)
        try:
            await send_infra_alert(
                code=f"biz_{pid_type}_correction_no_effect",
                alert_type="AE3 Correction No Effect",
                message=f"{pid_type.upper()} correction produced no observable response three times in a row.",
                severity="error",
                zone_id=int(task.zone_id),
                service="automation-engine",
                component=f"correction:{task.current_stage}",
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "pid_type": pid_type,
                    "baseline_value": baseline_value,
                    "observed_value": observed_value,
                    "expected_effect": expected_effect,
                },
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
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
