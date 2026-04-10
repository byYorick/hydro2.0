"""CommandHandler: выполняет batch команд через gateway и маршрутизирует по StageDef."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError

_logger = logging.getLogger(__name__)


class CommandHandler(BaseStageHandler):
    """Выполняет batch команд из ``StageDef.command_plans`` и затем маршрутизирует.

    После завершения run_batch:
    - если задан ``StageDef.terminal_error`` → вернуть fail с этой ошибкой
    - если задан ``StageDef.next_stage`` → перейти в следующий stage
    """

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        commands = self._resolve_commands(plan=plan, stage_def=stage_def)
        _logger.debug(
            "command_handler: running batch stage=%s commands=%s zone_id=%s",
            stage_def.name, len(commands), task.zone_id,
        )
        result = await self._command_gateway.run_batch(
            task=task, commands=commands, now=now,
        )
        if not result["success"]:
            _logger.warning(
                "command_handler: batch failed stage=%s error=%s zone_id=%s",
                stage_def.name, result.get("error_code"), task.zone_id,
            )
            raise TaskExecutionError(
                str(result["error_code"]), str(result["error_message"]),
            )

        _logger.debug(
            "command_handler: batch succeeded stage=%s commands_total=%s zone_id=%s",
            stage_def.name, result.get("commands_total", 0), task.zone_id,
        )
        # После run_batch задача снова находится в `running` с тем же current_stage.
        # Маршрутизация берётся из topology registry (StageDef), а не из состояния задачи.
        if stage_def.terminal_error is not None:
            error_code, error_message = stage_def.terminal_error
            return StageOutcome(
                kind="fail",
                error_code=error_code,
                error_message=error_message,
            )

        if stage_def.next_stage is not None:
            return StageOutcome(
                kind="transition",
                next_stage=stage_def.next_stage,
                task_override=result.get("task"),
            )

        raise TaskExecutionError(
            "ae3_command_no_routing",
            f"Command stage {stage_def.name} has no next_stage or terminal_error",
        )

    def _resolve_commands(self, *, plan: Any, stage_def: Any) -> tuple:
        """Разрешает имена command plan из StageDef в кортежи PlannedCommand."""
        named = plan.named_plans if hasattr(plan, "named_plans") else {}
        result: list = []
        for plan_name in stage_def.command_plans:
            cmds = named.get(plan_name, ())
            result.extend(cmds)
        if not result:
            raise TaskExecutionError(
                "ae3_empty_command_plan",
                f"No commands resolved for stage {stage_def.name}, plans={stage_def.command_plans}",
            )
        return tuple(result)
