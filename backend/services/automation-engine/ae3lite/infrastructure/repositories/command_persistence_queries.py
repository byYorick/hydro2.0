"""PgAeCommandRepository queries: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional


@dataclass(frozen=True)
class CommandPersistenceQueriesPorts:
    global_get_pool: Callable[..., Any]


class CommandPersistenceQueries:
    def __init__(self, ports: CommandPersistenceQueriesPorts) -> None:
        self._ports = ports

    async def get_latest_for_task(
        self,
        *,
        task_id: int,
        exclude_fail_safe: bool = True,
    ) -> Optional[Mapping[str, Any]]:
        """Возвращает последнюю ae_command задачи.

        По умолчанию исключает fail-safe shutdown publishes (`_ae3_fail_safe`),
        чтобы они не маскировали штатный command-stage recovery.
        """
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            if exclude_fail_safe:
                row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM ae_commands
                    WHERE task_id = $1
                      AND NOT (COALESCE(payload, '{}'::jsonb) @> '{"_ae3_fail_safe": true}'::jsonb)
                    ORDER BY step_no DESC, id DESC
                    LIMIT 1
                    """,
                    task_id,
                )
            else:
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

    async def get_latest_by_planner_step(
        self,
        *,
        task_id: int,
        planner_step: str,
    ) -> Optional[Mapping[str, Any]]:
        """Возвращает последний execution record детерминированного шага planner.

        Fail-safe publishes исключаются: они не участвуют в штатном batch resume.
        """
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM ae_commands
                WHERE task_id = $1
                  AND planner_step = $2
                  AND NOT (COALESCE(payload, '{}'::jsonb) @> '{"_ae3_fail_safe": true}'::jsonb)
                ORDER BY step_no DESC, id DESC
                LIMIT 1
                """,
                task_id,
                planner_step,
            )
        return dict(row) if row is not None else None

    async def get_by_task_step(self, *, task_id: int, step_no: int) -> Optional[Mapping[str, Any]]:
        pool = await self._ports.global_get_pool()
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

    def normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)
