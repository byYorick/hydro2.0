"""PostgreSQL-репозиторий zone lease для AE3-Lite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg

from ae3lite.domain.entities import ZoneLease
from common.db import get_pool


class PgZoneLeaseRepository:
    """Репозиторий zone lease для модели single-writer."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    async def claim(
        self,
        *,
        zone_id: int,
        owner: str,
        now: datetime,
        lease_ttl_sec: int,
    ) -> Optional[ZoneLease]:
        normalized_now = self._normalize_timestamp(now)
        leased_until = normalized_now + timedelta(seconds=max(1, int(lease_ttl_sec)))
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ae_zone_leases (zone_id, owner, leased_until, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (zone_id) DO UPDATE
                SET owner = EXCLUDED.owner,
                    leased_until = EXCLUDED.leased_until,
                    updated_at = EXCLUDED.updated_at
                WHERE ae_zone_leases.owner = EXCLUDED.owner
                   OR ae_zone_leases.leased_until <= $4
                RETURNING zone_id, owner, leased_until, updated_at
                """,
                zone_id,
                owner,
                leased_until,
                normalized_now,
            )
        return ZoneLease.from_row(row) if row is not None else None

    async def extend(
        self,
        *,
        zone_id: int,
        owner: str,
        now: datetime,
        lease_ttl_sec: int,
    ) -> bool:
        """Продлевает lease текущего owner.

        Возвращает ``True``, если lease продлён, и ``False``, если lease уже принадлежит другому owner.
        """
        normalized_now = self._normalize_timestamp(now)
        leased_until = normalized_now + timedelta(seconds=max(1, int(lease_ttl_sec)))
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ae_zone_leases
                SET leased_until = $3,
                    updated_at = $2
                WHERE zone_id = $1
                  AND owner = $4
                RETURNING zone_id
                """,
                zone_id,
                normalized_now,
                leased_until,
                owner,
            )
        return row is not None

    async def release(self, *, zone_id: int, owner: str) -> bool:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                DELETE FROM ae_zone_leases
                WHERE zone_id = $1
                  AND owner = $2
                RETURNING zone_id
                """,
                zone_id,
                owner,
            )
        return row is not None

    async def get(
        self,
        *,
        zone_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Optional[ZoneLease]:
        if conn is not None:
            row = await conn.fetchrow(
                """
                SELECT zone_id, owner, leased_until, updated_at
                FROM ae_zone_leases
                WHERE zone_id = $1
                LIMIT 1
                """,
                zone_id,
            )
        else:
            pool = await get_pool()
            async with pool.acquire() as pool_conn:
                row = await pool_conn.fetchrow(
                    """
                    SELECT zone_id, owner, leased_until, updated_at
                    FROM ae_zone_leases
                    WHERE zone_id = $1
                    LIMIT 1
                    """,
                    zone_id,
                )
        return ZoneLease.from_row(row) if row is not None else None

    async def release_expired(self, *, now: datetime) -> int:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                DELETE FROM ae_zone_leases
                WHERE leased_until <= $1
                RETURNING zone_id
                """,
                normalized_now,
            )
        return len(rows)
