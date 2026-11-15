"""StartupRecoveryUseCase scan: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.application.services.correction_interrupt_safety import (
    CorrectionInterruptPendingCheck,
)
from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    escalate_foreign_lease_stale_task,
    record_foreign_lease_skip,
)
from ae3lite.application.services.startup_recovery_shared import logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.domain.errors import StartupRecoveryError
from ae3lite.infrastructure.advisory_locks import (
    AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY,
)
from ae3lite.infrastructure.metrics import (
    STARTUP_RECOVERY_RUN,
    STARTUP_RECOVERY_SKIPPED,
    STARTUP_RECOVERY_TASK,
)


@dataclass(frozen=True)
class StartupRecoveryScanPorts:
    alert_repository: Callable[[], Any]
    lease_repository: Callable[[], Any]
    reconcile_pending_vs_terminal_idle_workflow: Callable[..., Awaitable[Any]]
    reconcile_terminal_task_commands: Callable[..., Awaitable[Any]]
    record_startup_recovery_outcome: Callable[..., Awaitable[Any]]
    recover_task: Callable[..., Awaitable[Any]]
    resolve_foreign_owned_task: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    use_startup_recovery_lock: Callable[[], Any]
    worker_owner: Callable[[], Any]
    global_load_open_pending_correction_interrupt_checks: Callable[..., Any]
    global_try_session_advisory_lock: Callable[..., Any]


class StartupRecoveryScan:
    def __init__(self, ports: StartupRecoveryScanPorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

    async def run(self, *, now: datetime) -> StartupRecoveryResult:
        STARTUP_RECOVERY_RUN.inc()
        # release_expired выполняется каждой репликой без advisory lock (R7):
        # просроченные lease не должны блокироваться, пока leader держит recovery lock.
        released_expired_leases = await self._ports.lease_repository().release_expired(now=now)
        if not self._ports.use_startup_recovery_lock():
            return await self.run_scan_and_heal(
                now=now,
                released_expired_leases=released_expired_leases,
            )
        async with self._ports.global_try_session_advisory_lock(AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY) as acquired:
            if acquired:
                return await self.run_scan_and_heal(
                    now=now,
                    released_expired_leases=released_expired_leases,
                )

        STARTUP_RECOVERY_SKIPPED.labels(reason="lock_not_acquired").inc()
        logger.info(
            "Startup recovery: пропуск scan/heal — advisory lock удерживается другим экземпляром AE "
            "(release_expired уже выполнен)",
        )
        # Fetch после выхода из advisory-lock context: соединение пула уже
        # отпущено. Иначе pytest pool max_size=1 deadlocks на acquire.
        restored: list[CorrectionInterruptPendingCheck] = []
        try:
            restored = list(await self._ports.global_load_open_pending_correction_interrupt_checks(now=now))
        except Exception:
            logger.warning(
                "Startup recovery: не удалось загрузить persisted correction-interrupt checks (lock skipped)",
                exc_info=True,
            )
        return StartupRecoveryResult(
            released_expired_leases=released_expired_leases,
            scanned_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            waiting_command_tasks=0,
            recovered_waiting_command_tasks=0,
            skipped_due_to_lock=True,
            pending_correction_safety_checks=tuple(restored),
        )

    async def run_scan_and_heal(
        self,
        *,
        now: datetime,
        released_expired_leases: int,
    ) -> StartupRecoveryResult:
        list_for_recovery = self._ports.task_repository().list_for_startup_recovery
        if self._ports.worker_owner():
            tasks = await list_for_recovery(worker_owner=self._ports.worker_owner(), now=now)
        else:
            tasks = await list_for_recovery()

        completed_tasks = 0
        failed_tasks = 0
        waiting_command_tasks = 0
        recovered_waiting_command_tasks = 0
        terminal_outcomes: list[StartupRecoveryTerminalOutcome] = []
        self._state.pending_correction_safety_checks = []

        for task in tasks:
            foreign_action, foreign_ctx = await self._ports.resolve_foreign_owned_task(
                task=task,
                now=now,
            )
            if foreign_action == ForeignLeaseAction.SKIP:
                STARTUP_RECOVERY_SKIPPED.labels(reason="foreign_lease_task").inc()
                record_foreign_lease_skip(recovery_source="startup_recovery")
                logger.info(
                    "Startup recovery: skip foreign-lease task task_id=%s zone_id=%s claimed_by=%s worker=%s",
                    task.id,
                    task.zone_id,
                    task.claimed_by,
                    self._ports.worker_owner(),
                )
                continue
            if foreign_action == ForeignLeaseAction.ESCALATE:
                failed = await escalate_foreign_lease_stale_task(
                    task_repository=self._ports.task_repository(),
                    alert_repository=self._ports.alert_repository(),
                    task=task,
                    now=now,
                    recovery_source="startup_recovery",
                    lease_context=foreign_ctx,
                )
                if failed is not None:
                    failed_tasks += 1
                    STARTUP_RECOVERY_TASK.labels(outcome="failed").inc()
                    await self._ports.record_startup_recovery_outcome(
                        zone_id=int(failed.zone_id),
                        task_id=int(failed.id),
                        topology=str(failed.topology or ""),
                        stage=str(failed.current_stage or ""),
                        outcome="failed",
                        terminal_outcome=None,
                        recovery_source="startup_recovery",
                    )
                continue

            outcome, terminal_outcome, observability_task = await self._ports.recover_task(task=task, now=now)
            STARTUP_RECOVERY_TASK.labels(outcome=outcome).inc()
            if outcome == "completed":
                completed_tasks += 1
            elif outcome == "failed":
                failed_tasks += 1
            elif outcome == "waiting_command":
                waiting_command_tasks += 1
            elif outcome == "recovered_waiting_command":
                waiting_command_tasks += 1
                recovered_waiting_command_tasks += 1
            else:
                logger.error(
                    "Startup recovery: неподдерживаемый outcome=%s task_id=%s zone_id=%s",
                    outcome,
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                )
                raise StartupRecoveryError(f"Неподдерживаемый результат startup recovery={outcome}")
            if terminal_outcome is not None:
                terminal_outcomes.append(terminal_outcome)
            report_task = observability_task or task
            await self._ports.record_startup_recovery_outcome(
                zone_id=int(report_task.zone_id),
                task_id=int(report_task.id),
                topology=str(report_task.topology or ""),
                stage=str(report_task.current_stage or ""),
                outcome=outcome,
                terminal_outcome=terminal_outcome,
                recovery_source="startup_recovery",
            )

        rec_failed, rec_outcomes = await self._ports.reconcile_pending_vs_terminal_idle_workflow(now=now)
        failed_tasks += rec_failed
        terminal_outcomes.extend(rec_outcomes)

        reconciled_terminal_commands, unresolved_terminal_commands = await self._ports.reconcile_terminal_task_commands(
            now=now
        )

        await self.merge_persisted_pending_correction_checks(now=now)

        return StartupRecoveryResult(
            released_expired_leases=released_expired_leases,
            scanned_tasks=len(tasks),
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            waiting_command_tasks=waiting_command_tasks,
            recovered_waiting_command_tasks=recovered_waiting_command_tasks,
            pending_correction_safety_checks=tuple(self._state.pending_correction_safety_checks),
            terminal_outcomes=tuple(terminal_outcomes),
            reconciled_terminal_commands=reconciled_terminal_commands,
            unresolved_terminal_commands=unresolved_terminal_commands,
        )

    async def merge_persisted_pending_correction_checks(self, *, now: datetime) -> None:
        """Подмешивает незакрытые PENDING_VERIFY из zone_events (после рестарта AE)."""
        try:
            persisted = await self._ports.global_load_open_pending_correction_interrupt_checks(now=now)
        except Exception:
            logger.warning(
                "Startup recovery: не удалось загрузить persisted correction-interrupt checks",
                exc_info=True,
            )
            return
        if not persisted:
            return
        known = {int(check.task_id) for check in self._state.pending_correction_safety_checks}
        added = 0
        for check in persisted:
            if int(check.task_id) in known:
                continue
            self._state.pending_correction_safety_checks.append(check)
            known.add(int(check.task_id))
            added += 1
        if added:
            logger.info(
                "Startup recovery: restored %s persisted correction-interrupt safety checks",
                added,
            )
