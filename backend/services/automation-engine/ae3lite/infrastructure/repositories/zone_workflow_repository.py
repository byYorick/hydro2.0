"""PostgreSQL-репозиторий состояния zone workflow в AE3-Lite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping, Optional

import asyncpg

from ae3lite.domain.entities import ZoneWorkflow
from ae3lite.domain.errors import Ae3LiteError
from common.db import get_pool


class PgZoneWorkflowRepository:
    """Сохраняет канонический `zone_workflow_state` с CAS-инкрементом версии."""

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    @asynccontextmanager
    async def _connection(self, conn: asyncpg.Connection | None = None) -> AsyncIterator[asyncpg.Connection]:
        if conn is not None:
            yield conn
            return

        pool = await get_pool()
        async with pool.acquire() as acquired_conn:
            yield acquired_conn

    async def get(self, *, zone_id: int, conn: asyncpg.Connection | None = None) -> Optional[ZoneWorkflow]:
        async with self._connection(conn) as db_conn:
            row = await db_conn.fetchrow(
                """
                SELECT zone_id, workflow_phase, version, started_at, updated_at, payload, scheduler_task_id
                FROM zone_workflow_state
                WHERE zone_id = $1
                LIMIT 1
                """,
                zone_id,
            )
        return ZoneWorkflow.from_row(row) if row is not None else None

    async def upsert_phase(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: Mapping[str, Any],
        scheduler_task_id: Optional[str],
        now: datetime,
        conn: asyncpg.Connection | None = None,
    ) -> ZoneWorkflow:
        normalized_now = self._normalize_timestamp(now)
        normalized_payload = dict(payload) if isinstance(payload, Mapping) else {}
        async with self._connection(conn) as db_conn:
            if conn is None:
                async with db_conn.transaction():
                    row = await self._upsert_phase_with_conn(
                        conn=db_conn,
                        zone_id=zone_id,
                        workflow_phase=workflow_phase,
                        payload=normalized_payload,
                        scheduler_task_id=scheduler_task_id,
                        now=normalized_now,
                    )
            else:
                row = await self._upsert_phase_with_conn(
                    conn=db_conn,
                    zone_id=zone_id,
                    workflow_phase=workflow_phase,
                    payload=normalized_payload,
                    scheduler_task_id=scheduler_task_id,
                    now=normalized_now,
                )
        if row is None:
            raise Ae3LiteError(
                f"zone_workflow_state CAS conflict on zone_id={zone_id}: "
                "concurrent modification detected (version mismatch)"
            )
        return ZoneWorkflow.from_row(row)

    async def _upsert_phase_with_conn(
        self,
        *,
        conn: asyncpg.Connection,
        zone_id: int,
        workflow_phase: str,
        payload: Mapping[str, Any],
        scheduler_task_id: Optional[str],
        now: datetime,
    ) -> asyncpg.Record | None:
        current = await conn.fetchrow(
            """
            SELECT version, started_at
            FROM zone_workflow_state
            WHERE zone_id = $1
            FOR UPDATE
            """,
            zone_id,
        )
        if current is None:
            return await conn.fetchrow(
                """
                INSERT INTO zone_workflow_state (
                    zone_id,
                    workflow_phase,
                    version,
                    started_at,
                    updated_at,
                    payload,
                    scheduler_task_id
                )
                VALUES ($1, $2, 1, $3, $3, $4::jsonb, $5)
                RETURNING zone_id, workflow_phase, version, started_at, updated_at, payload, scheduler_task_id
                """,
                zone_id,
                workflow_phase,
                now,
                payload,
                scheduler_task_id,
            )

        started_at = current["started_at"] or now
        return await conn.fetchrow(
            """
            UPDATE zone_workflow_state
            SET workflow_phase = $2,
                version = $3,
                started_at = $4,
                updated_at = $5,
                payload = $6::jsonb,
                scheduler_task_id = $7
            WHERE zone_id = $1
              AND version = $8
            RETURNING zone_id, workflow_phase, version, started_at, updated_at, payload, scheduler_task_id
            """,
            zone_id,
            workflow_phase,
            int(current["version"]) + 1,
            started_at,
            now,
            payload,
            scheduler_task_id,
            int(current["version"]),
        )
