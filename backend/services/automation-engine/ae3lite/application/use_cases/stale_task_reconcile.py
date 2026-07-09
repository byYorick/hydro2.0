"""Периодический healing застрявших claimed/running/waiting_command задач (TaskJanitor)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as _tz
from typing import Any

from ae3lite.application.dto import StaleTaskReconcileResult
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    escalate_foreign_lease_stale_task,
    record_foreign_lease_skip,
    resolve_foreign_active_lease,
)
from ae3lite.domain.entities import AutomationTask
from ae3lite.infrastructure.metrics import STALE_TASKS_RECLAIMED, inc_observability_write_failed
from common.db import create_zone_event

logger = logging.getLogger(__name__)

_STALE_TASK_RECLAIMED_EVENT = "AE_TASK_RECLAIMED"
_PROGRESS_OUTCOMES = frozenset({"recovered_waiting_command", "completed"})
_STALE_WAITING_COMMAND_ERROR = "ae3_stale_waiting_command"


class StaleTaskReconcileUseCase:
    """Освобождает просроченные lease и переводит stale active задачи в безопасное состояние."""

    def __init__(
        self,
        *,
        task_repository: Any,
        lease_repository: Any,
        alert_repository: Any | None = None,
        startup_recovery_use_case: Any | None = None,
        stale_claimed_ttl_sec: int = 120,
        stale_running_ttl_sec: int = 960,
        stale_waiting_command_ttl_sec: int = 210,
        stale_unconfirmed_command_ttl_sec: int = 120,
        foreign_lease_skip_escalate_sec: int = 300,
        batch_limit: int = 16,
    ) -> None:
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._alert_repository = alert_repository
        self._startup_recovery_use_case = startup_recovery_use_case
        self._stale_claimed_ttl_sec = max(1, int(stale_claimed_ttl_sec))
        self._stale_running_ttl_sec = max(1, int(stale_running_ttl_sec))
        self._stale_waiting_command_ttl_sec = max(1, int(stale_waiting_command_ttl_sec))
        self._stale_unconfirmed_command_ttl_sec = max(1, int(stale_unconfirmed_command_ttl_sec))
        self._foreign_lease_skip_escalate_sec = max(1, int(foreign_lease_skip_escalate_sec))
        self._batch_limit = max(1, min(int(batch_limit), 16))

    async def run(
        self,
        *,
        now: datetime,
        owner: str,
    ) -> StaleTaskReconcileResult:
        released_expired_leases = await self._lease_repository.release_expired(now=now)

        refresh_metrics = getattr(self._task_repository, "refresh_pending_queue_metrics", None)
        if callable(refresh_metrics):
            try:
                await refresh_metrics(now=now)
            except Exception:
                logger.warning(
                    "Stale task reconcile: failed to refresh pending queue metrics",
                    exc_info=True,
                )

        list_stale = getattr(self._task_repository, "list_stale_claimed_running_for_reconcile", None)
        if not callable(list_stale):
            return StaleTaskReconcileResult(
                released_expired_leases=released_expired_leases,
                scanned_tasks=0,
                requeued_tasks=0,
                failed_tasks=0,
                skipped_lease_tasks=0,
            )

        tasks = await list_stale(
            now=now,
            stale_claimed_before=self._stale_before(now, self._stale_claimed_ttl_sec),
            stale_running_before=self._stale_before(now, self._stale_running_ttl_sec),
            stale_waiting_command_before=self._stale_before(now, self._stale_waiting_command_ttl_sec),
            stale_unconfirmed_before=self._stale_before(now, self._stale_unconfirmed_command_ttl_sec),
            limit=self._batch_limit,
        )

        requeued_tasks = 0
        failed_tasks = 0
        skipped_lease_tasks = 0
        worker_owner = str(owner or "").strip()

        for task in tasks:
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
                record_foreign_lease_skip(recovery_source="stale_task_reconcile")
                continue
            if foreign_action == ForeignLeaseAction.ESCALATE:
                failed = await escalate_foreign_lease_stale_task(
                    task_repository=self._task_repository,
                    alert_repository=self._alert_repository,
                    task=task,
                    now=now,
                    recovery_source="stale_task_reconcile",
                    lease_context=foreign_ctx,
                )
                if failed is not None:
                    failed_tasks += 1
                    STALE_TASKS_RECLAIMED.labels(
                        from_status=str(task.status or "").strip().lower(),
                        action="fail",
                    ).inc()
                continue

            from_status = str(task.status or "").strip().lower()
            age_sec = self._task_age_sec(task=task, now=now)

            reconcile_action = await self._try_command_reconcile(task=task, now=now)
            if reconcile_action == "progressed":
                requeued_tasks += 1
                await self._release_lease_after_action(task=task, now=now)
                STALE_TASKS_RECLAIMED.labels(from_status=from_status, action="reconcile").inc()
                await self._record_task_reclaimed_event(
                    zone_id=int(task.zone_id),
                    task_id=int(task.id),
                    from_status=from_status,
                    action="reconcile",
                    age_sec=age_sec,
                )
                logger.info(
                    "Stale task reconcile: command reconcile progressed task_id=%s zone_id=%s from_status=%s age_sec=%s owner=%s",
                    task.id,
                    task.zone_id,
                    from_status,
                    age_sec,
                    worker_owner,
                )
                continue
            if reconcile_action == "failed":
                failed_tasks += 1
                await self._release_lease_after_action(task=task, now=now)
                STALE_TASKS_RECLAIMED.labels(from_status=from_status, action="fail").inc()
                await self._record_task_reclaimed_event(
                    zone_id=int(task.zone_id),
                    task_id=int(task.id),
                    from_status=from_status,
                    action="fail",
                    age_sec=age_sec,
                )
                continue

            has_commands = await self._task_has_ae_commands(task_id=int(task.id))
            stale_waiting_command = from_status == "waiting_command"
            if not has_commands:
                requeued = await self._requeue_stale_task(task=task, now=now)
                if requeued is None:
                    logger.warning(
                        "Stale task reconcile: requeue noop task_id=%s zone_id=%s from_status=%s",
                        task.id,
                        task.zone_id,
                        from_status,
                    )
                    continue
                action = "requeue"
                requeued_tasks += 1
                await self._release_lease_after_action(task=task, now=now)
            else:
                error_code = (
                    _STALE_WAITING_COMMAND_ERROR
                    if stale_waiting_command
                    else "ae3_stale_task_reclaimed"
                )
                error_message = (
                    f"Задача {task.id} застряла в waiting_command и переведена в failed janitor'ом"
                    if stale_waiting_command
                    else f"Задача {task.id} застряла в {from_status} и переведена в failed janitor'ом"
                )
                failed = await self._task_repository.fail_for_recovery(
                    task_id=int(task.id),
                    error_code=error_code,
                    error_message=error_message,
                    now=now,
                )
                if failed is None:
                    logger.warning(
                        "Stale task reconcile: fail noop task_id=%s zone_id=%s from_status=%s",
                        task.id,
                        task.zone_id,
                        from_status,
                    )
                    continue
                action = "fail"
                failed_tasks += 1
                await emit_task_failed_alert(
                    alert_repository=self._alert_repository,
                    task=failed,
                    error_code=error_code,
                    error_message=str(failed.error_message or ""),
                    now=now,
                    extra_details={"recovery_source": "stale_task_reconcile"},
                )
                await self._release_lease_after_action(task=failed, now=now)

            STALE_TASKS_RECLAIMED.labels(from_status=from_status, action=action).inc()
            await self._record_task_reclaimed_event(
                zone_id=int(task.zone_id),
                task_id=int(task.id),
                from_status=from_status,
                action=action,
                age_sec=age_sec,
            )
            logger.info(
                "Stale task reconcile: reclaimed task_id=%s zone_id=%s from_status=%s action=%s age_sec=%s owner=%s",
                task.id,
                task.zone_id,
                from_status,
                action,
                age_sec,
                worker_owner,
            )

        return StaleTaskReconcileResult(
            released_expired_leases=released_expired_leases,
            scanned_tasks=len(tasks),
            requeued_tasks=requeued_tasks,
            failed_tasks=failed_tasks,
            skipped_lease_tasks=skipped_lease_tasks,
        )

    async def _try_command_reconcile(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> str | None:
        """Пробует reconcile command path; возвращает progressed/failed/unchanged/None."""
        if self._startup_recovery_use_case is None:
            return None

        from_status = str(task.status or "").strip().lower()
        needs_reconcile = from_status == "waiting_command" or await self._task_has_unconfirmed_commands(
            task_id=int(task.id),
        )
        if not needs_reconcile:
            return None

        reconcile_command_task = getattr(
            self._startup_recovery_use_case,
            "reconcile_command_task",
            None,
        )
        if not callable(reconcile_command_task):
            if from_status != "waiting_command":
                return None
            reconcile_command_task = getattr(
                self._startup_recovery_use_case,
                "reconcile_waiting_command_task",
                None,
            )
            if not callable(reconcile_command_task):
                return None

        try:
            outcome, _terminal_outcome, _observability_task = await reconcile_command_task(
                task=task,
                now=now,
                recovery_source="stale_task_reconcile",
            )
        except Exception:
            logger.warning(
                "Stale task reconcile: command reconcile failed task_id=%s zone_id=%s from_status=%s",
                task.id,
                task.zone_id,
                from_status,
                exc_info=True,
            )
            return None

        if outcome in _PROGRESS_OUTCOMES:
            return "progressed"
        if outcome == "failed":
            return "failed"
        if outcome == "waiting_command":
            if from_status == "waiting_command":
                return "unchanged"
            return "progressed"
        if outcome in {"skipped"}:
            return "unchanged"
        return None

    async def _requeue_stale_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> AutomationTask | None:
        requeue_fn = getattr(self._task_repository, "requeue_unpublished_execution", None)
        if not callable(requeue_fn):
            return None
        task_owner = str(task.claimed_by or "").strip()
        if not task_owner:
            return None
        return await requeue_fn(
            task_id=int(task.id),
            owner=task_owner,
            now=now,
        )

    async def _task_has_ae_commands(self, *, task_id: int) -> bool:
        has_commands = getattr(self._task_repository, "task_has_ae_commands", None)
        if not callable(has_commands):
            return True
        return bool(await has_commands(task_id=task_id))

    async def _task_has_unconfirmed_commands(self, *, task_id: int) -> bool:
        has_unconfirmed = getattr(self._task_repository, "task_has_unconfirmed_ae_commands", None)
        if not callable(has_unconfirmed):
            return False
        return bool(await has_unconfirmed(task_id=task_id))

    async def _release_lease_after_action(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        task_owner = str(task.claimed_by or "").strip()
        if not task_owner:
            return
        release_if_owner_or_expired = getattr(
            self._lease_repository,
            "release_if_owner_or_expired",
            None,
        )
        if not callable(release_if_owner_or_expired):
            return
        try:
            await release_if_owner_or_expired(
                zone_id=int(task.zone_id),
                owner=task_owner,
                now=now,
            )
        except Exception:
            logger.warning(
                "Stale task reconcile: failed to release lease zone_id=%s owner=%s task_id=%s",
                task.zone_id,
                task_owner,
                task.id,
                exc_info=True,
            )

    async def _record_task_reclaimed_event(
        self,
        *,
        zone_id: int,
        task_id: int,
        from_status: str,
        action: str,
        age_sec: float,
    ) -> None:
        payload = {
            "task_id": task_id,
            "from_status": from_status,
            "action": action,
            "age_sec": round(float(age_sec), 3),
            "recovery_source": "stale_task_reconcile",
        }
        try:
            await create_zone_event(zone_id, _STALE_TASK_RECLAIMED_EVENT, payload)
        except Exception:
            inc_observability_write_failed(kind="zone_event")
            logger.warning(
                "Stale task reconcile: failed to write zone_event zone_id=%s task_id=%s action=%s",
                zone_id,
                task_id,
                action,
                exc_info=True,
            )

    @staticmethod
    def _stale_before(now: datetime, ttl_sec: int) -> datetime:
        normalized = (
            now.astimezone(_tz.utc).replace(tzinfo=None)
            if now.tzinfo is not None
            else now.replace(microsecond=0)
        )
        return normalized - timedelta(seconds=max(1, int(ttl_sec)))

    @staticmethod
    def _task_age_sec(*, task: AutomationTask, now: datetime) -> float:
        normalized_now = (
            now.astimezone(_tz.utc).replace(tzinfo=None)
            if now.tzinfo is not None
            else now.replace(microsecond=0)
        )
        if str(task.status or "").strip().lower() == "claimed" and task.claimed_at is not None:
            anchor = task.claimed_at
        else:
            anchor = task.updated_at
        if anchor is None:
            return 0.0
        anchor_naive = (
            anchor.astimezone(_tz.utc).replace(tzinfo=None)
            if getattr(anchor, "tzinfo", None) is not None
            else anchor
        )
        return max(0.0, (normalized_now - anchor_naive).total_seconds())
