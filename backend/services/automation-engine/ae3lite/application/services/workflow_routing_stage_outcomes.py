"""WorkflowRouter stage outcomes: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.flow_path_guard import (
    MANUAL_HOLD_STAGE,
    decode_manual_hold_operator_step,
    decode_manual_hold_return_stage,
    encode_manual_hold_return_stage,
)
from ae3lite.application.services.workflow_routing_shared import (
    _DEFAULT_MANUAL_HOLD_TIMEOUT_SEC,
    _clamp_due_delay_sec,
    logger,
)
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import (
    CORRECTION_STARTED,
    STAGE_ENTERED,
    STAGE_RETRY,
    TASK_COMPLETED,
    inc_observability_write_failed,
)


@dataclass(frozen=True)
class WorkflowRoutingStageOutcomesPorts:
    correction_completed_metric: Callable[[], Any]
    complete_task_and_workflow_phase_atomic: Callable[..., Awaitable[Any]]
    compute_deadline: Callable[..., Any]
    deadline_reached: Callable[..., Any]
    record_stage_duration: Callable[..., Any]
    registry: Callable[[], Any]
    require_original_claim: Callable[..., Awaitable[Any]]
    resolve_inactive_terminal_task: Callable[..., Awaitable[Any]]
    safe_emit_irrigation_lifecycle_event: Callable[..., Awaitable[Any]]
    safe_record_transition: Callable[..., Awaitable[Any]]
    task_repo: Callable[[], Any]
    update_stage_and_workflow_phase_atomic: Callable[..., Awaitable[Any]]
    global_create_zone_event: Callable[..., Any]


class WorkflowRoutingStageOutcomes:
    def __init__(self, ports: WorkflowRoutingStageOutcomesPorts) -> None:
        self._ports = ports

    async def apply_poll(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Оставляет задачу в том же stage и ставит повторный запуск с задержкой."""
        workflow = task.workflow
        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner, generation = await self._ports.require_original_claim(task=task)
        # await_ready reads zone_workflow_state to decide whether the fill cycle
        # completed and irrigation is safe (via plan.runtime.zone_workflow_phase).
        # Writing "ready" back into zone_workflow_state on each poll tick would
        # create a self-fulfilling loop: on the very next tick the handler sees
        # "ready" written by *itself* and starts irrigation even when tanks are
        # still empty — for example after a failed irrigation_check that left
        # zone_workflow_state="idle" due to a level-sensor error.  Only the fill
        # cycle tasks (prepare_recirculation_stop_to_ready etc.) are allowed to
        # set zone_workflow_state="ready"; await_ready must leave it untouched.
        if task.current_stage != "await_ready":
            resolved_task, _applied = await self._ports.update_stage_and_workflow_phase_atomic(
                task=task,
                owner=owner,
                claim_generation=generation,
                workflow=workflow,
                correction=task.correction,
                due_at=due_at,
                workflow_phase=workflow.workflow_phase,
                preserve_pending_manual_step=True,
                error_code="ae3_poll_apply_failed",
                error_message=f"Не удалось сохранить poll outcome для задачи {task.id}",
                expected_stage=str(task.current_stage or ""),
                now=now,
            )
            return resolved_task

        updated_task = await self._ports.task_repo().update_stage(
            task_id=task.id,
            owner=owner,
            claim_generation=generation,
            workflow=workflow,
            correction=task.correction,
            due_at=due_at,
            now=now,
            # Operator may inject pending_manual_step via POST /manual-step while
            # this poll tick already holds a stale in-memory workflow snapshot.
            preserve_pending_manual_step=True,
        )
        resolved_task = await self._ports.resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_poll_apply_failed",
            error_message=f"Не удалось сохранить poll outcome для задачи {task.id}",
            expected_stage=str(task.current_stage or ""),
        )
        return resolved_task

    async def apply_transition(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Переходит в новый stage, очищает correction state и вычисляет дедлайн."""
        next_stage = outcome.next_stage
        if next_stage is None:
            raise TaskExecutionError(
                "ae3_transition_no_next_stage",
                "Для transition outcome требуется next_stage",
            )

        topology = task.topology
        next_def = self._ports.registry().get(topology, next_stage)
        # Audit F8: same-stage transitions are intentional — handlers like
        # ``CorrectionHandler._interrupt_for_imminent_retry_then_probe_deadline``
        # and ``_correction_exhausted`` use them to schedule a retry of the
        # current stage without resetting ``stage_entered_at`` or the existing
        # deadline. When this branch fires we skip ``_record_stage_duration``
        # (the stage is not actually ending) and reuse the prior deadline; the
        # caller is expected to bump ``stage_retry_count`` explicitly if the
        # retry should count against an attempt budget.
        same_stage = next_stage == task.current_stage

        # Записать метрики завершённого stage
        if not same_stage:
            self._ports.record_stage_duration(task=task, now=now)
            STAGE_ENTERED.labels(topology=topology, stage=next_stage).inc()
        if (outcome.stage_retry_count or 0) > 0:
            STAGE_RETRY.labels(topology=topology, stage=next_stage).inc()

        # Вычислить новое состояние workflow
        runtime = plan.runtime if isinstance(getattr(plan, "runtime", None), RuntimePlan) else None
        if runtime is None:
            raise TaskExecutionError(
                "runtime_plan_missing",
                "Отсутствует typed RuntimePlan в command plan",
            )
        irrigation_start_entered_at = (
            task.workflow.stage_entered_at
            if not same_stage and str(task.current_stage or "").strip().lower() == "irrigation_start"
            else None
        )
        clean_fill_cycle = (
            outcome.clean_fill_cycle if outcome.clean_fill_cycle is not None else task.workflow.clean_fill_cycle
        )
        stage_retry_count = (
            outcome.stage_retry_count
            if outcome.stage_retry_count is not None
            else (task.workflow.stage_retry_count if same_stage else 0)
        )
        stage_entered_at = task.workflow.stage_entered_at if same_stage else now

        if next_stage == MANUAL_HOLD_STAGE:
            workflow_phase = task.workflow.workflow_phase
            stage_entered_at = task.workflow.stage_entered_at or now
            deadline = task.workflow.stage_deadline_at
            if deadline is None or self._ports.deadline_reached(now=now, deadline=deadline):
                computed = self._ports.compute_deadline(
                    task=task,
                    stage_def=next_def,
                    runtime=runtime,
                    now=now,
                    plan=plan,
                )
                deadline = (
                    computed if computed is not None else now + timedelta(seconds=_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC)
                )
        else:
            workflow_phase = next_def.workflow_phase
            deadline = (
                task.workflow.stage_deadline_at
                if same_stage
                else self._ports.compute_deadline(
                    task=task,
                    stage_def=next_def,
                    runtime=runtime,
                    now=now,
                    plan=plan,
                    irrigation_start_entered_at=irrigation_start_entered_at,
                )
            )

        pending_manual_step = None
        if outcome.flow_hold_return_stage:
            pending_manual_step = encode_manual_hold_return_stage(outcome.flow_hold_return_stage)
        elif next_stage == MANUAL_HOLD_STAGE:
            pending_manual_step = encode_manual_hold_return_stage(str(task.current_stage or ""))
        elif str(task.current_stage or "").strip() == MANUAL_HOLD_STAGE:
            operator_step = decode_manual_hold_operator_step(getattr(task.workflow, "pending_manual_step", None))
            if operator_step:
                pending_manual_step = operator_step

        saved_return = decode_manual_hold_return_stage(task.workflow.pending_manual_step)
        resume_start = (
            task.current_stage == MANUAL_HOLD_STAGE and next_stage.endswith("_start") and saved_return is not None
        )
        resume_check = str(task.current_stage or "").endswith("_start") and saved_return == next_stage
        if resume_start or resume_check:
            # A pause cannot grant a new fill/recirc timeout or restart the
            # leak guard clock. Carry the existing return marker for one hop.
            deadline = task.workflow.stage_deadline_at
            stage_entered_at = task.workflow.stage_entered_at
            stage_retry_count = task.workflow.stage_retry_count
            pending_manual_step = encode_manual_hold_return_stage(saved_return) if resume_start else None

        new_workflow = WorkflowState(
            current_stage=next_stage,
            workflow_phase=workflow_phase,
            stage_deadline_at=deadline,
            stage_retry_count=stage_retry_count,
            stage_entered_at=stage_entered_at,
            clean_fill_cycle=clean_fill_cycle,
            control_mode=task.workflow.control_mode,
            pending_manual_step=pending_manual_step,
        )

        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner, generation = await self._ports.require_original_claim(task=task)
        resolved_task, transition_applied = await self._ports.update_stage_and_workflow_phase_atomic(
            task=task,
            owner=owner,
            claim_generation=generation,
            workflow=new_workflow,
            correction=None,  # Очистить correction state при переходе
            due_at=due_at,
            workflow_phase=next_def.workflow_phase,
            stage=next_stage,
            error_code="ae3_transition_apply_failed",
            error_message=f"Не удалось перевести задачу {task.id} в stage {next_stage}",
            expected_stage=next_stage,
            now=now,
        )
        if transition_applied:
            await self._ports.safe_record_transition(
                task_id=task.id,
                from_stage=task.current_stage,
                to_stage=next_stage,
                workflow_phase=next_def.workflow_phase,
                now=now,
            )
            await self._ports.safe_emit_irrigation_lifecycle_event(
                task=task,
                from_stage=task.current_stage,
                to_stage=next_stage,
            )
        return resolved_task

    async def apply_enter_correction(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Входит в подмашину коррекции или продолжает её в рамках текущего stage."""
        corr = outcome.correction
        if corr is None:
            raise TaskExecutionError(
                "ae3_enter_correction_no_state",
                "Для enter_correction outcome требуется correction state",
            )

        # Записать метрики при первом входе
        if task.correction is None:
            CORRECTION_STARTED.labels(topology=task.topology).inc()

        workflow = task.workflow
        due_at = now + timedelta(seconds=_clamp_due_delay_sec(outcome.due_delay_sec))
        owner, generation = await self._ports.require_original_claim(task=task)
        resolved_task, _applied = await self._ports.update_stage_and_workflow_phase_atomic(
            task=task,
            owner=owner,
            claim_generation=generation,
            workflow=workflow,
            correction=corr,
            due_at=due_at,
            workflow_phase=workflow.workflow_phase,
            stage=str(task.current_stage or ""),
            error_code="ae3_correction_apply_failed",
            error_message=f"Не удалось сохранить correction state для задачи {task.id}",
            expected_corr_step=str(getattr(corr, "corr_step", "") or ""),
            now=now,
        )
        return resolved_task

    async def apply_exit_correction(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Коррекция завершена: перейти в stage возврата."""
        final_corr = outcome.correction if outcome.correction is not None else task.correction
        success = final_corr.outcome_success if final_corr and final_corr.outcome_success is not None else False
        self._ports.correction_completed_metric().labels(
            topology=task.topology,
            outcome="success" if success else "fail",
        ).inc()

        if (
            str(outcome.next_stage or "").strip().lower() == "irrigation_check"
            and str(task.current_stage or "").strip().lower() == "irrigation_check"
        ):
            try:
                await self._ports.global_create_zone_event(
                    int(task.zone_id),
                    "IRRIGATION_CORRECTION_COMPLETED",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "topology": str(getattr(task, "topology", "") or ""),
                        "success": bool(success),
                    },
                )
            except Exception:
                inc_observability_write_failed(kind="zone_event")
                logger.warning(
                    "AE3 не смог записать IRRIGATION_CORRECTION_COMPLETED zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )

        # Делегировать обычному переходу
        return await self.apply_transition(
            task=task,
            plan=plan,
            outcome=outcome,
            now=now,
        )

    async def complete_task(self, *, task: Any, now: datetime) -> Any:
        TASK_COMPLETED.labels(topology=task.topology).inc()
        owner, generation = await self._ports.require_original_claim(task=task)
        resolved_task, _applied = await self._ports.complete_task_and_workflow_phase_atomic(
            task=task,
            owner=owner,
            claim_generation=generation,
            now=now,
        )
        return resolved_task
