"""Берёт следующую pending-задачу AE3-Lite и zone lease."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Protocol, Tuple

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError

logger = logging.getLogger(__name__)


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
    """Забирает следующую pending-задачу и получает zone lease для single-writer выполнения."""

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
            logger.error(
                "Откат claim задачи завершился ошибкой: конфликт zone lease и release недоступен task_id=%s zone_id=%s owner=%s",
                task.id,
                task.zone_id,
                owner,
            )
            raise TaskClaimRollbackError(
                f"Не удалось откатить claimed task {task.id} после конфликта zone lease"
            )
        logger.debug(
            "Claim задачи откатан после конфликта zone lease: task_id=%s zone_id=%s owner=%s",
            task.id,
            task.zone_id,
            owner,
        )
        return None

    async def next_pending_due_at(self) -> Optional[datetime]:
        return await self._task_repository.next_pending_due_at()
