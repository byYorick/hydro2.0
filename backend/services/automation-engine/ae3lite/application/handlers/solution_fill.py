"""SolutionFillCheckHandler — level + targets + correction entry."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


class SolutionFillCheckHandler(BaseStageHandler):
    """Handles ``solution_fill_check``: probe, level sensor, targets, correction.

    Outcomes:
    1. Tank full + targets reached → ``solution_fill_stop_to_ready``
    2. Tank full + targets not reached → enter correction cycle
    3. Deadline exceeded → ``solution_fill_timeout_stop``
    4. Still filling → poll
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

        await self._probe_irr_state(
            task=task, plan=plan, now=now,
            expected={
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
        )

        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["solution_max_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
        )

        if solution_max["is_triggered"]:
            # Tank full — check consistency
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="solution_min_sensor_labels",
                min_unavailable_error="two_tank_solution_min_level_unavailable",
                min_stale_error="two_tank_solution_min_level_stale",
            )

            if await self._targets_reached(task=task, plan=plan):
                _logger.debug("solution_fill_check: targets reached, stopping fill zone_id=%s", task.zone_id)
                return StageOutcome(
                    kind="transition",
                    next_stage="solution_fill_stop_to_ready",
                )

            # Targets not met — enter correction.
            _logger.info("solution_fill_check: tank full but targets not met, entering correction zone_id=%s", task.zone_id)
            # Sensors already active (activated by solution_fill_start → sensor_mode_activate).
            # on_corr_success → stop fill → ready
            # on_corr_fail → stop fill → prepare_recirculation
            corr = self._build_correction_state(
                task=task,
                runtime=runtime,
                sensors_already_active=True,
                return_stage_success=stage_def.on_corr_success or "solution_fill_stop_to_ready",
                return_stage_fail=stage_def.on_corr_fail or "solution_fill_stop_to_prepare",
            )
            return StageOutcome(kind="enter_correction", correction=corr)

        # Check deadline
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning("solution_fill_check: deadline exceeded, stopping zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="solution_fill_timeout_stop")

        # Still filling — poll
        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
        )

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
            max_attempts=max(ec_max_attempts, ph_max_attempts),
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
