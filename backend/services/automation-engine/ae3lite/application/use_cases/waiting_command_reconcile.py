"""Фоновый reconcile `waiting_command` задач без republish в MQTT."""

from __future__ import annotations

import logging
from datetime import datetime, timezone as _tz
from typing import Any

from ae3lite.application.dto import WaitingCommandReconcileResult
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
        batch_limit: int = 32,
    ) -> None:
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._startup_recovery = startup_recovery_use_case
        self._batch_limit = max(1, int(batch_limit))

    async def run(
        self,
        *,
        now: datetime,
        worker_owner: str,
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

        for task in tasks:
            if await self._foreign_lease_blocks_reconcile(
                zone_id=int(task.zone_id),
                worker_owner=worker_owner,
                now=now,
            ):
                skipped_lease_tasks += 1
                WAITING_COMMAND_RECONCILE.labels(outcome="skipped_lease").inc()
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

    async def _foreign_lease_blocks_reconcile(
        self,
        *,
        zone_id: int,
        worker_owner: str,
        now: datetime,
    ) -> bool:
        get_lease = getattr(self._lease_repository, "get", None)
        if not callable(get_lease):
            return False

        lease = await get_lease(zone_id=zone_id)
        if lease is None:
            return False

        owner = str(getattr(lease, "owner", "") or "").strip()
        if owner == "" or owner == worker_owner:
            return False

        leased_until = getattr(lease, "leased_until", None)
        if leased_until is None:
            return True

        normalized_now = (
            now.astimezone(_tz.utc).replace(tzinfo=None)
            if now.tzinfo is not None
            else now.replace(microsecond=0)
        )
        lease_until = (
            leased_until.astimezone(_tz.utc).replace(tzinfo=None)
            if getattr(leased_until, "tzinfo", None) is not None
            else leased_until
        )
        return lease_until > normalized_now
