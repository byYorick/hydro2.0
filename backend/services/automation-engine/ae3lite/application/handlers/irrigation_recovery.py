"""Post-irrigation recovery handler."""

from __future__ import annotations

import logging
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
        runtime = plan.runtime
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")

        await self._probe_irr_state(
            task=task, plan=plan, now=now,
            expected={
                "valve_irrigation": False,
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
        )

        if pending_manual_step == "irrigation_recovery_stop":
            return StageOutcome(kind="transition", next_stage="irrigation_recovery_stop_to_ready")
        if control_mode == "manual":
            return StageOutcome(kind="poll", due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)))

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            return StageOutcome(
                kind="fail",
                error_code="irrigation_recovery_timeout",
                error_message="Irrigation recovery timeout exceeded",
            )

        if await self._targets_reached(task=task, plan=plan, now=now):
            return StageOutcome(kind="transition", next_stage="irrigation_recovery_stop_to_ready")

        _logger.info("irrigation_recovery_check: targets not met, entering correction zone_id=%s", task.zone_id)
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        corr = CorrectionState(
            corr_step="corr_check",
            attempt=0,
            max_attempts=max(
                int(correction_cfg.get("max_ec_correction_attempts", 5)),
                int(correction_cfg.get("max_ph_correction_attempts", 5)),
            ),
            ec_attempt=0,
            ec_max_attempts=int(correction_cfg.get("max_ec_correction_attempts", 5)),
            ph_attempt=0,
            ph_max_attempts=int(correction_cfg.get("max_ph_correction_attempts", 5)),
            activated_here=False,
            stabilization_sec=int(correction_cfg.get("stabilization_sec", 60)),
            return_stage_success=stage_def.on_corr_success or "irrigation_recovery_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "irrigation_recovery_stop_failed",
            outcome_success=None,
            needs_ec=False,
            ec_node_uid=None,
            ec_channel=None,
            ec_duration_ms=None,
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
            wait_until=None,
            limit_policy_logged=False,
        )
        return StageOutcome(kind="enter_correction", correction=corr)
