"""Handler recovery после полива."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


class IrrigationRecoveryCheckHandler(BaseStageHandler):
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
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")

        probe_outcome = await self._probe_irr_state_with_backoff(
            task=task, plan=plan, now=now,
            expected={
                "valve_irrigation": False,
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
            poll_delay_sec=int(runtime.level_poll_interval_sec),
            exhausted_outcome=StageOutcome(
                kind="fail",
                error_code="irrigation_recovery_probe_exhausted",
                error_message="IRR-нода недоступна: исчерпан лимит подряд идущих probe-deferrals",
            ),
        )
        if probe_outcome is not None:
            return probe_outcome

        if pending_manual_step == "irrigation_recovery_stop":
            return StageOutcome(kind="transition", next_stage="irrigation_recovery_stop_to_ready")
        if control_mode == "manual":
            return StageOutcome(kind="poll", due_delay_sec=int(runtime.level_poll_interval_sec))

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            return StageOutcome(
                kind="fail",
                error_code="irrigation_recovery_timeout",
                error_message="Превышено время этапа восстановления после полива",
            )

        if await self._targets_reached(task=task, plan=plan, now=now):
            return StageOutcome(kind="transition", next_stage="irrigation_recovery_stop_to_ready")

        _logger.info("irrigation_recovery_check: цели не достигнуты, переход в correction zone_id=%s", task.zone_id)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        ec_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ec_correction_attempts",
        )
        ph_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ph_correction_attempts",
        )
        corr = CorrectionState.build_default(
            corr_step="corr_check",
            max_attempts=max(ec_max_attempts, ph_max_attempts),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=ph_max_attempts,
            activated_here=False,
            stabilization_sec=self._required_correction_int(
                correction_cfg=correction_cfg,
                key="stabilization_sec",
            ),
            return_stage_success=stage_def.on_corr_success or "irrigation_recovery_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "irrigation_recovery_stop_failed",
        )
        corr = replace(corr, **self._probe_snapshot_correction_fields(task=task))
        return StageOutcome(kind="enter_correction", correction=corr)
