"""Воркер AE4: claim, тик зон ae4, исполнение, подъём незакрытого кадра."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from common.db import get_pool
from common.history_logger_gateway import HistoryLoggerGateway

from ae4.application.execute_claimed import execute_claimed_task
from ae4.application.frame_recovery import recover_inflight_tasks
from ae4.application.zone_tick import tick_ae4_zones
from ae4.infrastructure.metrics import (
    OLDEST_ACTIVE_TASK_AGE_SECONDS,
    PENDING_TASKS,
    TICK_DURATION,
)
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    ClaimedTask,
    PgAutomationTaskRepository,
)
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.runtime.env import Ae4RuntimeConfig

logger = logging.getLogger(__name__)

# Отдельный owner: общий AE_WORKER_OWNER принадлежит воркеру AE3.
AE4_WORKER_OWNER = "ae4-runtime-worker"


class Ae4RuntimeWorker:
    """Опрос claim зон ae4, тик политики и исполнение claimed-задач."""

    def __init__(
        self,
        *,
        config: Ae4RuntimeConfig,
        repository: PgAutomationTaskRepository | None = None,
        lease_repository: PgZoneLeaseRepository | None = None,
        command_repository: PgAeCommandRepository | None = None,
        gateway: HistoryLoggerGateway | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._repository = repository or PgAutomationTaskRepository()
        self._lease_repository = lease_repository or PgZoneLeaseRepository()
        self._command_repository = command_repository or PgAeCommandRepository()
        self._gateway = gateway or HistoryLoggerGateway(metrics_prefix="ae4")
        self._now_fn = now_fn or _utcnow
        self._stop = asyncio.Event()
        self._startup_recovery_done = False

    async def claim_next(self, *, now: datetime) -> ClaimedTask | None:
        return await self._repository.claim_next_pending(
            owner=AE4_WORKER_OWNER,
            now=now,
        )

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
            tick_started = time.monotonic()
            try:
                if not self._startup_recovery_done:
                    await self._run_startup_recovery()
                    self._startup_recovery_done = True
                await self._fail_stale_inflight()
                await self._claim_due()
                await self._tick_zones()
                await self._claim_due()
                await self._refresh_metrics()
            except Exception:
                logger.exception("AE4: цикл воркера не выполнен")
            finally:
                TICK_DURATION.observe(max(0.0, time.monotonic() - tick_started))
            await self._sleep()

    async def shutdown(self) -> None:
        self._stop.set()

    async def _refresh_metrics(self) -> None:
        pending = await self._repository.count_pending()
        PENDING_TASKS.set(float(pending))
        age = await self._repository.oldest_active_age_seconds(now=self._now_fn())
        OLDEST_ACTIVE_TASK_AGE_SECONDS.set(float(age))

    async def _run_startup_recovery(self) -> None:
        recovered = await recover_inflight_tasks(
            task_repository=self._repository,
            command_repository=self._command_repository,
            gateway=self._gateway,
            worker_owner=AE4_WORKER_OWNER,
            now=self._now_fn(),
        )
        if recovered:
            logger.info(
                "AE4: подъём незакрытых кадров",
                extra={"recovered": recovered, "owner": AE4_WORKER_OWNER},
            )

    async def _tick_zones(self) -> None:
        summary = await tick_ae4_zones(
            now=self._now_fn(),
            task_repository=self._repository,
            lease_repository=self._lease_repository,
            gateway=self._gateway,
            wake_climate=True,
        )
        if summary.get("created") or summary.get("failed"):
            logger.info(
                "AE4 тик зон",
                extra={
                    "zones": summary.get("zones"),
                    "tasks_created": summary.get("created"),
                    "paused": summary.get("paused"),
                    "tasks_failed": summary.get("failed"),
                    "climate_woken": summary.get("climate_woken"),
                },
            )

    async def _fail_stale_inflight(self) -> None:
        """Задача без движения дольше порога не остаётся в waiting_command."""
        from ae4.application.frame_recovery import fail_stale_inflight_tasks

        failed = await fail_stale_inflight_tasks(
            task_repository=self._repository,
            worker_owner=AE4_WORKER_OWNER,
            now=self._now_fn(),
            max_age_sec=self._config.stale_task_max_age_sec,
        )
        if failed:
            logger.warning(
                "AE4: зависшие задачи закрыты",
                extra={"failed": failed, "owner": AE4_WORKER_OWNER},
            )

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
            await execute_claimed_task(
                claimed_task_id=claimed.id,
                zone_id=claimed.zone_id,
                worker_owner=AE4_WORKER_OWNER,
                now=self._now_fn(),
                task_repository=self._repository,
                command_repository=self._command_repository,
                lease_repository=self._lease_repository,
                gateway=self._gateway,
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
