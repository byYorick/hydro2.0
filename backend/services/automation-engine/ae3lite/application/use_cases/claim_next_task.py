"""Claim next pending AE3-Lite task and zone lease."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Tuple

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError


class AutomationTaskRepository(Protocol):
    async def claim_next_pending(self, *, owner: str, now: datetime) -> Optional[AutomationTask]:
        ...

    async def next_pending_due_at(self) -> Optional[datetime]:
        ...

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        ...


class ZoneLeaseRepository(Protocol):
    async def claim(
        self,
        *,
        zone_id: int,
        owner: str,
        now: datetime,
        lease_ttl_sec: int,
    ) -> Optional[ZoneLease]:
        ...


class ClaimNextTaskUseCase:
    """Claim next pending task and acquire zone lease for single-writer execution."""

    def __init__(
        self,
        *,
        task_repository: AutomationTaskRepository,
        zone_lease_repository: ZoneLeaseRepository,
        lease_ttl_sec: int,
    ) -> None:
        self._task_repository = task_repository
        self._zone_lease_repository = zone_lease_repository
        self._lease_ttl_sec = max(1, int(lease_ttl_sec))

    async def run(self, *, owner: str, now: datetime) -> Optional[Tuple[AutomationTask, ZoneLease]]:
        task = await self._task_repository.claim_next_pending(owner=owner, now=now)
        if task is None:
            return None

        lease = await self._zone_lease_repository.claim(
            zone_id=task.zone_id,
            owner=owner,
            now=now,
            lease_ttl_sec=self._lease_ttl_sec,
        )
        if lease is not None:
            return task, lease

        reverted = await self._task_repository.release_claim(task_id=task.id, owner=owner, now=now)
        if not reverted:
            raise TaskClaimRollbackError(
                f"Failed to rollback claimed task {task.id} after zone lease conflict"
            )
        return None

    async def next_pending_due_at(self) -> Optional[datetime]:
        return await self._task_repository.next_pending_due_at()
