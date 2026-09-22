"""Claim задач только для зон ``automation_runtime = ae4``."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

import asyncpg

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
                          AND zones.automation_runtime = 'ae4'
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


__all__ = ["ClaimedTask", "PgAutomationTaskRepository"]
