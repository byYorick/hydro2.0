"""PrepareRecircWindowHandler — stop current window, retry or fail with alert."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError

_logger = logging.getLogger(__name__)


class PrepareRecircWindowHandler(BaseStageHandler):
    """Owns prepare-recirculation timeout-window rollover logic."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        alert_repository: Any = None,
    ) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._alert_repository = alert_repository

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        await self._run_commands(task=task, plan=plan, plan_names=("prepare_recirculation_stop", "sensor_mode_deactivate"), now=now)

        retry_count = int(task.workflow.stage_retry_count)
        correction_cfg = self._correction_config(plan=plan, task=task)
        attempt_limit = int(correction_cfg.get("prepare_recirculation_max_attempts", 3))
        if retry_count >= attempt_limit:
            _logger.warning(
                "prepare_recirc_window: retry limit reached retry_count=%s/%s zone_id=%s",
                retry_count, attempt_limit, task.zone_id,
            )
            await self._emit_retry_limit_alert(
                task=task,
                retry_count=retry_count,
                attempt_limit=attempt_limit,
                now=now,
            )
            return StageOutcome(
                kind="fail",
                error_code="prepare_recirculation_attempt_limit_reached",
                error_message="Prepare recirculation retry limit reached",
            )

        _logger.info(
            "prepare_recirc_window: rolling over window retry=%s/%s zone_id=%s",
            retry_count + 1, attempt_limit, task.zone_id,
        )
        await self._run_commands(task=task, plan=plan, plan_names=("sensor_mode_activate", "prepare_recirculation_start"), now=now)
        return StageOutcome(
            kind="transition",
            next_stage="prepare_recirculation_check",
            stage_retry_count=retry_count,
        )

    async def _emit_retry_limit_alert(
        self,
        *,
        task: Any,
        retry_count: int,
        attempt_limit: int,
        now: datetime,
    ) -> None:
        if self._alert_repository is None:
            return

        await self._alert_repository.create_or_update_active(
            zone_id=task.zone_id,
            code="biz_prepare_recirculation_retry_exhausted",
            details={
                "retry_count": retry_count,
                "attempt_limit": attempt_limit,
                "task_id": task.id,
                "stage": task.current_stage,
                "workflow_phase": task.workflow_phase,
                "topology": task.topology,
                "message": f"Превышен лимит попыток подготовки рециркуляции ({retry_count}/{attempt_limit})",
            },
            now=now,
        )

    async def _run_commands(
        self,
        *,
        task: Any,
        plan: Any,
        plan_names: tuple[str, ...],
        now: datetime,
    ) -> None:
        commands: list[Any] = []
        named = plan.named_plans if isinstance(plan.named_plans, Mapping) else {}
        for plan_name in plan_names:
            commands.extend(named.get(plan_name, ()))
        if not commands:
            raise TaskExecutionError(
                "ae3_empty_command_plan",
                f"No commands resolved for prepare recirculation window flow: {plan_names}",
            )
        result = await self._command_gateway.run_batch(task=task, commands=tuple(commands), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))

    def _correction_config(self, *, plan: Any, task: Any) -> Mapping[str, Any]:
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        return self._correction_config_for_task(task=task, runtime=runtime)
