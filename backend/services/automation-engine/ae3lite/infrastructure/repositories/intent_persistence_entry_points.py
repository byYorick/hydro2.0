"""PgZoneIntentRepository entry points: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.api.contracts import (
    StartCycleRequest,
    StartIrrigationRequest,
    StartLightingTickRequest,
    StartSolutionChangeRequest,
    StartSolutionTopupRequest,
)


@dataclass(frozen=True)
class IntentPersistenceEntryPointsPorts:
    claim_by_idempotency_key: Callable[..., Awaitable[Any]]


class IntentPersistenceEntryPoints:
    def __init__(self, ports: IntentPersistenceEntryPointsPorts) -> None:
        self._ports = ports

    async def claim_start_cycle(
        self,
        *,
        zone_id: int,
        req: StartCycleRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._ports.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_irrigation(
        self,
        *,
        zone_id: int,
        req: StartIrrigationRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._ports.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_lighting_tick(
        self,
        *,
        zone_id: int,
        req: StartLightingTickRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._ports.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_solution_topup(
        self,
        *,
        zone_id: int,
        req: StartSolutionTopupRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._ports.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )

    async def claim_start_solution_change(
        self,
        *,
        zone_id: int,
        req: StartSolutionChangeRequest,
        now: datetime,
        claimed_stale_after_sec: int = 180,
        running_stale_after_sec: int = 1800,
    ) -> dict[str, Any]:
        return await self._ports.claim_by_idempotency_key(
            zone_id=zone_id,
            idempotency_key=req.idempotency_key,
            now=now,
            claimed_stale_after_sec=claimed_stale_after_sec,
            running_stale_after_sec=running_stale_after_sec,
        )
