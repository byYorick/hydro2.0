"""Read-only access to zone alerts for AE3 runtime gating."""

from __future__ import annotations

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
