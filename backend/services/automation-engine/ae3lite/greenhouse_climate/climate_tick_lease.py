"""climate tick lease: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class ClimateTickLeasePorts:
    lease_owner_prefix: Callable[..., Any]
    execute: Callable[..., Any]
    fetch: Callable[..., Any]


class ClimateTickLease:
    def __init__(self, ports: ClimateTickLeasePorts) -> None:
        self._ports = ports

    def resolve_greenhouse_lease_owner(self, *, worker_owner: str | None) -> str:
        owner = str(worker_owner or "").strip()
        if owner:
            return f"{self._ports.lease_owner_prefix()}:{owner}"[:128]
        return self._ports.lease_owner_prefix()

    async def claim_greenhouse_lease(self, greenhouse_id: int, *, owner: str, ttl_sec: int) -> bool:
        now = datetime.now(timezone.utc)
        leased_until = now + timedelta(seconds=max(1, int(ttl_sec)))
        rows = await self._ports.fetch(
            """
            INSERT INTO greenhouse_automation_leases (greenhouse_id, owner, leased_until, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (greenhouse_id) DO UPDATE
            SET owner = EXCLUDED.owner,
                leased_until = EXCLUDED.leased_until,
                updated_at = EXCLUDED.updated_at
            WHERE greenhouse_automation_leases.owner = EXCLUDED.owner
               OR greenhouse_automation_leases.leased_until <= $4
            RETURNING greenhouse_id
            """,
            greenhouse_id,
            owner,
            leased_until,
            now,
        )
        return bool(rows)

    async def renew_greenhouse_lease(self, greenhouse_id: int, *, owner: str, ttl_sec: int) -> bool:
        now = datetime.now(timezone.utc)
        leased_until = now + timedelta(seconds=max(1, int(ttl_sec)))
        rows = await self._ports.fetch(
            """
            UPDATE greenhouse_automation_leases
            SET leased_until = $3,
                updated_at = $4
            WHERE greenhouse_id = $1
              AND owner = $2
            RETURNING greenhouse_id
            """,
            greenhouse_id,
            owner,
            leased_until,
            now,
        )
        return bool(rows)

    async def release_greenhouse_lease(self, greenhouse_id: int, *, owner: str) -> None:
        await self._ports.execute(
            """
            DELETE FROM greenhouse_automation_leases
            WHERE greenhouse_id = $1 AND owner = $2
            """,
            greenhouse_id,
            owner,
        )

    async def lock_owned_greenhouse_lease(self, conn: Any, *, greenhouse_id: int, owner: str) -> bool:
        row = await conn.fetchrow(
            """
            SELECT greenhouse_id FROM greenhouse_automation_leases
            WHERE greenhouse_id = $1 AND owner = $2 AND leased_until > now()
            FOR UPDATE
            """,
            greenhouse_id,
            owner,
        )
        return row is not None
