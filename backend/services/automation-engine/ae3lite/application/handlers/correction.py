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

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import CorrectionPlanner


class CorrectionHandler(BaseStageHandler):
    """Handles all ``corr_*`` steps within the correction state machine."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        planner: Optional[CorrectionPlanner] = None,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
        )
        self._planner = planner or CorrectionPlanner()

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
        tolerance = runtime.get("prepare_tolerance") if isinstance(runtime.get("prepare_tolerance"), Mapping) else {}
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
        ):
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        if corr.attempt > corr.max_attempts:
            return self._transition_to_deactivate_or_return(corr=corr, success=False)

        # Build dose plan
        correction_cfg = runtime.get("correction") if isinstance(runtime.get("correction"), Mapping) else {}
        actuators = self._resolve_actuators(runtime)
        dose_plan = self._planner.build_dose_plan(
            current_ph=current_ph, current_ec=current_ec,
            target_ph=target_ph, target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct, ec_tolerance_pct=ec_tol_pct,
            correction_config=correction_cfg,
            ec_actuator=actuators.get("ec"),
            ph_up_actuator=actuators.get("ph_up"),
            ph_down_actuator=actuators.get("ph_down"),
        )

        if not dose_plan.needs_any:
            return self._transition_to_deactivate_or_return(corr=corr, success=True)

        # Save dose plan into correction state
        next_corr = replace(
            corr,
            needs_ec=dose_plan.needs_ec,
            ec_node_uid=dose_plan.ec_node_uid,
            ec_channel=dose_plan.ec_channel,
            ec_duration_ms=dose_plan.ec_duration_ms,
            needs_ph_up=dose_plan.needs_ph_up,
            needs_ph_down=dose_plan.needs_ph_down,
            ph_node_uid=dose_plan.ph_node_uid,
            ph_channel=dose_plan.ph_channel,
            ph_duration_ms=dose_plan.ph_duration_ms,
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
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ec_node_uid,
            channel=corr.ec_channel,
            payload={"cmd": "run_pump", "params": {"duration_ms": corr.ec_duration_ms}},
        )
        result = await self._command_gateway.run_batch(task=task, commands=(cmd,), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))

        correction_cfg = self._correction_config(plan)
        ec_mix_wait = int(correction_cfg.get("ec_mix_wait_sec", 120))
        next_corr = replace(corr, corr_step="corr_wait_ec")
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
        cmd = PlannedCommand(
            step_no=1,
            node_uid=corr.ph_node_uid,
            channel=corr.ph_channel,
            payload={"cmd": "run_pump", "params": {"duration_ms": corr.ph_duration_ms}},
        )
        result = await self._command_gateway.run_batch(task=task, commands=(cmd,), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))

        correction_cfg = self._correction_config(plan)
        ph_mix_wait = int(correction_cfg.get("ph_mix_wait_sec", 60))
        next_corr = replace(corr, corr_step="corr_wait_ph")
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
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
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
        return StageOutcome(kind="exit_correction", next_stage=next_stage)

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
        return StageOutcome(kind="exit_correction", next_stage=next_stage)

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

    def _correction_config(self, plan: Any) -> Mapping[str, Any]:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        correction = runtime.get("correction")
        return correction if isinstance(correction, Mapping) else {}

    def _resolve_actuators(self, runtime: Mapping[str, Any]) -> dict:
        corr = runtime.get("correction") if isinstance(runtime.get("correction"), Mapping) else {}
        actuators = corr.get("actuators") if isinstance(corr.get("actuators"), Mapping) else {}
        return {
            "ec": actuators.get("ec"),
            "ph_up": actuators.get("ph_up"),
            "ph_down": actuators.get("ph_down"),
        }
