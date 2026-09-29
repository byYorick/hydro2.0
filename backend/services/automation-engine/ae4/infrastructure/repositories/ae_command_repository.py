"""PostgreSQL-репозиторий шагов команд AE4 (таблица ae_commands).

FK ae_commands.task_id → ae_tasks.id (CASCADE). Handler AE3 в FK нет.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import asyncpg

from common.db import get_pool


class PgAeCommandRepository:
    """Узкий журнал шагов команды для воркера AE4."""

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0)

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
            return None
        except asyncpg.exceptions.UniqueViolationError:
            return None
        return int(row["id"])

    async def get_next_step_no(self, *, task_id: int) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(MAX(step_no), 0) + 1 AS next_step
                FROM ae_commands
                WHERE task_id = $1
                """,
                task_id,
            )
        return int(row["next_step"] if row is not None else 1)

    async def mark_accepted(
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

    async def mark_terminal(
        self,
        *,
        ae_command_id: int,
        terminal_status: str,
        now: datetime,
        last_error: Optional[str] = None,
    ) -> bool:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_commands
                SET terminal_status = $2,
                    terminal_at = $3,
                    last_error = COALESCE($4, last_error),
                    updated_at = $3
                WHERE id = $1
                RETURNING id
                """,
                ae_command_id,
                terminal_status,
                normalized_now,
                last_error,
            )
        return row is not None

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

    async def list_open_irrigation_starts(
        self,
        *,
        task_id: int,
    ) -> list[Mapping[str, Any]]:
        """Шаги pump_main без парного irrigation_stop в payload.role."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM ae_commands
                WHERE task_id = $1
                  AND channel = 'pump_main'
                  AND COALESCE(payload->>'role', '') = 'irrigation_start'
                  AND terminal_status = 'DONE'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ae_commands AS stop_cmd
                      WHERE stop_cmd.task_id = ae_commands.task_id
                        AND stop_cmd.step_no > ae_commands.step_no
                        AND COALESCE(stop_cmd.payload->>'role', '') = 'irrigation_stop'
                        AND stop_cmd.terminal_status = 'DONE'
                  )
                ORDER BY step_no ASC, id ASC
                """,
                task_id,
            )
        return [dict(row) for row in rows]


__all__ = ["PgAeCommandRepository"]
