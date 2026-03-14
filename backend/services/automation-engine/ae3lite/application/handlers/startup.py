"""StartupHandler — probe hardware, read clean tank level, route to first fill stage."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError

logger = logging.getLogger(__name__)

class StartupHandler(BaseStageHandler):
    """Handles the ``startup`` stage: probe + level check + conditional routing."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        try:
            await self._probe_irr_state(
                task=task, plan=plan, now=now, expected={"pump_main": False},
            )
        except TaskExecutionError as exc:
            if exc.code != "irr_state_mismatch" or "pump_main" not in str(exc):
                raise
            await self._run_startup_safety_stop(task=task, plan=plan, now=now)
            await self._probe_irr_state(
                task=task, plan=plan, now=now, expected={"pump_main": False},
            )
        runtime = plan.runtime

        clean_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["clean_max_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error="two_tank_clean_level_unavailable",
            stale_error="two_tank_clean_level_stale",
        )
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()

        if control_mode in ("manual", "semi"):
            if clean_max["is_triggered"] and pending_manual_step == "solution_fill_start":
                await self._check_sensor_consistency(
                    task=task,
                    runtime=runtime,
                    min_labels_key="clean_min_sensor_labels",
                    min_unavailable_error="two_tank_clean_min_level_unavailable",
                    min_stale_error="two_tank_clean_min_level_stale",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_start")
            if not clean_max["is_triggered"] and pending_manual_step == "clean_fill_start":
                return StageOutcome(
                    kind="transition",
                    next_stage="clean_fill_start",
                    clean_fill_cycle=1,
                )
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 5)),
            )

        if clean_max["is_triggered"]:
            # Clean tank full — verify consistency, skip to solution fill
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="clean_min_sensor_labels",
                min_unavailable_error="two_tank_clean_min_level_unavailable",
                min_stale_error="two_tank_clean_min_level_stale",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_start")

        # Clean tank not full — start clean fill cycle
        return StageOutcome(
            kind="transition",
            next_stage="clean_fill_start",
            clean_fill_cycle=1,
        )

    async def _run_startup_safety_stop(self, *, task: Any, plan: Any, now: datetime) -> None:
        safety_plan = tuple(plan.named_plans.get("solution_fill_stop", ()))
        if not safety_plan:
            safety_plan = tuple(plan.named_plans.get("clean_fill_stop", ()))
        if not safety_plan:
            raise TaskExecutionError(
                "irr_state_mismatch",
                "IRR state mismatch for pump_main and no safety stop plan configured",
            )

        result = await self._command_gateway.run_batch(
            task=task,
            commands=safety_plan,
            now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]),
                str(result["error_message"]),
            )
