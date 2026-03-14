"""Read-only access to zone alerts for AE3 runtime gating."""

from __future__ import annotations

from typing import Iterable

import asyncpg

from common.db import get_pool


class PgZoneAlertRepository:
    """Minimal alert lookup used by AE3 stage guards."""

    async def has_active_alert(self, *, zone_id: int, code: str) -> bool:
        normalized_code = str(code or "").strip().lower()
        if zone_id <= 0 or normalized_code == "":
            return False

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1
                FROM alerts
                WHERE zone_id = $1
                  AND LOWER(code) = $2
                  AND status = 'ACTIVE'
                LIMIT 1
                """,
                zone_id,
                normalized_code,
            )
        return row is not None

    async def find_first_active_by_codes(
        self,
        *,
        zone_id: int,
        codes: Iterable[str],
        conn: asyncpg.Connection | None = None,
    ) -> dict[str, object] | None:
        normalized_codes = [
            str(code or "").strip().lower()
            for code in codes
            if str(code or "").strip()
        ]
        if zone_id <= 0 or not normalized_codes:
            return None

        if conn is not None:
            row = await conn.fetchrow(
                """
                SELECT id, code, status, severity
                FROM alerts
                WHERE zone_id = $1
                  AND status = 'ACTIVE'
                  AND LOWER(code) = ANY($2::text[])
                ORDER BY
                    CASE
                        WHEN LOWER(COALESCE(severity, '')) = 'critical' THEN 0
                        WHEN LOWER(COALESCE(severity, '')) = 'error' THEN 1
                        ELSE 2
                    END,
                    id ASC
                LIMIT 1
                """,
                zone_id,
                normalized_codes,
            )
        else:
            pool = await get_pool()
            async with pool.acquire() as pool_conn:
                row = await pool_conn.fetchrow(
                    """
                    SELECT id, code, status, severity
                    FROM alerts
                    WHERE zone_id = $1
                      AND status = 'ACTIVE'
                      AND LOWER(code) = ANY($2::text[])
                    ORDER BY
                        CASE
                            WHEN LOWER(COALESCE(severity, '')) = 'critical' THEN 0
                            WHEN LOWER(COALESCE(severity, '')) = 'error' THEN 1
                            ELSE 2
                        END,
                        id ASC
                    LIMIT 1
                    """,
                    zone_id,
                    normalized_codes,
                )
        return dict(row) if row is not None else None
