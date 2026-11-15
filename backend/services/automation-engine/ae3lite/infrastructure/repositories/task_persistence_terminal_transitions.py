"""PgAutomationTaskRepository terminal transitions: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.infrastructure.repositories.task_persistence_shared import ACTIVE_TASK_STATUSES, RUNNING_TASK_STATUSES


@dataclass(frozen=True)
class TaskPersistenceTerminalTransitionsPorts:
    fetchrow: Callable[..., Awaitable[Any]]
    log_fsm_cas_miss: Callable[..., Awaitable[Any]]
    log_fsm_success: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    observe_task_duration: Callable[..., Any]
    task_from_row: Callable[..., Any]


class TaskPersistenceTerminalTransitions:
    def __init__(self, ports: TaskPersistenceTerminalTransitionsPorts) -> None:
        self._ports = ports

    async def mark_completed(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'completed',
                updated_at = $3,
                completed_at = $3,
                error_code = NULL,
                error_message = NULL
            WHERE id = $1
              AND claimed_by = $2
              AND claim_generation = $4
              AND status IN ('claimed', 'running', 'waiting_command')
            RETURNING *
            """,
            task_id,
            owner,
            normalized_now,
            int(claim_generation),
            conn=conn,
        )
        task = self._ports.task_from_row(row)
        if task is not None:
            self._ports.observe_task_duration(row=row, outcome="completed")
            self._ports.log_fsm_success(
                action="terminal",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="completed",
                owner=owner,
            )
        else:
            await self._ports.log_fsm_cas_miss(
                action="terminal",
                task_id=task_id,
                to_status="completed",
                owner=owner,
                conn=conn,
            )
        return task

    async def mark_failed(
        self,
        *,
        task_id: int,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        return await self.mark_failed_row(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=owner,
            require_owner=True,
            claim_generation=claim_generation,
        )

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        owner: str,
        claim_generation: int,
    ) -> AutomationTask | None:
        """Fail только того claim, который вызвал recovery. Чужое поколение не трогает."""
        return await self.mark_failed_row(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=owner,
            require_owner=True,
            claim_generation=int(claim_generation),
        )

    async def fail_pending_or_active_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        claim_generation: int,
    ) -> AutomationTask | None:
        """Fail pending/active только наблюдаемого поколения claim."""
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'failed',
                error_code = $2,
                error_message = $3,
                updated_at = $4,
                completed_at = $4
            WHERE id = $1
              AND claim_generation = $6
              AND status = ANY($5::text[])
            RETURNING *
            """,
            task_id,
            error_code,
            error_message,
            normalized_now,
            list(ACTIVE_TASK_STATUSES),
            int(claim_generation),
        )
        return self._ports.task_from_row(row)

    async def update_task_status(
        self,
        *,
        task_id: int,
        owner: str,
        next_status: str,
        allowed_statuses: tuple[str, ...],
        now: datetime,
        action: str,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = $3,
                updated_at = $4
            WHERE id = $1
              AND claimed_by = $2
              AND claim_generation = $6
              AND status = ANY($5::text[])
            RETURNING *
            """,
            task_id,
            owner,
            next_status,
            normalized_now,
            list(allowed_statuses),
            int(claim_generation),
        )
        task = self._ports.task_from_row(row)
        if task is not None:
            self._ports.log_fsm_success(
                action=action,
                task=task,
                from_status="|".join(allowed_statuses),
                to_status=next_status,
                owner=owner,
            )
            return task
        await self._ports.log_fsm_cas_miss(
            action=action,
            task_id=task_id,
            to_status=next_status,
            owner=owner,
        )
        return None

    async def mark_failed_row(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
        owner: str | None,
        require_owner: bool,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        normalized_now = self._ports.normalize_timestamp(now)
        normalized_owner = str(owner or "").strip()
        if not normalized_owner:
            return None

        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'failed',
                error_code = $3,
                error_message = $4,
                updated_at = $5,
                completed_at = $5
            WHERE id = $1
              AND claimed_by = $2
              AND claim_generation = $7
              AND status = ANY($6::text[])
            RETURNING *
            """,
            task_id,
            normalized_owner,
            error_code,
            error_message,
            normalized_now,
            list(RUNNING_TASK_STATUSES),
            int(claim_generation),
        )

        task = self._ports.task_from_row(row)
        if task is not None:
            self._ports.observe_task_duration(row=row, outcome="failed")
            self._ports.log_fsm_success(
                action="terminal",
                task=task,
                from_status="claimed|running|waiting_command",
                to_status="failed",
                owner=str(owner or task.claimed_by or ""),
            )
        elif require_owner and owner is not None:
            await self._ports.log_fsm_cas_miss(
                action="terminal",
                task_id=task_id,
                to_status="failed",
                owner=owner,
            )
        return task
