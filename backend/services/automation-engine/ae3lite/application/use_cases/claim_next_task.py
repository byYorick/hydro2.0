"""Берёт следующую pending-задачу AE3-Lite и zone lease."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, Tuple

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError


class AutomationTaskRepository(Protocol):
    async def claim_next_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
    ) -> Optional[Tuple[AutomationTask, ZoneLease]]:
        ...

    async def next_pending_due_at(self) -> Optional[datetime]:
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
    """Забирает следующую pending-задачу и получает zone lease для single-writer выполнения."""

    def __init__(
        self,
        *,
        task_repository: AutomationTaskRepository,
        zone_lease_repository: ZoneLeaseRepository,
        lease_ttl_sec: int,
        overall_deadline_sec: int = 604800,
    ) -> None:
        self._task_repository = task_repository
        self._zone_lease_repository = zone_lease_repository
        self._lease_ttl_sec = max(1, int(lease_ttl_sec))
        self._overall_deadline_sec = max(60, int(overall_deadline_sec))

    async def run(
        self,
        *,
        owner: str,
        now: datetime,
        process_run_id: str,
    ) -> Optional[Tuple[AutomationTask, ZoneLease]]:
        """Один claim task+lease. Конфликт lease откатывается внутри транзакции репозитория."""
        normalized_owner = str(owner or "").strip()
        normalized_run = str(process_run_id or "").strip()
        if not normalized_owner or not normalized_run:
            raise TaskClaimRollbackError("claim требует owner и process_run_id")
        claim = getattr(self._task_repository, "claim_next_with_zone_lease", None)
        if not callable(claim):
            raise TaskClaimRollbackError("claim_next_with_zone_lease недоступен")
        return await claim(
            owner=normalized_owner,
            process_run_id=normalized_run,
            now=now,
            lease_ttl_sec=self._lease_ttl_sec,
            overall_deadline_sec=self._overall_deadline_sec,
        )

    async def next_pending_due_at(self) -> Optional[datetime]:
        return await self._task_repository.next_pending_due_at()
