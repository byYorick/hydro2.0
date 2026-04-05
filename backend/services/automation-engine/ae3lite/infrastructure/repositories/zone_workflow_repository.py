"""PostgreSQL-репозиторий состояния zone workflow в AE3-Lite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

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

    async def get(self, *, zone_id: int) -> Optional[ZoneWorkflow]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
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
    ) -> ZoneWorkflow:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        normalized_payload = dict(payload) if isinstance(payload, Mapping) else {}
        async with pool.acquire() as conn:
            async with conn.transaction():
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
                    row = await conn.fetchrow(
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
                        normalized_now,
                        normalized_payload,
                        scheduler_task_id,
                    )
                else:
                    started_at = current["started_at"] or normalized_now
                    row = await conn.fetchrow(
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
                        normalized_now,
                        normalized_payload,
                        scheduler_task_id,
                        int(current["version"]),
                    )
        if row is None:
            raise Ae3LiteError(
                f"zone_workflow_state CAS conflict on zone_id={zone_id}: "
                "concurrent modification detected (version mismatch)"
            )
        return ZoneWorkflow.from_row(row)
