"""StartupRecoveryUseCase failure: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    ForeignLeaseContext,
    resolve_foreign_active_lease,
)
from ae3lite.application.services.startup_recovery_shared import logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import StartupRecoveryError


@dataclass(frozen=True)
class StartupRecoveryFailurePorts:
    alert_repository: Callable[[], Any]
    command_gateway: Callable[[], Any]
    foreign_lease_skip_escalate_sec: Callable[[], Any]
    lease_repository: Callable[[], Any]
    sync_workflow_failure_state: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    worker_owner: Callable[[], Any]
    workflow_repository: Callable[[], Any]


class StartupRecoveryFailure:
    def __init__(self, ports: StartupRecoveryFailurePorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

    async def fail_task(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> AutomationTask:
        await self.maybe_fail_safe_shutdown_before_fail(task=task, now=now)
        if self._ports.workflow_repository() is not None:
            await self._ports.sync_workflow_failure_state(task=task, now=now)
        failed_task = await self._ports.task_repository().fail_for_recovery(
            task_id=task.id,
            error_code=error_code,
            error_message=error_message,
            now=now,
            owner=str(task.claimed_by or ""),
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if failed_task is None:
            logger.error(
                "Startup recovery: fail_for_recovery returned None task_id=%s zone_id=%s error_code=%s",
                task.id,
                task.zone_id,
                error_code,
            )
            raise StartupRecoveryError(
                f"Не удалось перевести task_id={task.id} в failed во время startup recovery с error_code={error_code}"
            )
        await self.emit_failed_task_alert(
            task=failed_task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            recovery_source=recovery_source,
        )
        await self.release_lease_after_recovery_fail(task=task, now=now)
        return failed_task

    async def finalize_recovery_failure(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> None:
        """Синхронизирует workflow/alert/lease для уже переведённой в failed задачи."""
        await self.maybe_fail_safe_shutdown_before_fail(task=task, now=now)
        if self._ports.workflow_repository() is not None:
            await self._ports.sync_workflow_failure_state(task=task, now=now)
        await self.emit_failed_task_alert(
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            recovery_source=recovery_source,
        )
        await self.release_lease_after_recovery_fail(task=task, now=now)

    async def maybe_fail_safe_shutdown_before_fail(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        from ae3lite.application.handlers.flow_path_guard import (
            should_fail_safe_shutdown_on_task_fail,
        )
        from ae3lite.application.services.correction_interrupt_safety import (
            attempt_task_fail_safe_shutdown,
        )

        if not should_fail_safe_shutdown_on_task_fail(task):
            return
        try:
            result = await attempt_task_fail_safe_shutdown(
                task=task,
                now=now,
                command_gateway=self._ports.command_gateway(),
                planner_step_prefix="startup_recovery_fail_safe",
            )
        except Exception:
            logger.warning(
                "Startup recovery: fail-safe shutdown exception task_id=%s zone_id=%s",
                task.id,
                task.zone_id,
                exc_info=True,
            )
            return
        if result.attempted and not result.success:
            logger.warning(
                "Startup recovery: fail-safe shutdown non-success task_id=%s reason=%s",
                task.id,
                result.reason,
            )

    async def release_lease_after_recovery_success(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        await self.release_lease_after_recovery_fail(task=task, now=now)

    async def release_lease_after_recovery_fail(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        owner = str(task.claimed_by or "").strip()
        if not owner:
            return
        try:
            release_if_owner_or_expired = getattr(
                self._ports.lease_repository(),
                "release_if_owner_or_expired",
                None,
            )
            if callable(release_if_owner_or_expired):
                released = await release_if_owner_or_expired(
                    zone_id=int(task.zone_id),
                    owner=owner,
                    now=now,
                    claim_generation=int(getattr(task, "claim_generation", 0) or 0),
                )
            else:
                release = getattr(self._ports.lease_repository(), "release", None)
                if not callable(release):
                    return
                released = await release(
                    zone_id=int(task.zone_id),
                    owner=owner,
                    claim_generation=int(getattr(task, "claim_generation", 0) or 0),
                )
            if not released:
                logger.debug(
                    "Startup recovery: lease not released zone_id=%s owner=%s task_id=%s",
                    task.zone_id,
                    owner,
                    task.id,
                )
        except Exception:
            logger.warning(
                "Startup recovery: failed to release lease zone_id=%s owner=%s task_id=%s",
                task.zone_id,
                owner,
                task.id,
                exc_info=True,
            )

    async def emit_failed_task_alert(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> None:
        await emit_task_failed_alert(
            alert_repository=self._ports.alert_repository(),
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            extra_details={"recovery_source": recovery_source},
        )

    async def resolve_foreign_owned_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[ForeignLeaseAction, ForeignLeaseContext | None]:
        worker_owner = self._ports.worker_owner()
        if not worker_owner:
            return ForeignLeaseAction.ALLOW, None

        task_owner = str(task.claimed_by or "").strip()
        if not task_owner or task_owner == worker_owner:
            return ForeignLeaseAction.ALLOW, None

        return await resolve_foreign_active_lease(
            lease_repository=self._ports.lease_repository(),
            zone_id=int(task.zone_id),
            worker_owner=worker_owner,
            task=task,
            now=now,
            escalate_sec=self._ports.foreign_lease_skip_escalate_sec(),
        )
