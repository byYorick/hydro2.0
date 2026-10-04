"""Одна обязательная транзакция прогресса для runtime и recovery."""
from typing import Any

from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


class TaskWorkflowTransition:
    def __init__(self, *, task_repository: Any, workflow_repository: Any):
        self._tasks = task_repository
        self._workflows = workflow_repository

    async def requeue(self, *, task, owner, claim_generation, workflow, correction,
                      due_at, now, workflow_phase, stage=None, preserve_pending_manual_step=False):
        async with self._tasks.transaction() as conn:
            updated = await self._tasks.update_stage(
                task_id=task.id, owner=owner, claim_generation=claim_generation,
                workflow=workflow, correction=correction, due_at=due_at, now=now,
                preserve_pending_manual_step=preserve_pending_manual_step, conn=conn,
            )
            if updated is not None and workflow_phase is not None:
                await self._sync(conn=conn, task=updated, phase=workflow_phase, stage=stage, now=now)
            return updated

    async def complete(self, *, task, owner, claim_generation, now, workflow_phase="ready"):
        async with self._tasks.transaction() as conn:
            updated = await self._tasks.mark_completed(
                task_id=task.id, owner=owner, claim_generation=claim_generation, now=now, conn=conn,
            )
            if updated is not None:
                await self._sync(conn=conn, task=updated, phase=workflow_phase, stage=None, now=now)
            return updated

    async def _sync(self, *, conn, task, phase, stage, now):
        if self._workflows is None:
            return
        try:
            await self._workflows.upsert_phase(
                zone_id=task.zone_id, workflow_phase=phase,
                payload={"ae3_cycle_start_stage": stage if stage is not None else task.current_stage},
                scheduler_task_id=str(task.id), now=now, conn=conn,
            )
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED,
                                     f"Не удалось синхронизировать workflow задачи {task.id}") from exc
