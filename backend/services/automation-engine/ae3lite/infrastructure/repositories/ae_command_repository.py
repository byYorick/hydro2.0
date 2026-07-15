"""PostgreSQL-репозиторий записей выполнения команд AE3-Lite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import asyncpg

from common.db import get_pool


class PgAeCommandRepository:
    """Сохраняет шаги команд AE3-Lite и разрешает legacy-связки с history-logger."""

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
            # Родительская строка `ae_tasks` была удалена между шагом планирования и INSERT
            # (например, raw DELETE в e2e или админском сценарии).
            return None
        except asyncpg.exceptions.UniqueViolationError:
            return None
        return int(row["id"])

    async def allocate_and_create_pending(
        self,
        *,
        task_id: int,
        zone_id: int,
        node_uid: str,
        channel: str,
        payload: Mapping[str, Any],
        now: datetime,
        stage_name: Optional[str] = None,
        planner_step: Optional[str] = None,
    ) -> Optional[tuple[int, int, bool, str]]:
        """Атомарно выделяет step_no и создаёт строку `ae_commands` под advisory lock task_id.

        При заданном `planner_step` переиспользует непубликованную строку (pending/published_unconfirmed)
        с тем же ключом — стабильный cmd_id для retry.

        Возвращает ``(ae_command_id, step_no, reused, publish_status)``.
        """
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        normalized_planner_step = str(planner_step or "").strip() or None
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", int(task_id))
                    if normalized_planner_step:
                        existing = await conn.fetchrow(
                            """
                            SELECT id, step_no, publish_status
                            FROM ae_commands
                            WHERE task_id = $1
                              AND planner_step = $2
                              AND publish_status IN ('pending', 'published_unconfirmed')
                            FOR UPDATE
                            LIMIT 1
                            """,
                            task_id,
                            normalized_planner_step,
                        )
                        if existing is not None:
                            step_no = int(existing["step_no"])
                            ae_command_id = int(existing["id"])
                            existing_publish_status = str(existing["publish_status"] or "pending").strip()
                            stored_payload = dict(payload)
                            stored_payload["cmd_id"] = f"ae3-t{task_id}-z{zone_id}-s{step_no}"
                            await conn.execute(
                                """
                                UPDATE ae_commands
                                SET node_uid = $2,
                                    channel = $3,
                                    payload = $4::jsonb,
                                    stage_name = COALESCE($5, stage_name),
                                    updated_at = $6
                                WHERE id = $1
                                """,
                                ae_command_id,
                                node_uid,
                                channel,
                                stored_payload,
                                stage_name or None,
                                normalized_now,
                            )
                            return ae_command_id, step_no, True, existing_publish_status

                    next_row = await conn.fetchrow(
                        """
                        SELECT COALESCE(MAX(step_no), 0) + 1 AS next_step_no
                        FROM ae_commands
                        WHERE task_id = $1
                        """,
                        task_id,
                    )
                    step_no = int(next_row["next_step_no"]) if next_row is not None else 1
                    stored_payload = dict(payload)
                    stored_payload["cmd_id"] = f"ae3-t{task_id}-z{zone_id}-s{step_no}"
                    row = await conn.fetchrow(
                        """
                        INSERT INTO ae_commands (
                            task_id,
                            step_no,
                            planner_step,
                            node_uid,
                            channel,
                            payload,
                            stage_name,
                            publish_status,
                            created_at,
                            updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, 'pending', $8, $8)
                        RETURNING id
                        """,
                        task_id,
                        step_no,
                        normalized_planner_step,
                        node_uid,
                        channel,
                        stored_payload,
                        stage_name or None,
                        normalized_now,
                    )
        except asyncpg.exceptions.ForeignKeyViolationError:
            return None
        if row is None:
            return None
        return int(row["id"]), step_no, False, "pending"

    async def mark_publish_published_unconfirmed(self, *, ae_command_id: int, now: datetime) -> bool:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET publish_status = 'published_unconfirmed',
                    updated_at = $2
                WHERE id = $1
                  AND publish_status IN ('pending', 'published_unconfirmed')
                RETURNING id
                """,
                ae_command_id,
                normalized_now,
            )
        return row is not None

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

    async def record_publish_retryable_error(
        self,
        *,
        ae_command_id: int,
        last_error: str,
        now: datetime,
        outcome_unknown: bool,
    ) -> bool:
        """Записывает transient publish error, сохраняя строку для retry с тем же cmd_id."""
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        publish_status = "published_unconfirmed" if outcome_unknown else "pending"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET publish_status = CASE
                        WHEN $4 = 'published_unconfirmed' THEN 'published_unconfirmed'
                        ELSE publish_status
                    END,
                    last_error = $2,
                    updated_at = $3
                WHERE id = $1
                  AND publish_status IN ('pending', 'published_unconfirmed')
                RETURNING id
                """,
                ae_command_id,
                last_error,
                normalized_now,
                publish_status,
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
                    c.error_message,
                    c.duration_ms
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
                    c.error_message,
                    c.duration_ms
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
