"""Await-ready stage for irrigation tasks."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler


_WAIT_READY_TIMEOUT_SEC = max(30, int(os.getenv("AE_IRRIGATION_WAIT_READY_SEC", "1800")))
_WAIT_READY_POLL_SEC = max(1, int(os.getenv("AE_IRRIGATION_WAIT_READY_POLL_SEC", "10")))


class AwaitReadyHandler(BaseStageHandler):
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
        workflow_phase = str(runtime.get("zone_workflow_phase") or "").strip().lower()
        if workflow_phase == "ready":
            return StageOutcome(kind="transition", next_stage="decision_gate")

        deadline = task.irrigation_wait_ready_deadline_at
        if deadline is None and getattr(task, "claimed_by", None):
            await self._task_repository.update_irrigation_runtime(
                task_id=int(task.id),
                owner=str(task.claimed_by or ""),
                now=now,
                irrigation_wait_ready_deadline_at=now.replace(microsecond=0) + timedelta(seconds=_WAIT_READY_TIMEOUT_SEC),
            )
            return StageOutcome(kind="poll", due_delay_sec=_WAIT_READY_POLL_SEC)

        if self._deadline_reached(now=now, deadline=deadline):
            return StageOutcome(
                kind="fail",
                error_code="irrigation_wait_ready_timeout",
                error_message="Irrigation request timed out while waiting for READY state",
            )

        return StageOutcome(kind="poll", due_delay_sec=_WAIT_READY_POLL_SEC)
