"""PrepareRecircCheckHandler — targets + deadline + correction entry."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState


class PrepareRecircCheckHandler(BaseStageHandler):
    """Handles ``prepare_recirculation_check``: probe, targets, correction.

    Outcomes:
    1. Targets reached → ``prepare_recirculation_stop_to_ready``
    2. Targets not reached → enter correction cycle
    3. Deadline exceeded → ``prepare_recirculation_timeout_stop``
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
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
        )

        # Check deadline first (fail-fast)
        deadline = task.workflow.stage_deadline_at
        if deadline is not None and now >= deadline:
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_timeout_stop",
            )

        if await self._targets_reached(task=task, plan=plan):
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )

        # Targets not reached — enter correction.
        # Sensors already active (activated by prepare_recirculation_start → sensor_mode_activate).
        corr = self._build_correction_state(
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=stage_def.on_corr_success or "prepare_recirculation_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "prepare_recirculation_timeout_stop",
        )
        return StageOutcome(kind="enter_correction", correction=corr)

    def _build_correction_state(
        self,
        *,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        correction_cfg = runtime.get("correction") if isinstance(runtime.get("correction"), dict) else {}
        return CorrectionState(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            attempt=1,
            max_attempts=int(correction_cfg.get("max_correction_attempts", 5)),
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
