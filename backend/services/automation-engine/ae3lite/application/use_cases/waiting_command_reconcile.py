"""Фоновый reconcile `waiting_command` задач без republish в MQTT."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto import WaitingCommandReconcileResult
from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    escalate_foreign_lease_stale_task,
    record_foreign_lease_skip,
    resolve_foreign_active_lease,
)
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.infrastructure.metrics import WAITING_COMMAND_RECONCILE

logger = logging.getLogger(__name__)


class WaitingCommandReconcileUseCase:
    """Периодически проверяет legacy `commands` для `waiting_command` задач."""

    def __init__(
        self,
        *,
        task_repository: Any,
        lease_repository: Any,
        startup_recovery_use_case: StartupRecoveryUseCase,
        alert_repository: Any | None = None,
        foreign_lease_skip_escalate_sec: int = 300,
        batch_limit: int = 32,
    ) -> None:
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._startup_recovery = startup_recovery_use_case
        self._alert_repository = alert_repository
        self._foreign_lease_skip_escalate_sec = max(1, int(foreign_lease_skip_escalate_sec))
        self._batch_limit = max(1, int(batch_limit))

    async def run(
        self,
        *,
        now: datetime,
        worker_owner: str,
        inflight_task_ids: frozenset[int] | None = None,
    ) -> WaitingCommandReconcileResult:
        list_waiting = getattr(self._task_repository, "list_waiting_command_for_reconcile", None)
        if not callable(list_waiting):
            return WaitingCommandReconcileResult(
                scanned_tasks=0,
                progressed_tasks=0,
                failed_tasks=0,
                unchanged_tasks=0,
                skipped_lease_tasks=0,
                terminal_outcomes=(),
            )

        tasks = await list_waiting(limit=self._batch_limit)
        progressed_tasks = 0
        failed_tasks = 0
        unchanged_tasks = 0
        skipped_lease_tasks = 0
        terminal_outcomes = []
        inflight_ids = inflight_task_ids or frozenset()

        for task in tasks:
            if int(task.id) in inflight_ids:
                WAITING_COMMAND_RECONCILE.labels(outcome="skipped_inflight").inc()
                continue

            foreign_action, foreign_ctx = await resolve_foreign_active_lease(
                lease_repository=self._lease_repository,
                zone_id=int(task.zone_id),
                worker_owner=worker_owner,
                task=task,
                now=now,
                escalate_sec=self._foreign_lease_skip_escalate_sec,
            )
            if foreign_action == ForeignLeaseAction.SKIP:
                skipped_lease_tasks += 1
                record_foreign_lease_skip(recovery_source="waiting_command_reconcile")
                WAITING_COMMAND_RECONCILE.labels(outcome="skipped_lease").inc()
                continue
            if foreign_action == ForeignLeaseAction.ESCALATE:
                failed = await escalate_foreign_lease_stale_task(
                    task_repository=self._task_repository,
                    alert_repository=self._alert_repository,
                    task=task,
                    now=now,
                    recovery_source="waiting_command_reconcile",
                    lease_context=foreign_ctx,
                )
                if failed is not None:
                    failed_tasks += 1
                    WAITING_COMMAND_RECONCILE.labels(outcome="failed").inc()
                continue

            try:
                outcome, terminal_outcome, _observability_task = (
                    await self._startup_recovery.reconcile_waiting_command_task(
                        task=task,
                        now=now,
                        recovery_source="waiting_command_reconcile",
                    )
                )
            except Exception:
                logger.warning(
                    "Waiting command reconcile: unexpected failure task_id=%s zone_id=%s",
                    task.id,
                    task.zone_id,
                    exc_info=True,
                )
                WAITING_COMMAND_RECONCILE.labels(outcome="error").inc()
                continue

            WAITING_COMMAND_RECONCILE.labels(outcome=outcome).inc()
            if terminal_outcome is not None:
                terminal_outcomes.append(terminal_outcome)
            if outcome in {"recovered_waiting_command", "completed"}:
                progressed_tasks += 1
            elif outcome == "failed":
                failed_tasks += 1
            elif outcome == "waiting_command":
                unchanged_tasks += 1

        return WaitingCommandReconcileResult(
            scanned_tasks=len(tasks),
            progressed_tasks=progressed_tasks,
            failed_tasks=failed_tasks,
            unchanged_tasks=unchanged_tasks,
            skipped_lease_tasks=skipped_lease_tasks,
            terminal_outcomes=tuple(terminal_outcomes),
        )
