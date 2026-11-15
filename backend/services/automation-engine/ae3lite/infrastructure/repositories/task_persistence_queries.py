"""PgAutomationTaskRepository queries: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.infrastructure.repositories.task_persistence_shared import ACTIVE_TASK_STATUSES, RUNNING_TASK_STATUSES


@dataclass(frozen=True)
class TaskPersistenceQueriesPorts:
    connection: Callable[..., Any]
    fetch: Callable[..., Awaitable[Any]]
    fetchrow: Callable[..., Awaitable[Any]]
    normalize_timestamp: Callable[..., Any]
    task_from_row: Callable[..., Any]


class TaskPersistenceQueries:
    def __init__(self, ports: TaskPersistenceQueriesPorts) -> None:
        self._ports = ports

    async def get_by_idempotency_key(self, *, zone_id: int, idempotency_key: str) -> AutomationTask | None:
        normalized_key = str(idempotency_key or "").strip()
        if normalized_key == "":
            return None

        row = await self._ports.fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
              AND idempotency_key = $2
            LIMIT 1
            """,
            zone_id,
            normalized_key,
        )
        return self._ports.task_from_row(row)

    async def get_active_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        return await self.get_active_for_zone_with_conn(zone_id=zone_id)

    async def get_active_for_zone_with_conn(
        self,
        *,
        zone_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> AutomationTask | None:
        row = await self._ports.fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
              AND status = ANY($2::text[])
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            list(ACTIVE_TASK_STATUSES),
            conn=conn,
        )
        return self._ports.task_from_row(row)

    async def get_last_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        """Возвращает самую свежую задачу зоны независимо от статуса."""
        row = await self._ports.fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
        return self._ports.task_from_row(row)

    async def get_last_irrigation_for_zone(self, *, zone_id: int) -> AutomationTask | None:
        """Последняя задача полива зоны, независимо от статуса."""
        row = await self._ports.fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE zone_id = $1
              AND task_type = 'irrigation_start'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
        )
        return self._ports.task_from_row(row)

    async def get_by_id(self, *, task_id: int) -> AutomationTask | None:
        row = await self._ports.fetchrow(
            """
            SELECT *
            FROM ae_tasks
            WHERE id = $1
            LIMIT 1
            """,
            task_id,
        )
        return self._ports.task_from_row(row)

    async def list_for_startup_recovery(
        self,
        *,
        worker_owner: str | None = None,
        now: datetime | None = None,
    ) -> list[AutomationTask]:
        """Возвращает in-flight задачи для startup recovery.

        Чужой активный zone lease не фильтруется на уровне SQL — use case
        решает skip vs bounded escalate (H6).
        """
        _ = worker_owner
        _ = now
        rows = await self._ports.fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = ANY($1::text[])
            ORDER BY updated_at ASC, id ASC
            """,
            list(RUNNING_TASK_STATUSES),
        )
        return [AutomationTask.from_row(row) for row in rows]

    async def list_waiting_command_for_reconcile(self, *, limit: int = 32) -> list[AutomationTask]:
        """Возвращает `waiting_command` задачи для фонового reconcile (oldest first)."""
        bounded_limit = max(1, min(int(limit), 200))
        rows = await self._ports.fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = 'waiting_command'
            ORDER BY updated_at ASC, id ASC
            LIMIT $1
            """,
            bounded_limit,
        )
        return [AutomationTask.from_row(row) for row in rows]

    async def list_stale_claimed_running_for_reconcile(
        self,
        *,
        now: datetime,
        stale_claimed_before: datetime,
        stale_running_before: datetime,
        stale_waiting_command_before: datetime | None = None,
        stale_unconfirmed_before: datetime | None = None,
        limit: int = 16,
    ) -> list[AutomationTask]:
        """Stale claimed/running/waiting_command и running+unconfirmed для janitor."""
        normalized_claimed_before = self._ports.normalize_timestamp(stale_claimed_before)
        normalized_running_before = self._ports.normalize_timestamp(stale_running_before)
        normalized_waiting_before = self._ports.normalize_timestamp(
            stale_waiting_command_before or stale_running_before
        )
        normalized_unconfirmed_before = self._ports.normalize_timestamp(
            stale_unconfirmed_before or stale_claimed_before
        )
        bounded_limit = max(1, min(int(limit), 16))
        async with self._ports.connection() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    WITH stale AS (
                        SELECT id
                        FROM ae_tasks AS tasks
                        WHERE (
                            tasks.status = 'claimed'
                            AND tasks.claimed_at IS NOT NULL
                            AND tasks.claimed_at < $1
                        ) OR (
                            tasks.status = 'running'
                            AND tasks.updated_at < $2
                        ) OR (
                            tasks.status = 'waiting_command'
                            AND tasks.updated_at < $3
                        ) OR (
                            tasks.status IN ('claimed', 'running')
                            AND EXISTS (
                                SELECT 1
                                FROM ae_commands AS commands
                                WHERE commands.task_id = tasks.id
                                  AND commands.publish_status IN ('pending', 'published_unconfirmed')
                                  AND commands.updated_at < $4
                            )
                        )
                        ORDER BY tasks.updated_at ASC, tasks.id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT $5
                    )
                    SELECT tasks.*
                    FROM ae_tasks AS tasks
                    INNER JOIN stale ON stale.id = tasks.id
                    ORDER BY tasks.updated_at ASC, tasks.id ASC
                    """,
                    normalized_claimed_before,
                    normalized_running_before,
                    normalized_waiting_before,
                    normalized_unconfirmed_before,
                    bounded_limit,
                )
        return [AutomationTask.from_row(row) for row in rows]

    async def task_has_unconfirmed_ae_commands(self, *, task_id: int) -> bool:
        row = await self._ports.fetchrow(
            """
            SELECT EXISTS(
                SELECT 1
                FROM ae_commands
                WHERE task_id = $1
                  AND publish_status IN ('pending', 'published_unconfirmed')
            ) AS has_unconfirmed
            """,
            task_id,
        )
        return bool(row["has_unconfirmed"]) if row is not None else False

    async def task_has_ae_commands(self, *, task_id: int) -> bool:
        row = await self._ports.fetchrow(
            """
            SELECT EXISTS(
                SELECT 1
                FROM ae_commands
                WHERE task_id = $1
            ) AS has_commands
            """,
            task_id,
        )
        return bool(row["has_commands"]) if row is not None else False

    async def fetch_pending_with_idle_zone_workflow_rows(self) -> list[Any]:
        """Pending-задачи при workflow_phase=idle (часто после терминального stop в payload)."""
        return await self._ports.fetch(
            """
            SELECT t.*, zws.payload->>'ae3_cycle_start_stage' AS snapshot_stage
            FROM ae_tasks t
            INNER JOIN zone_workflow_state zws ON zws.zone_id = t.zone_id
            WHERE t.status = 'pending'
              AND zws.workflow_phase = 'idle'
            ORDER BY t.id ASC
            """,
        )

    async def next_pending_due_at(self) -> datetime | None:
        row = await self._ports.fetchrow(
            """
            SELECT LEAST(due_at, COALESCE(overall_deadline_at, due_at)) AS effective_due_at
            FROM ae_tasks
            WHERE status = 'pending'
            ORDER BY effective_due_at ASC, created_at ASC, id ASC
            LIMIT 1
            """
        )
        return None if row is None else row["effective_due_at"]

    async def list_claimed_by_owner(self, *, owner: str) -> list[AutomationTask]:
        rows = await self._ports.fetch(
            """
            SELECT *
            FROM ae_tasks
            WHERE status = 'claimed'
              AND claimed_by = $1
            ORDER BY claimed_at ASC NULLS LAST, id ASC
            """,
            owner,
        )
        return [self._ports.task_from_row(row) for row in rows]

    async def list_unpublished_execution_by_owner(self, *, owner: str) -> list[AutomationTask]:
        rows = await self._ports.fetch(
            """
            SELECT tasks.*
            FROM ae_tasks AS tasks
            WHERE tasks.claimed_by = $1
              AND tasks.status IN ('claimed', 'running')
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_commands AS commands
                  WHERE commands.task_id = tasks.id
              )
            ORDER BY tasks.claimed_at ASC NULLS LAST, tasks.id ASC
            """,
            owner,
        )
        return [self._ports.task_from_row(row) for row in rows]

    async def get_transitions_for_task(self, *, task_id: int, limit: int = 50) -> list[dict]:
        """Return stage transitions for a task ordered chronologically."""
        rows = await self._ports.fetch(
            """
            SELECT from_stage, to_stage, workflow_phase, triggered_at, metadata
            FROM ae_stage_transitions
            WHERE task_id = $1
            ORDER BY triggered_at ASC, id ASC
            LIMIT $2
            """,
            task_id,
            limit,
        )
        return [dict(row) for row in rows]
