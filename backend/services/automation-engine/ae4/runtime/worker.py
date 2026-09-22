"""Воркер AE4: забирает только задачи зон ``automation_runtime = ae4``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from common.db import get_pool

from ae4.infrastructure.repositories.automation_task_repository import (
    ClaimedTask,
    PgAutomationTaskRepository,
)
from ae4.runtime.env import Ae4RuntimeConfig

logger = logging.getLogger(__name__)

# Отдельный owner: общий AE_WORKER_OWNER принадлежит воркеру AE3.
AE4_WORKER_OWNER = "ae4-runtime-worker"


class Ae4RuntimeWorker:
    """Опрос claim. Исполнения стадий в этом воркере нет: он только переводит pending в claimed."""

    def __init__(
        self,
        *,
        config: Ae4RuntimeConfig,
        repository: PgAutomationTaskRepository | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._repository = repository or PgAutomationTaskRepository()
        self._now_fn = now_fn or _utcnow
        self._stop = asyncio.Event()

    async def claim_next(self, *, now: datetime) -> ClaimedTask | None:
        return await self._repository.claim_next_pending(owner=AE4_WORKER_OWNER, now=now)

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await get_pool()
            except Exception:
                logger.exception("AE4: пул PostgreSQL недоступен")
                await self._sleep()
                continue
            logger.info("AE4 воркер запущен", extra={"owner": AE4_WORKER_OWNER})
            break

        while not self._stop.is_set():
            try:
                await self._claim_due()
            except Exception:
                logger.exception("AE4: claim не выполнен")
            await self._sleep()

    async def shutdown(self) -> None:
        self._stop.set()

    async def _claim_due(self) -> None:
        while not self._stop.is_set():
            claimed = await self.claim_next(now=self._now_fn())
            if claimed is None:
                return
            logger.info(
                "AE4 забрал задачу",
                extra={
                    "task_id": claimed.id,
                    "zone_id": claimed.zone_id,
                    "owner": AE4_WORKER_OWNER,
                },
            )

    async def _sleep(self) -> None:
        try:
            await asyncio.wait_for(
                self._stop.wait(),
                timeout=self._config.reconcile_poll_interval_sec,
            )
        except TimeoutError:
            return


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["AE4_WORKER_OWNER", "Ae4RuntimeWorker"]
