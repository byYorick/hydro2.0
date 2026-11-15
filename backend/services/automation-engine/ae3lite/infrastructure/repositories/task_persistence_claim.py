"""PgAutomationTaskRepository claim: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

import asyncpg

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.infrastructure.repositories.task_persistence_shared import _ZoneLeaseNotAcquired


@dataclass(frozen=True)
class TaskPersistenceClaimPorts:
    connection: Callable[..., Any]
    fetchrow: Callable[..., Awaitable[Any]]
    log_fsm_cas_miss: Callable[..., Awaitable[Any]]
    log_fsm_success: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    task_from_row: Callable[..., Any]


class TaskPersistenceClaim:
    def __init__(self, ports: TaskPersistenceClaimPorts) -> None:
        self._ports = ports

    async def claim_next_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        """Захватывает pending-задачу и zone lease в одной транзакции.

        Если lease не получена, транзакция откатывается: задача не остаётся claimed.
        """
        return await self.claim_with_zone_lease(
            owner=owner,
            process_run_id=process_run_id,
            now=now,
            lease_ttl_sec=lease_ttl_sec,
            overall_deadline_sec=overall_deadline_sec,
            task_id=None,
        )

    async def claim_pending_task_with_zone_lease(
        self,
        *,
        task_id: int,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        """Тот же атомарный claim, но только для конкретной pending-задачи."""
        return await self.claim_with_zone_lease(
            owner=owner,
            process_run_id=process_run_id,
            now=now,
            lease_ttl_sec=lease_ttl_sec,
            overall_deadline_sec=overall_deadline_sec,
            task_id=int(task_id),
            conn=conn,
        )

    async def claim_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int,
        task_id: int | None,
        conn: asyncpg.Connection | None = None,
    ) -> tuple[AutomationTask, ZoneLease] | None:
        normalized_owner = str(owner or "").strip()
        normalized_run = str(process_run_id or "").strip()
        if not normalized_owner or not normalized_run:
            return None
        normalized_now = self._ports.normalize_timestamp(now)
        leased_until = normalized_now + timedelta(seconds=max(1, int(lease_ttl_sec)))
        first_claim_deadline = normalized_now + timedelta(seconds=max(60, int(overall_deadline_sec)))

        async def _run(db: asyncpg.Connection) -> tuple[AutomationTask, ZoneLease] | None:
            try:
                async with db.transaction():
                    if task_id is None:
                        row = await db.fetchrow(
                            """
                            WITH candidate AS (
                                SELECT id
                                FROM ae_tasks
                                WHERE status = 'pending'
                                  AND (
                                      due_at <= $1
                                      OR (overall_deadline_at IS NOT NULL AND overall_deadline_at <= $1)
                                  )
                                ORDER BY LEAST(due_at, COALESCE(overall_deadline_at, due_at)) ASC,
                                         created_at ASC,
                                         id ASC
                                FOR UPDATE SKIP LOCKED
                                LIMIT 1
                            )
                            UPDATE ae_tasks tasks
                            SET status = 'claimed',
                                claimed_by = $2,
                                claimed_at = $1,
                                claim_generation = nextval('ae_claim_generation_seq'),
                                process_run_id = $3,
                                overall_deadline_at = COALESCE(tasks.overall_deadline_at, $4),
                                updated_at = $1
                            FROM candidate
                            WHERE tasks.id = candidate.id
                            RETURNING tasks.*
                            """,
                            normalized_now,
                            normalized_owner,
                            normalized_run,
                            first_claim_deadline,
                        )
                    else:
                        row = await db.fetchrow(
                            """
                            WITH candidate AS (
                                SELECT id
                                FROM ae_tasks
                                WHERE id = $5
                                  AND status = 'pending'
                                  AND (
                                      due_at <= $1
                                      OR (overall_deadline_at IS NOT NULL AND overall_deadline_at <= $1)
                                  )
                                FOR UPDATE SKIP LOCKED
                            )
                            UPDATE ae_tasks tasks
                            SET status = 'claimed',
                                claimed_by = $2,
                                claimed_at = $1,
                                claim_generation = nextval('ae_claim_generation_seq'),
                                process_run_id = $3,
                                overall_deadline_at = COALESCE(tasks.overall_deadline_at, $4),
                                updated_at = $1
                            FROM candidate
                            WHERE tasks.id = candidate.id
                            RETURNING tasks.*
                            """,
                            normalized_now,
                            normalized_owner,
                            normalized_run,
                            first_claim_deadline,
                            int(task_id),
                        )
                    task = self._ports.task_from_row(row)
                    if task is None:
                        return None
                    lease_row = await db.fetchrow(
                        """
                        INSERT INTO ae_zone_leases (
                            zone_id, owner, leased_until, updated_at, claim_generation, process_run_id
                        )
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (zone_id) DO UPDATE
                        SET owner = EXCLUDED.owner,
                            leased_until = EXCLUDED.leased_until,
                            updated_at = EXCLUDED.updated_at,
                            claim_generation = EXCLUDED.claim_generation,
                            process_run_id = EXCLUDED.process_run_id
                        WHERE ae_zone_leases.leased_until <= EXCLUDED.updated_at
                           OR (
                                ae_zone_leases.owner = EXCLUDED.owner
                                AND ae_zone_leases.process_run_id IS NOT DISTINCT FROM EXCLUDED.process_run_id
                           )
                        RETURNING zone_id, owner, leased_until, updated_at, claim_generation, process_run_id
                        """,
                        int(task.zone_id),
                        normalized_owner,
                        leased_until,
                        normalized_now,
                        int(task.claim_generation),
                        normalized_run,
                    )
                    if lease_row is None:
                        raise _ZoneLeaseNotAcquired()
                    return task, ZoneLease.from_row(lease_row)
            except _ZoneLeaseNotAcquired:
                return None

        if conn is not None:
            return await _run(conn)
        async with self._ports.connection() as owned:
            return await _run(owned)

    async def release_claim(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> bool:
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks
            SET status = 'pending',
                claimed_by = NULL,
                claimed_at = NULL,
                process_run_id = NULL,
                updated_at = $3
            WHERE id = $1
              AND status = 'claimed'
              AND claimed_by = $2
              AND claim_generation = $4
            RETURNING id
            """,
            task_id,
            owner,
            normalized_now,
            int(claim_generation),
        )
        return row is not None

    async def requeue_unpublished_execution(
        self,
        *,
        task_id: int,
        owner: str,
        now: datetime,
        claim_generation: int = 0,
    ) -> AutomationTask | None:
        """Откатывает `claimed|running` без `ae_commands` в `pending` для graceful shutdown."""
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            UPDATE ae_tasks AS tasks
            SET status = 'pending',
                claimed_by = NULL,
                claimed_at = NULL,
                process_run_id = NULL,
                updated_at = $3
            WHERE tasks.id = $1
              AND tasks.status IN ('claimed', 'running')
              AND tasks.claimed_by = $2
              AND tasks.claim_generation = $4
              AND NOT EXISTS (
                  SELECT 1
                  FROM ae_commands AS commands
                  WHERE commands.task_id = tasks.id
              )
            RETURNING tasks.*
            """,
            task_id,
            owner,
            normalized_now,
            int(claim_generation),
        )
        task = self._ports.task_from_row(row)
        if task is not None:
            self._ports.log_fsm_success(
                action="requeue",
                task=task,
                from_status="claimed|running",
                to_status="pending",
                owner=owner,
            )
        else:
            await self._ports.log_fsm_cas_miss(
                action="requeue",
                task_id=task_id,
                to_status="pending",
                owner=owner,
            )
        return task
