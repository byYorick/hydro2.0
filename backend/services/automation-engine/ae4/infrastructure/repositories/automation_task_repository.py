"""Claim и lifecycle задач только для зон ``automation_runtime = ae4``."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping, Optional

import asyncpg

from dataclasses import dataclass

from ae4.domain.entities import (
    ACTIVE_TASK_STATUSES,
    INFLIGHT_TASK_STATUSES,
    Ae4Task,
)
from common.db import get_pool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedTask:
    id: int
    zone_id: int
    status: str
    claimed_by: str


class PgAutomationTaskRepository:
    """Забирает pending-задачу зоны ``ae4``, у которой ``due_at`` уже наступил."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0)

    def _task_from_row(self, row: Any) -> Ae4Task | None:
        if row is None:
            return None
        return Ae4Task.from_row(row)

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[asyncpg.Connection]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            yield conn

    async def claim_next_pending(self, *, owner: str, now: datetime) -> ClaimedTask | None:
        normalized_now = self._normalize_timestamp(now)
        # FOR UPDATE OF tasks: блокировка строки zones не должна прятать задачу.
        async with self._connection() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    WITH candidate AS (
                        SELECT tasks.id
                        FROM ae_tasks AS tasks
                        JOIN zones ON zones.id = tasks.zone_id
                        WHERE tasks.status = 'pending'
                          AND tasks.due_at <= $1
                          AND zones.automation_runtime IS DISTINCT FROM 'ae3'
                        ORDER BY tasks.due_at ASC, tasks.created_at ASC, tasks.id ASC
                        FOR UPDATE OF tasks SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE ae_tasks AS tasks
                    SET status = 'claimed',
                        claimed_by = $2,
                        claimed_at = $1,
                        updated_at = $1
                    FROM candidate
                    WHERE tasks.id = candidate.id
                    RETURNING tasks.id, tasks.zone_id, tasks.status, tasks.claimed_by
                    """,
                    normalized_now,
                    owner,
                )
        if row is None:
            return None
        task = ClaimedTask(
            id=int(row["id"]),
            zone_id=int(row["zone_id"]),
            status=str(row["status"]),
            claimed_by=str(row["claimed_by"]),
        )
        logger.info(
            "AE4 claim",
            extra={
                "task_id": task.id,
                "zone_id": task.zone_id,
                "from_status": "pending",
                "to_status": "claimed",
                "owner": owner,
            },
        )
        return task

    async def get_by_id(self, *, task_id: int) -> Ae4Task | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_tasks
                WHERE id = $1
                LIMIT 1
                """,
                task_id,
            )
        return self._task_from_row(row)

    async def get_active_for_zone(self, *, zone_id: int) -> Ae4Task | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
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
            )
        return self._task_from_row(row)

    async def get_last_for_zone(self, *, zone_id: int) -> Ae4Task | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_tasks
                WHERE zone_id = $1
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
            )
        return self._task_from_row(row)

    async def force_fail(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Ae4Task | None:
        """Помечает активную задачу failed без проверки claimed_by (operator/control-mode)."""
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    updated_at = $2,
                    completed_at = $2,
                    error_code = $3,
                    error_message = $4
                WHERE id = $1
                  AND status = ANY($5::text[])
                RETURNING *
                """,
                task_id,
                normalized_now,
                error_code,
                error_message,
                list(ACTIVE_TASK_STATUSES),
            )
        return self._task_from_row(row)

    async def create_pending_if_idle(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        task_type: str,
        current_stage: str,
        workflow_phase: str,
        scheduled_for: datetime,
        due_at: datetime,
        now: datetime,
        intent_meta: Mapping[str, Any] | None = None,
        topology: str = "planting",
    ) -> Ae4Task | None:
        """Создаёт pending только если у зоны нет активной задачи (E217)."""
        normalized_scheduled = self._normalize_timestamp(scheduled_for)
        normalized_due = self._normalize_timestamp(due_at)
        normalized_now = self._normalize_timestamp(now)
        meta = dict(intent_meta or {})
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                active = await conn.fetchrow(
                    """
                    SELECT id
                    FROM ae_tasks
                    WHERE zone_id = $1
                      AND status = ANY($2::text[])
                    LIMIT 1
                    FOR UPDATE
                    """,
                    zone_id,
                    list(ACTIVE_TASK_STATUSES),
                )
                if active is not None:
                    return None
                try:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ae_tasks (
                            zone_id, task_type, status, idempotency_key,
                            topology, current_stage, workflow_phase,
                            intent_meta, scheduled_for, due_at,
                            created_at, updated_at
                        )
                        VALUES (
                            $1, $2, 'pending', $3,
                            $4, $5, $6,
                            $7::jsonb, $8, $9,
                            $10, $10
                        )
                        RETURNING *
                        """,
                        zone_id,
                        task_type,
                        idempotency_key,
                        topology,
                        current_stage,
                        workflow_phase,
                        meta,
                        normalized_scheduled,
                        normalized_due,
                        normalized_now,
                    )
                except asyncpg.UniqueViolationError:
                    return None
        return self._task_from_row(row)

    async def mark_running(self, *, task_id: int, owner: str, now: datetime) -> Ae4Task | None:
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'running',
                    updated_at = $3
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return self._task_from_row(row)

    async def mark_waiting_command(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
    ) -> Ae4Task | None:
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'waiting_command',
                    updated_at = $3
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return self._task_from_row(row)

    async def mark_completed(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
    ) -> Ae4Task | None:
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'completed',
                    updated_at = $3,
                    completed_at = $3,
                    error_code = NULL,
                    error_message = NULL
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
            )
        return self._task_from_row(row)

    async def mark_failed(
        self,
        *,
        task_id: int,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Ae4Task | None:
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_tasks
                SET status = 'failed',
                    updated_at = $3,
                    completed_at = $3,
                    error_code = $4,
                    error_message = $5
                WHERE id = $1
                  AND claimed_by = $2
                  AND status IN ('claimed', 'running', 'waiting_command')
                RETURNING *
                """,
                task_id,
                owner,
                normalized_now,
                error_code,
                error_message,
            )
        return self._task_from_row(row)

    async def list_inflight_for_ae4(
        self,
        *,
        worker_owner: str | None = None,
    ) -> list[Ae4Task]:
        """In-flight задачи только зон ae4. Задачи ae3 не трогает."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            if worker_owner:
                rows = await conn.fetch(
                    """
                    SELECT tasks.*
                    FROM ae_tasks AS tasks
                    JOIN zones ON zones.id = tasks.zone_id
                    WHERE tasks.status = ANY($1::text[])
                      AND zones.automation_runtime IS DISTINCT FROM 'ae3'
                      AND tasks.claimed_by = $2
                    ORDER BY tasks.updated_at ASC, tasks.id ASC
                    """,
                    list(INFLIGHT_TASK_STATUSES),
                    worker_owner,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT tasks.*
                    FROM ae_tasks AS tasks
                    JOIN zones ON zones.id = tasks.zone_id
                    WHERE tasks.status = ANY($1::text[])
                      AND zones.automation_runtime IS DISTINCT FROM 'ae3'
                    ORDER BY tasks.updated_at ASC, tasks.id ASC
                    """,
                    list(INFLIGHT_TASK_STATUSES),
                )
        return [Ae4Task.from_row(row) for row in rows]

    async def count_pending(self) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT COUNT(*)::int
                FROM ae_tasks AS tasks
                JOIN zones ON zones.id = tasks.zone_id
                WHERE tasks.status = 'pending'
                  AND zones.automation_runtime IS DISTINCT FROM 'ae3'
                """
            )
        return int(value or 0)

    async def oldest_active_age_seconds(self, *, now: datetime) -> float:
        normalized_now = self._normalize_timestamp(now)
        pool = await get_pool()
        async with pool.acquire() as conn:
            created = await conn.fetchval(
                """
                SELECT MIN(tasks.created_at)
                FROM ae_tasks AS tasks
                JOIN zones ON zones.id = tasks.zone_id
                WHERE tasks.status = ANY($1::text[])
                  AND zones.automation_runtime IS DISTINCT FROM 'ae3'
                """,
                list(ACTIVE_TASK_STATUSES),
            )
        if created is None:
            return 0.0
        created_naive = self._normalize_timestamp(created)
        return max(0.0, (normalized_now - created_naive).total_seconds())


__all__ = ["ClaimedTask", "PgAutomationTaskRepository"]
