"""PgAeCommandRepository publication: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass(frozen=True)
class CommandPersistencePublicationPorts:
    normalize_timestamp: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class CommandPersistencePublication:
    def __init__(self, ports: CommandPersistencePublicationPorts) -> None:
        self._ports = ports

    async def mark_publish_published_unconfirmed(self, *, ae_command_id: int, now: datetime) -> bool:
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
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
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
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
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
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
        pool = await self._ports.global_get_pool()
        normalized_now = self._ports.normalize_timestamp(now)
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
