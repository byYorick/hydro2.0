"""StartupRecoveryUseCase stage transition: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.services.startup_recovery_shared import logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import StartupRecoveryError


@dataclass(frozen=True)
class StartupRecoveryStageTransitionPorts:
    command_gateway: Callable[[], Any]
    emit_failed_task_alert: Callable[..., Awaitable[Any]]
    fail_task: Callable[..., Awaitable[Any]]
    registry: Callable[[], Any]
    release_lease_after_recovery_fail: Callable[..., Awaitable[Any]]
    release_lease_after_recovery_success: Callable[..., Awaitable[Any]]
    sync_workflow_failure_state: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    transitions: Callable[[], Any]
    workflow_repository: Callable[[], Any]


class StartupRecoveryStageTransition:
    def __init__(self, ports: StartupRecoveryStageTransitionPorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

    async def apply_topology_done_transition(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> AutomationTask:
        """Маршрутизирует DONE без принятия одного command step за весь stage.

        Command-stage всегда requeue'ится на тот же stage для сверки полного
        RuntimePlan batch. Остальные handler'ы продолжают registry-driven
        recovery по своей topology семантике.
        """
        topology = task.topology
        current_stage = task.current_stage

        try:
            stage_def = self._ports.registry().get(topology, current_stage)
        except KeyError:
            if self._ports.workflow_repository() is not None:
                await self._ports.sync_workflow_failure_state(task=task, now=now)
            failed = await self._ports.task_repository().fail_for_recovery(
                task_id=task.id,
                error_code="startup_recovery_unknown_stage",
                error_message=f"Неизвестный stage {current_stage} в topology {topology}",
                now=now,
                owner=str(task.claimed_by or ""),
                claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            )
            if failed is None:
                logger.error(
                    "Startup recovery: fail_for_recovery returned None for unknown stage task_id=%s zone_id=%s stage=%s topology=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    topology,
                )
                raise StartupRecoveryError(
                    f"Не удалось перевести task_id={task.id} в failed для неизвестного stage",
                )
            await self._ports.emit_failed_task_alert(
                task=failed,
                error_code="startup_recovery_unknown_stage",
                error_message=f"Неизвестный stage {current_stage} в topology {topology}",
                now=now,
                recovery_source=recovery_source,
            )
            await self._ports.release_lease_after_recovery_fail(task=task, now=now)
            return failed

        # DONE подтверждает только одну команду, а не весь command batch stage.
        # Возвращаем stage в pending: обычный handler восстановит полный
        # RuntimePlan, gateway пропустит persisted DONE planner_step'ы и
        # выполнит оставшиеся команды до topology transition.
        if stage_def.handler == "command":
            mark_batch_resume = getattr(
                self._ports.command_gateway(),
                "mark_recovery_batch_resume",
                None,
            )
            if callable(mark_batch_resume):
                marked = await mark_batch_resume(task=task, now=now)
                if not marked:
                    return await self._ports.fail_task(
                        task=task,
                        error_code="startup_recovery_unconfirmed_command",
                        error_message=(
                            f"Нельзя безопасно возобновить command batch задачи {task.id}: "
                            f"отсутствует persisted planner_step для stage={task.current_stage}"
                        ),
                        now=now,
                        recovery_source=recovery_source,
                    )
            return await self.requeue_recovered_command_stage(
                task=task,
                stage_def=stage_def,
                now=now,
            )

        # Terminal error stage
        if stage_def.terminal_error is not None:
            error_code, error_message = stage_def.terminal_error
            await self._ports.sync_workflow_failure_state(task=task, now=now)
            failed = await self._ports.task_repository().fail_for_recovery(
                task_id=task.id,
                error_code=error_code,
                error_message=error_message,
                now=now,
                owner=str(task.claimed_by or ""),
                claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            )
            if failed is None:
                logger.error(
                    "Startup recovery: fail_for_recovery returned None on terminal_error stage task_id=%s zone_id=%s stage=%s error_code=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    error_code,
                )
                raise StartupRecoveryError(
                    f"Не удалось перевести task_id={task.id} в failed после recovery DONE",
                )
            await self._ports.emit_failed_task_alert(
                task=failed,
                error_code=error_code,
                error_message=error_message,
                now=now,
                recovery_source=recovery_source,
            )
            await self._ports.release_lease_after_recovery_fail(task=task, now=now)
            return failed

        # Has next_stage — transition
        if stage_def.next_stage is not None:
            next_stage = stage_def.next_stage
            try:
                next_def = self._ports.registry().get(topology, next_stage)
            except KeyError:
                next_def = None

            next_phase = next_def.workflow_phase if next_def else "idle"

            new_workflow = WorkflowState(
                current_stage=next_stage,
                workflow_phase=next_phase,
                stage_deadline_at=None,  # Will be computed on next handler run
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=task.workflow.clean_fill_cycle,
            )

            requeued = await self.task_repo_update_stage(
                task=task,
                workflow=new_workflow,
                now=now,
            )
            if requeued is None:
                logger.error(
                    "Startup recovery: update_stage returned None on requeue task_id=%s zone_id=%s stage=%s next_stage=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    next_stage,
                )
                raise StartupRecoveryError(
                    f"Не удалось повторно поставить task_id={task.id} в очередь после recovery DONE",
                )
            # Record transition in audit trail
            await self._ports.task_repository().record_transition(
                task_id=task.id,
                from_stage=current_stage,
                to_stage=next_stage,
                workflow_phase=next_phase,
                metadata={"recovery": True},
                now=now,
            )

            await self._ports.release_lease_after_recovery_success(task=task, now=now)
            return requeued

        # Poll/handler stages (handler != "command" and != "ready") have no static
        # next_stage — transitions are decided by the handler at runtime. A stale
        # DONE from the previous command batch must not terminal-complete the task.
        if stage_def.handler != "ready":
            continued_workflow = WorkflowState(
                current_stage=current_stage,
                workflow_phase=stage_def.workflow_phase,
                stage_deadline_at=task.workflow.stage_deadline_at,
                stage_retry_count=task.workflow.stage_retry_count,
                stage_entered_at=task.workflow.stage_entered_at,
                clean_fill_cycle=task.workflow.clean_fill_cycle,
            )
            requeued = await self.task_repo_update_stage(
                task=task,
                workflow=continued_workflow,
                now=now,
            )
            if requeued is None:
                logger.error(
                    "Startup recovery: update_stage returned None on poll-stage requeue task_id=%s zone_id=%s stage=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                )
                raise StartupRecoveryError(
                    f"Не удалось повторно поставить task_id={task.id} в очередь после recovery DONE на poll-stage",
                )
            await self._ports.release_lease_after_recovery_success(task=task, now=now)
            return requeued

        # Terminal success stages (complete_ready, completed_run, completed_skip)
        completed = await self._ports.transitions().complete(
            task=task,
            workflow_phase=stage_def.workflow_phase,
            owner=str(task.claimed_by or ""),
            now=now,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if completed is None:
            logger.error(
                "Startup recovery: mark_completed returned None task_id=%s zone_id=%s stage=%s",
                task.id,
                task.zone_id,
                current_stage,
            )
            raise StartupRecoveryError(
                f"Не удалось завершить task_id={task.id} после recovery DONE",
            )
        await self._ports.release_lease_after_recovery_success(task=task, now=now)
        return completed

    async def requeue_recovered_command_stage(
        self,
        *,
        task: AutomationTask,
        stage_def: Any,
        now: datetime,
    ) -> AutomationTask:
        current_stage = str(task.current_stage or "")
        continued_workflow = WorkflowState(
            current_stage=current_stage,
            workflow_phase=stage_def.workflow_phase,
            stage_deadline_at=task.workflow.stage_deadline_at,
            stage_retry_count=task.workflow.stage_retry_count,
            stage_entered_at=task.workflow.stage_entered_at,
            clean_fill_cycle=task.workflow.clean_fill_cycle,
        )
        requeued = await self.task_repo_update_stage(
            task=task,
            workflow=continued_workflow,
            now=now,
        )
        if requeued is None:
            logger.error(
                "Startup recovery: update_stage returned None on command-stage batch resume "
                "task_id=%s zone_id=%s stage=%s",
                task.id,
                task.zone_id,
                current_stage,
            )
            raise StartupRecoveryError(
                f"Не удалось повторно поставить task_id={task.id} в очередь "
                f"для продолжения command batch stage={current_stage}",
            )
        await self._ports.release_lease_after_recovery_success(task=task, now=now)
        return requeued

    async def task_repo_update_stage(
        self,
        *,
        task: AutomationTask,
        workflow: WorkflowState,
        now: datetime,
    ) -> Any:
        """Wrapper for update_stage during recovery."""
        return await self._ports.transitions().requeue(
            task=task,
            owner=str(task.claimed_by or ""),
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            workflow=workflow,
            correction=None,
            due_at=now,
            now=now,
            workflow_phase=None if workflow.current_stage == "await_ready" else workflow.workflow_phase,
            preserve_pending_manual_step=True,
        )

    async def sync_workflow_failure_state(self, *, task: AutomationTask, now: datetime) -> None:
        from ae3lite.domain.services.workflow_failure_rollback import (
            resolve_workflow_phase_after_task_failure,
        )

        rollback_phase = resolve_workflow_phase_after_task_failure(task)
        # irrig_recirc: legacy compat only for old tasks.
        scheduler_task_id = None if rollback_phase in {"ready", "irrig_recirc"} else str(task.id)
        payload = {
            "ae3_cycle_start_stage": str(getattr(task, "current_stage", "") or ""),
            "ae3_failure_rollback": True,
            "ae3_failed_task_id": int(getattr(task, "id", 0) or 0) or None,
        }
        await self.safe_upsert_workflow_phase(
            zone_id=task.zone_id,
            workflow_phase=rollback_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def safe_upsert_workflow_phase(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: dict[str, Any],
        scheduler_task_id: str,
        now: datetime,
    ) -> None:
        if self._ports.workflow_repository() is None:
            return
        try:
            await self._ports.workflow_repository().upsert_phase(
                zone_id=zone_id,
                workflow_phase=workflow_phase,
                payload=payload,
                scheduler_task_id=scheduler_task_id,
                now=now,
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to sync zone_workflow_state zone_id=%s task_id=%s phase=%s",
                zone_id,
                scheduler_task_id,
                workflow_phase,
                exc_info=True,
            )
