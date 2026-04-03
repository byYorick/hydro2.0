"""PostgreSQL repository for AE3-Lite command execution records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import asyncpg

from common.db import get_pool


class PgAeCommandRepository:
    """Persists AE3-Lite command steps and resolves legacy history-logger links."""

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    async def create_pending(
        self,
        *,
        task_id: int,
        step_no: int,
        node_uid: str,
        channel: str,
        payload: Mapping[str, Any],
        now: datetime,
        stage_name: Optional[str] = None,
    ) -> Optional[int]:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO ae_commands (
                        task_id,
                        step_no,
                        node_uid,
                        channel,
                        payload,
                        stage_name,
                        publish_status,
                        created_at,
                        updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'pending', $7, $7)
                    RETURNING id
                    """,
                    task_id,
                    step_no,
                    node_uid,
                    channel,
                    dict(payload),
                    stage_name or None,
                    normalized_now,
                )
        except asyncpg.exceptions.ForeignKeyViolationError:
            # Parent ae_tasks row removed between plan step and insert (e.g. raw DELETE in e2e / admin).
            return None
        return int(row["id"])

    async def mark_publish_accepted(
        self,
        *,
        ae_command_id: int,
        external_id: str,
        now: datetime,
    ) -> bool:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET external_id = $2,
                    publish_status = 'accepted',
                    updated_at = $3
                WHERE id = $1
                RETURNING id
                """,
                ae_command_id,
                external_id,
                normalized_now,
            )
        return row is not None

    async def mark_publish_failed(self, *, ae_command_id: int, last_error: str, now: datetime) -> bool:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET publish_status = 'failed',
                    last_error = $2,
                    updated_at = $3
                WHERE id = $1
                RETURNING id
                """,
                ae_command_id,
                last_error,
                normalized_now,
            )
        return row is not None

    async def update_from_legacy(
        self,
        *,
        ae_command_id: int,
        external_id: Optional[str],
        ack_received_at: Optional[datetime],
        terminal_status: Optional[str],
        terminal_at: Optional[datetime],
        last_error: Optional[str],
        now: datetime,
    ) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        normalized_ack_received_at = self._normalize_timestamp(ack_received_at)
        normalized_terminal_at = self._normalize_timestamp(terminal_at)
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET external_id = COALESCE($2, external_id),
                    publish_status = CASE
                        WHEN COALESCE($2, external_id) IS NOT NULL THEN 'accepted'
                        ELSE publish_status
                    END,
                    ack_received_at = COALESCE($3, ack_received_at),
                    terminal_status = COALESCE($4, terminal_status),
                    terminal_at = COALESCE($5, terminal_at),
                    last_error = COALESCE($6, last_error),
                    updated_at = $7
                WHERE id = $1
                RETURNING *
                """,
                ae_command_id,
                external_id,
                normalized_ack_received_at,
                terminal_status,
                normalized_terminal_at,
                last_error,
                normalized_now,
            )
        return dict(row) if row is not None else None

    async def resolve_greenhouse_uid(self, *, zone_id: int) -> Optional[str]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT g.uid AS greenhouse_uid
                FROM zones z
                JOIN greenhouses g
                    ON g.id = z.greenhouse_id
                WHERE z.id = $1
                LIMIT 1
                """,
                zone_id,
            )
        if row is None:
            return None
        greenhouse_uid = str(row.get("greenhouse_uid") or "").strip()
        return greenhouse_uid or None

    async def resolve_legacy_command_id(self, *, zone_id: int, cmd_id: str) -> Optional[int]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id
                FROM commands
                WHERE zone_id = $1
                  AND cmd_id = $2
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
                cmd_id,
            )
        return int(row["id"]) if row is not None else None

    async def get_legacy_command_by_id(self, *, external_id: str) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    c.id,
                    c.zone_id,
                    c.node_id,
                    n.uid AS node_uid,
                    c.channel,
                    c.cmd,
                    c.params,
                    c.source,
                    c.cycle_id,
                    c.cmd_id,
                    c.status,
                    c.ack_at,
                    c.sent_at,
                    c.failed_at,
                    c.updated_at,
                    c.created_at,
                    c.error_message
                FROM commands c
                LEFT JOIN nodes n
                    ON n.id = c.node_id
                WHERE c.id = $1
                LIMIT 1
                """,
                int(external_id),
            )
        return dict(row) if row is not None else None

    async def get_legacy_command_by_cmd_id(self, *, zone_id: int, cmd_id: str) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    c.id,
                    c.zone_id,
                    c.node_id,
                    n.uid AS node_uid,
                    c.channel,
                    c.cmd,
                    c.params,
                    c.source,
                    c.cycle_id,
                    c.cmd_id,
                    c.status,
                    c.ack_at,
                    c.sent_at,
                    c.failed_at,
                    c.updated_at,
                    c.created_at,
                    c.error_message
                FROM commands c
                LEFT JOIN nodes n
                    ON n.id = c.node_id
                WHERE c.zone_id = $1
                  AND c.cmd_id = $2
                ORDER BY c.created_at DESC, c.id DESC
                LIMIT 1
                """,
                zone_id,
                cmd_id,
            )
        return dict(row) if row is not None else None

    async def get_node_runtime_context(self, *, node_uid: str) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    n.id,
                    n.uid,
                    LOWER(COALESCE(n.type, '')) AS node_type,
                    LOWER(COALESCE(n.status, '')) AS node_status,
                    n.zone_id,
                    n.last_seen_at,
                    n.last_heartbeat_at,
                    n.updated_at
                FROM nodes n
                WHERE n.uid = $1
                LIMIT 1
                """,
                node_uid,
            )
        return dict(row) if row is not None else None

    async def get_latest_for_task(self, *, task_id: int) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_commands
                WHERE task_id = $1
                ORDER BY step_no DESC, id DESC
                LIMIT 1
                """,
                task_id,
            )
        return dict(row) if row is not None else None

    async def get_by_task_step(self, *, task_id: int, step_no: int) -> Optional[Mapping[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_commands
                WHERE task_id = $1
                  AND step_no = $2
                LIMIT 1
                """,
                task_id,
                step_no,
            )
        return dict(row) if row is not None else None

    async def get_next_step_no(self, *, task_id: int) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(step_no), 0) + 1 AS next_step_no
                FROM ae_commands
                WHERE task_id = $1
                """,
                task_id,
            )
        return int(row["next_step_no"]) if row is not None else 1
