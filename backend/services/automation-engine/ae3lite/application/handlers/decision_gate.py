"""Decision gate for irrigation tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError


class DecisionGateHandler(BaseStageHandler):
    def __init__(self, *, runtime_monitor: Any, command_gateway: Any, task_repository: Any, decision_controller: Any) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._task_repository = task_repository
        self._decision_controller = decision_controller

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        owner = str(getattr(task, "claimed_by", "") or "")
        decision = await self._decision_controller.evaluate(
            zone_id=int(task.zone_id),
            runtime_monitor=self._runtime_monitor,
            runtime=plan.runtime if hasattr(plan, "runtime") else {},
            mode=str(getattr(task, "irrigation_mode", None) or "normal"),
            requested_duration_sec=getattr(task, "irrigation_requested_duration_sec", None),
            now=now,
        )
        updated = await self._task_repository.update_irrigation_runtime(
            task_id=int(task.id),
            owner=owner,
            now=now,
            irrigation_decision_strategy=str(
                ((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy")
            ),
            irrigation_decision_outcome=decision.outcome,
            irrigation_decision_reason_code=decision.reason_code,
            irrigation_decision_degraded=decision.degraded,
        )
        if updated is None:
            raise TaskExecutionError("irrigation_decision_persist_failed", "Unable to persist irrigation decision")

        if decision.outcome == "skip":
            return StageOutcome(kind="transition", next_stage="completed_skip")
        if decision.outcome == "fail":
            return StageOutcome(
                kind="fail",
                error_code=decision.reason_code,
                error_message="Irrigation decision-controller returned fail",
            )
        return StageOutcome(kind="transition", next_stage="irrigation_start")

