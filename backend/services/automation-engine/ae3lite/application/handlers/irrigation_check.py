"""Irrigation runtime check handler."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError


class IrrigationCheckHandler(BaseStageHandler):
    def __init__(self, *, runtime_monitor: Any, command_gateway: Any, task_repository: Any) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._task_repository = task_repository

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = plan.runtime if hasattr(plan, "runtime") else {}
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")

        await self._probe_irr_state(
            task=task,
            plan=plan,
            now=now,
            expected={
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        )

        if pending_manual_step == "irrigation_stop":
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")
        if control_mode == "manual":
            return StageOutcome(kind="poll", due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)))

        safety = runtime.get("irrigation_safety") if isinstance(runtime.get("irrigation_safety"), dict) else {}
        recovery = runtime.get("irrigation_recovery") if isinstance(runtime.get("irrigation_recovery"), dict) else {}
        if bool(safety.get("stop_on_solution_min", True)):
            solution_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["solution_min_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
            )
            if solution_min["is_triggered"]:
                max_replays = int(recovery.get("max_setup_replays") or 0)
                next_replay_count = int(getattr(task, "irrigation_replay_count", 0) or 0) + 1
                if next_replay_count > max_replays:
                    return StageOutcome(
                        kind="fail",
                        error_code="irrigation_solution_min_replay_exhausted",
                        error_message="Solution min triggered again after setup replay budget was exhausted",
                    )
                updated = await self._task_repository.update_irrigation_runtime(
                    task_id=int(task.id),
                    owner=str(task.claimed_by or ""),
                    now=now,
                    irrigation_replay_count=next_replay_count,
                )
                if updated is None:
                    raise TaskExecutionError("irrigation_replay_persist_failed", "Unable to persist irrigation replay count")
                return StageOutcome(kind="transition", next_stage="irrigation_stop_to_setup")

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            if await self._targets_reached(task=task, plan=plan, now=now):
                return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_recovery")

        return StageOutcome(kind="poll", due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)))

