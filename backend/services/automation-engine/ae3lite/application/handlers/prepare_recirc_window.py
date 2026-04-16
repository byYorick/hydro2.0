"""PrepareRecircWindowHandler: остановка текущего окна, retry или fail с alert."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError

_logger = logging.getLogger(__name__)


class PrepareRecircWindowHandler(BaseStageHandler):
    """Управляет rollover-логикой timeout-окна prepare-recirculation."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        alert_repository: Any = None,
        live_reload_enabled: bool = False,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            live_reload_enabled=live_reload_enabled,
        )
        self._alert_repository = alert_repository

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        retry_count = int(task.workflow.stage_retry_count)
        attempt_limit = self._prepare_recirculation_max_attempts(plan=plan, task=task)
        limit_reached = retry_count >= attempt_limit

        current_task = task
        try:
            current_task = await self._run_commands(
                task=current_task,
                plan=plan,
                plan_names=("prepare_recirculation_stop", "sensor_mode_deactivate"),
                now=now,
            )
        except TaskExecutionError as exc:
            if not limit_reached or exc.code not in {"command_timeout", "ae3_command_poll_deadline_exceeded"}:
                raise
            # Audit F4: swallow the stop-command failure ONLY when the retry
            # budget is already exhausted. The fail outcome below reports the
            # primary cause (attempt_limit_reached); the stop-timeout is a
            # secondary symptom of the same stuck window. Explicitly reset
            # current_task to `task` to guarantee no partial mutation reaches
            # the ``task_override`` we pass to the fail outcome below — this
            # is technically a no-op (the assignment on the line above never
            # completed if _run_commands raised), but making it explicit
            # blocks future refactors from introducing phantom state.
            current_task = task
            _logger.warning(
                "prepare_recirc_window: stop-команды завершились ошибкой после достижения лимита повторов; "
                "сохраняется основная ошибка исчерпания лимита zone_id=%s retry=%s/%s code=%s",
                task.zone_id,
                retry_count,
                attempt_limit,
                exc.code,
            )

        if limit_reached:
            _logger.warning(
                "prepare_recirc_window: достигнут лимит повторов retry_count=%s/%s zone_id=%s",
                retry_count, attempt_limit, task.zone_id,
            )
            await self._emit_retry_limit_alert(
                task=current_task,
                retry_count=retry_count,
                attempt_limit=attempt_limit,
                now=now,
            )
            return StageOutcome(
                kind="fail",
                error_code="prepare_recirculation_attempt_limit_reached",
                error_message="Исчерпан лимит повторов подготовки рециркуляции",
                task_override=current_task,
            )

        _logger.info(
            "prepare_recirc_window: окно перезапускается retry=%s/%s zone_id=%s",
            retry_count + 1, attempt_limit, task.zone_id,
        )
        current_task = await self._run_commands(
            task=current_task,
            plan=plan,
            plan_names=("sensor_mode_activate", "prepare_recirculation_start"),
            now=now,
        )
        return StageOutcome(
            kind="transition",
            next_stage="prepare_recirculation_check",
            stage_retry_count=retry_count + 1,
            task_override=current_task,
        )

    def _prepare_recirculation_max_attempts(self, *, plan: Any, task: Any) -> int:
        """Читает лимит из phase correction bundle (``retry.*`` или top-level).

        Missing config — fail-closed: ``prepare_recirculation_max_attempts`` is
        required in ``CorrectionPhaseRuntime`` (RuntimePlan), так что typed
        load гарантирует наличие поля. Legacy raw-dict path также обязан его
        иметь — иначе ``PlannerConfigurationError``.
        """
        correction_cfg = self._correction_config(plan=plan, task=task)
        if isinstance(correction_cfg, Mapping):
            retry = correction_cfg.get("retry")
            if isinstance(retry, Mapping):
                raw = retry.get("prepare_recirculation_max_attempts")
                if raw is not None:
                    return max(1, int(raw))
            raw = correction_cfg.get("prepare_recirculation_max_attempts")
            if raw is not None:
                return max(1, int(raw))
        raise TaskExecutionError(
            "ae3_prepare_recirculation_max_attempts_missing",
            "В bundle коррекции отсутствует обязательный параметр "
            "prepare_recirculation_max_attempts",
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

        await self._alert_repository.raise_active(
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
    ) -> Any:
        commands: list[Any] = []
        named = plan.named_plans if isinstance(plan.named_plans, Mapping) else {}
        for plan_name in plan_names:
            commands.extend(named.get(plan_name, ()))
        if not commands:
            raise TaskExecutionError(
                "ae3_empty_command_plan",
                f"Для окна подготовки рециркуляции не удалось разрешить команды: {plan_names}",
            )
        result = await self._command_gateway.run_batch(task=task, commands=tuple(commands), now=now)
        if not result["success"]:
            raise TaskExecutionError(str(result["error_code"]), str(result["error_message"]))
        return result.get("task") or task

    def _correction_config(self, *, plan: Any, task: Any) -> Mapping[str, Any]:
        runtime = self._require_runtime_plan(plan=plan)
        return self._correction_config_for_task(task=task, runtime=runtime)
