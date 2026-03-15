"""CleanFillCheckHandler — level polling, deadline, retry logic."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.infra_alerts import send_infra_alert

_logger = logging.getLogger(__name__)


class CleanFillCheckHandler(BaseStageHandler):
    """Handles ``clean_fill_check``: poll level sensor, manage deadline and retries.

    Four possible outcomes:
    1. Tank full → transition to ``clean_fill_stop_to_solution``
    2. Deadline exceeded + retries available → transition to ``clean_fill_retry_stop``
    3. Deadline exceeded + no retries → transition to ``clean_fill_timeout_stop``
    4. Still waiting → poll (re-enqueue with delay)
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

        if pending_manual_step == "clean_fill_stop":
            _logger.info("clean_fill_check: manual stop requested zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_stop_to_solution")
        if control_mode == "manual":
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

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
            # Tank full — verify sensor consistency
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="clean_min_sensor_labels",
                min_unavailable_error="two_tank_clean_min_level_unavailable",
                min_stale_error="two_tank_clean_min_level_stale",
            )
            _logger.debug("clean_fill_check: clean tank full, transitioning zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_stop_to_solution")

        # Check deadline
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            cycle = max(1, task.workflow.clean_fill_cycle)
            retry_limit = 1 + int(runtime.get("clean_fill_retry_cycles", 0))
            if cycle < retry_limit:
                # Retry: increment cycle, new deadline will be set by WorkflowRouter
                _logger.info(
                    "clean_fill_check: deadline exceeded, retrying cycle=%s/%s zone_id=%s",
                    cycle + 1, retry_limit, task.zone_id,
                )
                return StageOutcome(
                    kind="transition",
                    next_stage="clean_fill_retry_stop",
                    clean_fill_cycle=cycle + 1,
                )
            # Max retries exceeded — terminal timeout
            _logger.warning(
                "clean_fill_check: deadline exceeded, max retries reached cycle=%s zone_id=%s",
                cycle, task.zone_id,
            )
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="clean_fill_check",
            ).inc()
            try:
                await send_infra_alert(
                    code="biz_clean_fill_timeout",
                    alert_type="AE3 Clean Fill Timeout",
                    message="Clean tank fill deadline exceeded after all retry cycles.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    service="automation-engine",
                    component="handler:clean_fill_check",
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "cycle": cycle,
                        "retry_limit": retry_limit,
                        "message": "Clean tank fill deadline exceeded after all retry cycles — check water supply.",
                    },
                )
            except Exception:
                _logger.warning("Failed to send clean_fill_timeout alert zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_timeout_stop")

        # Still filling — poll again
        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
        )
