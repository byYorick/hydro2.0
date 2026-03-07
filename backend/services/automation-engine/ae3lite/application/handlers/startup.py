"""StartupHandler — probe hardware, read clean tank level, route to first fill stage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler


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
