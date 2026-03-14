"""CorrectionHandler — 8-step PH/EC correction state machine.

Replaces CorrectionExecutor v1 by reading/writing explicit CorrectionState
fields instead of payload JSONB keys.

Protocol (per CORRECTION_CYCLE_SPEC.md):
  1. corr_activate   — activate PH/EC sensor nodes
  2. corr_wait_stable — wait for sensor stabilization
  3. corr_check      — read PH/EC, decide: done / dose EC / dose PH / give up
  4. corr_dose_ec    — issue EC dose pulse
  5. corr_wait_ec    — wait for EC mixing
  6. corr_dose_ph    — issue PH dose pulse
  7. corr_wait_ph    — wait for PH mixing, then bump attempt → corr_check
  8. corr_deactivate — deactivate sensor nodes, return to parent stage
"""

from __future__ import annotations

import logging
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
            return self._run_wait_ec(corr=corr)
        if step == "corr_dose_ph":
            return await self._run_dose_ph(task=task, plan=plan, corr=corr, now=now)
        if step == "corr_wait_ph":
            return self._run_wait_ph(corr=corr)
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

        ph = await self._runtime_monitor.read_metric(
            zone_id=task.zone_id, sensor_type="PH", telemetry_max_age_sec=max_age,
        )
        ec = await self._runtime_monitor.read_metric(
            zone_id=task.zone_id, sensor_type="EC", telemetry_max_age_sec=max_age,
        )
        if not ph["has_value"] or not ec["has_value"]:
            raise TaskExecutionError(
                "corr_telemetry_unavailable",
                "PH/EC telemetry unavailable during correction check",
            )
        if ph["is_stale"] or ec["is_stale"]:
            raise TaskExecutionError(
                "corr_telemetry_stale",
                "PH/EC telemetry stale during correction check",
            )

        current_ph = float(ph["value"])
        current_ec = float(ec["value"])

        if self._planner.is_within_tolerance(
            current_ph=current_ph, current_ec=current_ec,
            target_ph=target_ph, target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
            ph_min=self._float_or_none(runtime.get("target_ph_min")),
            ph_max=self._float_or_none(runtime.get("target_ph_max")),
            ec_min=self._float_or_none(runtime.get("target_ec_min")),
            ec_max=self._float_or_none(runtime.get("target_ec_max")),
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
        correction_cfg = self._correction_config(plan=plan, task=task)
        actuators = self._resolve_actuators(runtime=runtime, task=task, plan=plan)
        dose_plan = self._planner.build_dose_plan(
            current_ph=current_ph, current_ec=current_ec,
            target_ph=target_ph, target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
            correction_config=correction_cfg,
            workflow_phase=task.workflow.workflow_phase,
            process_calibrations=runtime.get("process_calibrations"),
            ec_component_policy=correction_cfg.get("ec_component_policy"),
            pid_state=runtime.get("pid_state"),
            now=now,
            ph_min=self._float_or_none(runtime.get("target_ph_min")),
            ph_max=self._float_or_none(runtime.get("target_ph_max")),
            ec_min=self._float_or_none(runtime.get("target_ec_min")),
            ec_max=self._float_or_none(runtime.get("target_ec_max")),
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

        correction_cfg = self._correction_config(plan=plan, task=task)
        ec_mix_wait = int(correction_cfg.get("ec_mix_wait_sec", 120))
        next_corr = replace(corr, corr_step="corr_wait_ec", ec_attempt=corr.ec_attempt + 1)
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=ec_mix_wait,
        )

    def _run_wait_ec(self, *, corr: CorrectionState) -> StageOutcome:
        if corr.needs_ph_up or corr.needs_ph_down:
            next_corr = replace(corr, corr_step="corr_dose_ph")
        else:
            next_corr = replace(corr, corr_step="corr_check", attempt=corr.attempt + 1)
        return StageOutcome(kind="enter_correction", correction=next_corr)

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

        correction_cfg = self._correction_config(plan=plan, task=task)
        ph_mix_wait = int(correction_cfg.get("ph_mix_wait_sec", 60))
        next_corr = replace(corr, corr_step="corr_wait_ph", ph_attempt=corr.ph_attempt + 1)
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=ph_mix_wait,
        )

    def _run_wait_ph(self, *, corr: CorrectionState) -> StageOutcome:
        next_corr = replace(
            corr,
            corr_step="corr_check",
            attempt=corr.attempt + 1,
            # Clear stale dose plan for recomputation
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
        await self._pid_state_repository.upsert_states(
            zone_id=int(zone_id),
            now=now,
            updates=[
                {"pid_type": pid_type, **state_dict}
                for pid_type, state_dict in updates.items()
            ],
        )

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None
