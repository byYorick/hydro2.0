"""PrepareRecircCheckHandler — targets + deadline + correction entry."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


class PrepareRecircCheckHandler(BaseStageHandler):
    """Handles ``prepare_recirculation_check``: probe, targets, correction.

    Outcomes:
    1. Targets reached → ``prepare_recirculation_stop_to_ready``
    2. Targets not reached → enter correction cycle
    3. Deadline exceeded → ``prepare_recirculation_window_exhausted``
    """

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
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
        )

        if pending_manual_step == "prepare_recirculation_stop":
            _logger.info("prepare_recirculation_check: manual stop requested zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )
        if control_mode == "manual":
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

        # Check deadline first (fail-fast)
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.info(
                "prepare_recirculation_check: deadline exceeded, exhausting window zone_id=%s retry=%s",
                task.zone_id, task.workflow.stage_retry_count + 1,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )

        if await self._targets_reached(task=task, plan=plan, now=now):
            _logger.debug("prepare_recirculation_check: targets reached zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )

        # Targets not reached — enter correction.
        _logger.info("prepare_recirculation_check: targets not met, entering correction zone_id=%s", task.zone_id)
        # Sensors already active (activated by prepare_recirculation_start → sensor_mode_activate).
        corr = self._build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=stage_def.on_corr_success or "prepare_recirculation_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "prepare_recirculation_window_exhausted",
        )
        return StageOutcome(kind="enter_correction", correction=corr)

    def _build_correction_state(
        self,
        *,
        task: Any,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        ec_max_attempts = int(correction_cfg.get("max_ec_correction_attempts", 5))
        ph_max_attempts = int(correction_cfg.get("max_ph_correction_attempts", 5))
        return CorrectionState(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            attempt=1,
            max_attempts=int(correction_cfg.get("prepare_recirculation_max_correction_attempts", 20)),
            ec_attempt=0,
            ec_max_attempts=ec_max_attempts,
            ph_attempt=0,
            ph_max_attempts=ph_max_attempts,
            activated_here=not sensors_already_active,
            stabilization_sec=int(correction_cfg.get("stabilization_sec", 60)),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
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
        )
