"""PgAutomationTaskRepository metrics: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

import asyncpg

from ae3lite.domain.entities import AutomationTask
from ae3lite.infrastructure.metrics import (
    OLDEST_ACTIVE_TASK_AGE_SECONDS,
    OLDEST_PENDING_TASK_AGE_SECONDS,
    PENDING_TASKS,
    TASK_DURATION_SECONDS,
)
from ae3lite.infrastructure.repositories.task_persistence_shared import logger


@dataclass(frozen=True)
class TaskPersistenceMetricsPorts:
    fetch: Callable[..., Awaitable[Any]]
    fetchrow: Callable[..., Awaitable[Any]]
    normalize_timestamp: Callable[..., Any]
    task_from_row: Callable[..., Any]


class TaskPersistenceMetrics:
    def __init__(self, ports: TaskPersistenceMetricsPorts) -> None:
        self._ports = ports

    async def refresh_pending_queue_metrics(self, *, now: datetime) -> None:
        """Обновляет gauge метрики очереди pending одним SQL-запросом."""
        normalized_now = self._ports.normalize_timestamp(now)
        row = await self._ports.fetchrow(
            """
            SELECT
                COUNT(*)::double precision AS pending_count,
                COALESCE(
                    EXTRACT(EPOCH FROM ($1 - MIN(created_at))),
                    0
                )::double precision AS oldest_age_sec
            FROM ae_tasks
            WHERE status = 'pending'
            """,
            normalized_now,
        )
        if row is None:
            PENDING_TASKS.set(0)
            OLDEST_PENDING_TASK_AGE_SECONDS.set(0)
            return
        PENDING_TASKS.set(float(row["pending_count"] or 0))
        OLDEST_PENDING_TASK_AGE_SECONDS.set(max(0.0, float(row["oldest_age_sec"] or 0)))

    async def refresh_active_task_age_metrics(self, *, now: datetime) -> None:
        """Обновляет gauge возраста самой старой активной задачи по статусу."""
        normalized_now = self._ports.normalize_timestamp(now)
        for status in ("claimed", "running", "waiting_command"):
            OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status=status).set(0.0)
        rows = await self._ports.fetch(
            """
            SELECT
                status,
                COALESCE(
                    EXTRACT(EPOCH FROM ($1 - MIN(updated_at))),
                    0
                )::double precision AS oldest_age_sec
            FROM ae_tasks
            WHERE status IN ('claimed', 'running', 'waiting_command')
            GROUP BY status
            """,
            normalized_now,
        )
        for row in rows:
            status = str(row["status"] or "").strip()
            if not status:
                continue
            OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status=status).set(max(0.0, float(row["oldest_age_sec"] or 0)))

    @staticmethod
    def observe_task_duration(*, row: asyncpg.Record | None, outcome: str) -> None:
        if row is None:
            return
        created_at = row.get("created_at")
        completed_at = row.get("completed_at") or row.get("updated_at")
        if created_at is None or completed_at is None:
            return
        duration_sec = max(0.0, (completed_at - created_at).total_seconds())
        topology = str(row.get("topology") or "unknown").strip() or "unknown"
        TASK_DURATION_SECONDS.labels(topology=topology, outcome=outcome).observe(duration_sec)

    @staticmethod
    def log_fsm_success(
        *,
        action: str,
        task: AutomationTask,
        from_status: str,
        to_status: str,
        owner: str,
    ) -> None:
        logger.info(
            "AE3 task FSM %s",
            action,
            extra={
                "task_id": int(task.id),
                "zone_id": int(task.zone_id),
                "from_status": from_status,
                "to_status": to_status,
                "owner": owner,
            },
        )

    async def log_fsm_cas_miss(
        self,
        *,
        action: str,
        task_id: int,
        to_status: str,
        owner: str,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        row = await self._ports.fetchrow("SELECT * FROM ae_tasks WHERE id = $1", task_id, conn=conn)
        current = self._ports.task_from_row(row)
        from_status = str(current.status if current is not None else "missing")
        zone_id = int(current.zone_id) if current is not None else None
        logger.warning(
            "AE3 task FSM CAS miss %s",
            action,
            extra={
                "task_id": int(task_id),
                "zone_id": zone_id,
                "from_status": from_status,
                "to_status": to_status,
                "owner": owner,
            },
        )
