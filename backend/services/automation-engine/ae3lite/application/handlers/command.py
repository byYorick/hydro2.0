"""CommandHandler — execute command batch via gateway, route using StageDef."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError


class CommandHandler(BaseStageHandler):
    """Executes command batch defined by ``StageDef.command_plans``, then routes.

    After run_batch completes:
    - If ``StageDef.terminal_error`` is set → fail with that error
    - If ``StageDef.next_stage`` is set → transition to next stage
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
        result = await self._command_gateway.run_batch(
            task=task, commands=commands, now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]), str(result["error_message"]),
            )

        # After run_batch, task is back in 'running' with same current_stage.
        # Routing comes from topology registry (StageDef), not from task state.
        if stage_def.terminal_error is not None:
            error_code, error_message = stage_def.terminal_error
            return StageOutcome(
                kind="fail",
                error_code=error_code,
                error_message=error_message,
            )

        if stage_def.next_stage is not None:
            return StageOutcome(kind="transition", next_stage=stage_def.next_stage)

        raise TaskExecutionError(
            "ae3_command_no_routing",
            f"Command stage {stage_def.name} has no next_stage or terminal_error",
        )

    def _resolve_commands(self, *, plan: Any, stage_def: Any) -> tuple:
        """Resolve command plan names from StageDef into PlannedCommand tuples."""
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
