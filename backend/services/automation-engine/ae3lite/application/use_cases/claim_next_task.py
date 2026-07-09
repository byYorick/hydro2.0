"""Берёт следующую pending-задачу AE3-Lite и zone lease."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Protocol, Tuple

from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError
from common.infra_alerts import send_infra_alert

logger = logging.getLogger(__name__)

_RELEASE_CLAIM_MAX_ATTEMPTS = 3
_RELEASE_CLAIM_BACKOFF_SEC = (0.05, 0.1)


class AutomationTaskRepository(Protocol):
    async def claim_next_pending(self, *, owner: str, now: datetime) -> Optional[AutomationTask]:
        ...

    async def next_pending_due_at(self) -> Optional[datetime]:
        ...

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        ...

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> Optional[AutomationTask]:
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

    async def _release_claim_with_retry(self, *, task_id: int, owner: str, now: datetime) -> bool:
        for attempt in range(_RELEASE_CLAIM_MAX_ATTEMPTS):
            reverted = await self._task_repository.release_claim(task_id=task_id, owner=owner, now=now)
            if reverted:
                return True
            if attempt + 1 < _RELEASE_CLAIM_MAX_ATTEMPTS:
                backoff_sec = _RELEASE_CLAIM_BACKOFF_SEC[min(attempt, len(_RELEASE_CLAIM_BACKOFF_SEC) - 1)]
                await asyncio.sleep(backoff_sec)
        return False

    async def _fail_task_after_rollback_exhausted(
        self,
        *,
        task: AutomationTask,
        owner: str,
        now: datetime,
    ) -> None:
        error_code = "ae3_claim_rollback_failed"
        error_message = (
            f"Не удалось откатить claimed task {task.id} после конфликта zone lease"
        )
        fail_for_recovery = getattr(self._task_repository, "fail_for_recovery", None)
        if callable(fail_for_recovery):
            try:
                await fail_for_recovery(
                    task_id=task.id,
                    error_code=error_code,
                    error_message=error_message,
                    now=now,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Не удалось перевести задачу в failed после провала claim rollback: "
                    "task_id=%s zone_id=%s owner=%s",
                    task.id,
                    task.zone_id,
                    owner,
                    exc_info=True,
                )
        try:
            await send_infra_alert(
                code=error_code,
                alert_type="AE3 Claim Rollback Failed",
                message=(
                    "Claim задачи не удалось откатить после конфликта zone lease; "
                    "задача переведена в failed для recovery."
                ),
                severity="critical",
                zone_id=int(task.zone_id),
                service="automation-engine",
                component="claim_next_task",
                details={
                    "task_id": int(task.id),
                    "owner": owner,
                    "message": error_message,
                },
            )
        except Exception:
            logger.warning(
                "Не удалось отправить infra alert после провала claim rollback: "
                "task_id=%s zone_id=%s owner=%s",
                task.id,
                task.zone_id,
                owner,
                exc_info=True,
            )

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

        reverted = await self._release_claim_with_retry(task_id=task.id, owner=owner, now=now)
        if not reverted:
            logger.error(
                "Откат claim задачи завершился ошибкой после retry: конфликт zone lease и release недоступен "
                "task_id=%s zone_id=%s owner=%s",
                task.id,
                task.zone_id,
                owner,
            )
            await self._fail_task_after_rollback_exhausted(task=task, owner=owner, now=now)
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
