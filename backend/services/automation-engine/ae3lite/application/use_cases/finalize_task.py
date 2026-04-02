"""Finalize AE3-Lite task into a terminal state."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskFinalizeError

logger = logging.getLogger(__name__)


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


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
        if completed is not None:
            return completed

        get_by_id = getattr(self._task_repository, "get_by_id", None)
        if not callable(get_by_id):
            raise TaskFinalizeError("ae3_task_complete_failed", f"Unable to complete task {task.id}")

        current_task = await get_by_id(task_id=task.id)
        if current_task is not None and not current_task.is_active:
            return current_task
        if current_task is None:
            logger.info(
                "AE3 finalize complete: task row absent after mark_completed miss "
                "(likely concurrent cleanup); returning synthetic completed task task_id=%s zone_id=%s",
                task.id,
                task.zone_id,
            )
            naive_now = _naive_utc(now)
            return replace(
                task,
                status="completed",
                error_code=None,
                error_message=None,
                updated_at=naive_now,
                completed_at=naive_now,
            )
        raise TaskFinalizeError(
            "ae3_task_complete_failed",
            f"Unable to complete task {task.id}: row still active with status={current_task.status}",
        )

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

        if current_task is None:
            logger.info(
                "AE3 finalize fail_closed: task row absent after mark_failed miss "
                "(likely concurrent cleanup); returning synthetic failed task task_id=%s zone_id=%s",
                task.id,
                task.zone_id,
            )
            naive_now = _naive_utc(now)
            return replace(
                task,
                status="failed",
                error_code=str(error_code or "ae3_task_finalize_failed").strip() or "ae3_task_finalize_failed",
                error_message=str(error_message or ""),
                updated_at=naive_now,
                completed_at=naive_now,
            )

        raise TaskFinalizeError(
            error_code or "ae3_task_finalize_failed",
            (
                f"Unable to fail task {task.id}: task row remained active "
                f"with status={current_task.status}"
            ),
        )
