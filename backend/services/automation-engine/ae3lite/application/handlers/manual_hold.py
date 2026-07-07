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
            _logger.info(
                "manual_hold: control_mode=auto, возврат в stage=%s zone_id=%s task_id=%s",
                return_stage,
                task.zone_id,
                task.id,
            )
            return StageOutcome(kind="transition", next_stage=return_stage, due_delay_sec=0)

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
