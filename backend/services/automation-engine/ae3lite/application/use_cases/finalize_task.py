"""Finalize AE3-Lite task into a terminal state."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskFinalizeError


class FinalizeTaskUseCase:
    """Owns terminal task transitions so runtime paths do not inline them."""

    def __init__(self, *, task_repository: Any) -> None:
        self._task_repository = task_repository

    async def complete(self, *, task: AutomationTask, owner: str, now: datetime) -> AutomationTask:
        completed = await self._task_repository.mark_completed(
            task_id=task.id,
            owner=owner,
            now=now,
        )
        if completed is None:
            raise TaskFinalizeError("ae3_task_complete_failed", f"Unable to complete task {task.id}")
        return completed

    async def fail(
        self,
        *,
        task: AutomationTask,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask:
        failed = await self._task_repository.mark_failed(
            task_id=task.id,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )
        if failed is None:
            raise TaskFinalizeError(error_code or "ae3_task_finalize_failed", f"Unable to fail task {task.id}")
        return failed

    async def fail_closed(
        self,
        *,
        task: AutomationTask,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask:
        failed = await self._task_repository.mark_failed(
            task_id=task.id,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )
        if failed is not None:
            return failed

        current_task = await self._task_repository.get_by_id(task_id=task.id)
        if current_task is not None and not current_task.is_active:
            return current_task

        # Cleanup may cascade-delete the task row while the worker is still unwinding.
        return replace(
            task,
            status="failed",
            error_code=error_code,
            error_message=error_message,
            updated_at=now,
            completed_at=now,
        )
