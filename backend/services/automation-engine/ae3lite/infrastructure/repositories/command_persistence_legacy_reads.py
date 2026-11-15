"""PgAeCommandRepository legacy reads: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional


@dataclass(frozen=True)
class CommandPersistenceLegacyReadsPorts:
    global_get_pool: Callable[..., Any]


class CommandPersistenceLegacyReads:
    def __init__(self, ports: CommandPersistenceLegacyReadsPorts) -> None:
        self._ports = ports

    async def resolve_greenhouse_uid(self, *, zone_id: int) -> Optional[str]:
        pool = await self._ports.global_get_pool()
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
        pool = await self._ports.global_get_pool()
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
        pool = await self._ports.global_get_pool()
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
        pool = await self._ports.global_get_pool()
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
        pool = await self._ports.global_get_pool()
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
