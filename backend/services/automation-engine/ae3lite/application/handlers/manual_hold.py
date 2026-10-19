"""ManualHoldHandler — ожидание возврата в auto или manual step после flow-stop (PR7)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.handlers.flow_path_guard import (
    decode_manual_hold_operator_step,
    decode_manual_hold_return_stage,
)

_logger = logging.getLogger(__name__)

# Check требует уже включённый flow-path. После interrupt насос и клапаны OFF,
# поэтому auto-resume после проверок идёт в start.
_FLOW_CHECK_RESUME_START: dict[str, str] = {
    "solution_fill_check": "solution_fill_start",
    "prepare_recirculation_check": "prepare_recirculation_start",
    "clean_fill_check": "clean_fill_start",
    "solution_topup_check": "solution_topup_start",
    "solution_drain_check": "solution_drain_start",
}


def _auto_resume_stage(*, return_stage: str, plan: Any) -> str:
    """Стадия, в которую auto возвращается из manual_hold."""
    if return_stage == "irrigation_check":
        # Interrupt already stopped both pump and valves. A new start would
        # repeat the hydraulic duration; check requires the valves to be ON.
        return "irrigation_stop_to_ready"
    return _FLOW_CHECK_RESUME_START.get(return_stage, return_stage)


class ManualHoldHandler(BaseStageHandler):
    """Poll-stage после принудительной остановки flow-path в manual/semi."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = self._require_runtime_plan(plan=plan)
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "").strip()
        return_stage = decode_manual_hold_return_stage(pending_manual_step)

        if return_stage is None:
            return StageOutcome(
                kind="fail",
                error_code="ae3_manual_hold_return_stage_missing",
                error_message="manual_hold без сохранённого return stage",
            )

        if control_mode == "auto":
            if self._deadline_reached(now=now, deadline=task.workflow.stage_deadline_at):
                return StageOutcome(
                    kind="fail", error_code="ae3_manual_hold_deadline_exceeded",
                    error_message=f"Превышен deadline manual_hold для stage {return_stage}",
                )
            next_stage = _auto_resume_stage(return_stage=return_stage, plan=plan)
            if return_stage == "irrigation_check":
                target_snapshot = await self._target_outcome_on_deadline(
                    task=task, plan=plan, now=now, runtime=runtime,
                )
                await self._record_deadline_target_outcome(
                    task=task, snapshot=target_snapshot, reason="manual_hold_irrigation_stopped",
                )
            else:
                await self._validate_resume_levels(task=task, runtime=runtime, return_stage=return_stage)
            _logger.info(
                "manual_hold: control_mode=auto, возврат в stage=%s (saved=%s) zone_id=%s task_id=%s",
                next_stage,
                return_stage,
                task.zone_id,
                task.id,
            )
            return StageOutcome(kind="transition", next_stage=next_stage, due_delay_sec=0)

        from ae3lite.application.use_cases.manual_control_contract import (
            allowed_manual_steps_for_stage,
        )

        operator_step = decode_manual_hold_operator_step(pending_manual_step)
        if operator_step:
            allowed = allowed_manual_steps_for_stage(return_stage)
            if operator_step in allowed:
                _logger.info(
                    "manual_hold: manual step=%s на return_stage=%s zone_id=%s",
                    operator_step,
                    return_stage,
                    task.zone_id,
                )
                return StageOutcome(kind="transition", next_stage=return_stage, due_delay_sec=0)

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            return StageOutcome(
                kind="fail",
                error_code="ae3_manual_hold_deadline_exceeded",
                error_message=f"Превышен deadline manual_hold для stage {return_stage}",
            )

        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.level_poll_interval_sec),
        )

    async def _validate_resume_levels(self, *, task: Any, runtime: Any, return_stage: str) -> None:
        """Fresh levels are mandatory before reopening an interrupted path."""
        from ae3lite.domain.errors import TaskExecutionError

        requirements = {
            "clean_fill_check": (("clean_max", False),),
            "solution_fill_check": (("solution_max", False), ("clean_min", True)),
            "solution_topup_check": (("solution_max", False), ("clean_min", True), ("solution_min", True)),
            "prepare_recirculation_check": (("solution_min", True),),
            "solution_drain_check": (("solution_min", True),),
        }
        for sensor, expected in requirements.get(return_stage, ()):
            level = await self._read_level(
                task=task, zone_id=task.zone_id,
                labels=getattr(runtime, f"{sensor}_sensor_labels"),
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="ae3_manual_resume_level_unavailable",
                stale_error="ae3_manual_resume_level_stale",
            )
            if bool(level["is_triggered"]) != expected:
                raise TaskExecutionError(
                    "ae3_manual_resume_level_guard",
                    f"Возобновление {return_stage} запрещено по датчику {sensor}",
                )
