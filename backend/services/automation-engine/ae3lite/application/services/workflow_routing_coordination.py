"""WorkflowRouter coordination: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.claim_fence import same_claim_token
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.hydraulics.dispatch import assert_stage_dispatch
from ae3lite.hydraulics.failure_report import (
    publish_upward_reports,
)
from ae3lite.infrastructure.log_context import log_context_scope


@dataclass(frozen=True)
class WorkflowRoutingCoordinationPorts:
    apply_enter_correction: Callable[..., Awaitable[Any]]
    apply_exit_correction: Callable[..., Awaitable[Any]]
    apply_poll: Callable[..., Awaitable[Any]]
    apply_transition: Callable[..., Awaitable[Any]]
    complete_task: Callable[..., Awaitable[Any]]
    extract_irrig_node_uid_from_plan: Callable[..., Any]
    fail_task: Callable[..., Awaitable[Any]]
    handlers: Callable[[], Any]
    invoke_handler: Callable[..., Awaitable[Any]]
    registry: Callable[[], Any]
    remap_execution_error_for_task: Callable[..., Awaitable[Any]]


class WorkflowRoutingCoordination:
    def __init__(self, ports: WorkflowRoutingCoordinationPorts) -> None:
        self._ports = ports

    async def run(self, *, task: Any, plan: Any, now: datetime) -> Any:
        """Выполняет один stage workflow и возвращает обновлённую задачу.

        Вызывается из ExecuteTaskUseCase после claim и перевода задачи в running.
        """
        topology = task.topology
        current_stage = task.current_stage

        with log_context_scope(stage=current_stage):
            # Подмашина коррекции имеет приоритет
            if task.correction is not None:
                handler = self._ports.handlers()["correction"]
                stage_def = self._ports.registry().get(topology, current_stage)
                assert_stage_dispatch(stage_def, correction_active=True)
                outcome = await self._ports.invoke_handler(
                    handler=handler,
                    task=task,
                    plan=plan,
                    stage_def=stage_def,
                    now=now,
                )
                return await self.apply_outcome(
                    task=task,
                    plan=plan,
                    outcome=outcome,
                    now=now,
                )

            # Обычный dispatch stage
            stage_def = self._ports.registry().get(topology, current_stage)
            assert_stage_dispatch(stage_def, correction_active=False)
            handler_key = stage_def.handler

            # Терминальные ready-stage обрабатываются централизованно
            if current_stage == "complete_ready" and str(getattr(task, "task_type", "") or "") == "irrigation_start":
                if int(getattr(task, "irrigation_replay_count", 0) or 0) > 0:
                    runtime = getattr(plan, "runtime", None)
                    recovery = getattr(runtime, "irrigation_recovery", None) if runtime is not None else None
                    auto_replay = (
                        bool(getattr(recovery, "auto_replay_after_setup", False)) if recovery is not None else False
                    )
                    if auto_replay:
                        return await self._ports.apply_transition(
                            task=task,
                            plan=plan,
                            outcome=StageOutcome(kind="transition", next_stage="irrigation_start"),
                            now=now,
                        )
                return await self._ports.complete_task(task=task, now=now)
            if handler_key == "ready":
                return await self._ports.complete_task(task=task, now=now)
            if handler_key == "solution_topup_complete":
                handler = self._ports.handlers().get("solution_topup_complete")
                if handler is not None:
                    outcome = await self._ports.invoke_handler(
                        handler=handler,
                        task=task,
                        plan=plan,
                        stage_def=stage_def,
                        now=now,
                    )
                    return await self.apply_outcome(
                        task=task,
                        plan=plan,
                        outcome=outcome,
                        now=now,
                    )
            if (
                current_stage == "complete_ready"
                and str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change"
            ):
                handler = self._ports.handlers().get("solution_change_complete")
                if handler is not None:
                    outcome = await self._ports.invoke_handler(
                        handler=handler,
                        task=task,
                        plan=plan,
                        stage_def=stage_def,
                        now=now,
                    )
                    return await self.apply_outcome(
                        task=task,
                        plan=plan,
                        outcome=outcome,
                        now=now,
                    )

            handler = self._ports.handlers().get(handler_key)
            if handler is None:
                raise TaskExecutionError(
                    "ae3_unknown_handler",
                    f"Не найден handler для key={handler_key!r} (stage={current_stage})",
                )

            outcome = await self._ports.invoke_handler(
                handler=handler,
                task=task,
                plan=plan,
                stage_def=stage_def,
                now=now,
            )
            return await self.apply_outcome(
                task=task,
                plan=plan,
                outcome=outcome,
                now=now,
            )

    async def apply_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        override = getattr(outcome, "task_override", None)
        if override is not None and not same_claim_token(task, override):
            raise TaskExecutionError(
                "ae3_stale_claim_rejected",
                (
                    f"task_override не даёт права записи task_id={getattr(task, 'id', None)}: "
                    "чужой claimed_by или другое поколение claim"
                ),
            )
        current_task = override if override is not None else task
        reports = tuple(getattr(outcome, "upward_reports", ()) or ())
        if outcome.kind != "fail" and reports:
            await publish_upward_reports(reports)

        if outcome.kind == "poll":
            return await self._ports.apply_poll(task=current_task, outcome=outcome, now=now)

        if outcome.kind == "transition":
            return await self._ports.apply_transition(
                task=current_task,
                plan=plan,
                outcome=outcome,
                now=now,
            )

        if outcome.kind == "enter_correction":
            return await self._ports.apply_enter_correction(
                task=current_task,
                outcome=outcome,
                now=now,
            )

        if outcome.kind == "exit_correction":
            return await self._ports.apply_exit_correction(
                task=current_task,
                plan=plan,
                outcome=outcome,
                now=now,
            )

        if outcome.kind == "complete":
            return await self._ports.complete_task(task=current_task, now=now)

        if outcome.kind == "fail":
            irr_uid = self._ports.extract_irrig_node_uid_from_plan(plan=plan)
            error_code, error_message = await self._ports.remap_execution_error_for_task(
                task=current_task,
                error_code=outcome.error_code or "ae3_stage_failed",
                error_message=outcome.error_message or "Этап завершился ошибкой",
                node_uid=irr_uid,
            )
            return await self._ports.fail_task(
                task=current_task,
                now=now,
                error_code=error_code,
                error_message=error_message,
                upward_reports=tuple(getattr(outcome, "upward_reports", ()) or ()),
            )

        raise TaskExecutionError(
            "ae3_unknown_outcome_kind",
            f"Неизвестный StageOutcome.kind={outcome.kind!r}",
        )
