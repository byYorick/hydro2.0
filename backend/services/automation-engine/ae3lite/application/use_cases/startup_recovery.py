"""Безопасно восстанавливает in-flight задачи AE3-Lite v2 после рестарта runtime."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as _tz
from typing import Any, Mapping, Optional

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    ForeignLeaseContext,
    escalate_foreign_lease_stale_task,
    record_foreign_lease_skip,
    resolve_foreign_active_lease,
)
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import StartupRecoveryError, TaskExecutionError
from ae3lite.infrastructure.advisory_locks import (
    AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY,
    try_session_advisory_lock,
)
from ae3lite.infrastructure.metrics import (
    STARTUP_RECOVERY_RUN,
    STARTUP_RECOVERY_SKIPPED,
    STARTUP_RECOVERY_TASK,
)
from ae3lite.application.services.correction_interrupt_safety import (
    DEFAULT_VERIFY_GRACE_SEC,
    CorrectionInterruptPendingCheck,
    build_pending_check_from_task,
    emit_correction_interrupt_pending_verify,
    is_dose_correction_step,
    load_open_pending_correction_interrupt_checks,
)
from common.db import create_zone_event
from common.service_logs import send_service_log


from ae3lite.application.services.task_workflow_transition import TaskWorkflowTransition


from ae3lite.application.services.startup_recovery_shared import logger, _STARTUP_RECOVERY_OUTCOME_EVENT
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.application.services.startup_recovery_scan import StartupRecoveryScan, StartupRecoveryScanPorts
from ae3lite.application.services.startup_recovery_terminal_repair import (
    StartupRecoveryTerminalRepair,
    StartupRecoveryTerminalRepairPorts,
)
from ae3lite.application.services.startup_recovery_command_recovery import (
    StartupRecoveryCommandRecovery,
    StartupRecoveryCommandRecoveryPorts,
)
from ae3lite.application.services.startup_recovery_stage_transition import (
    StartupRecoveryStageTransition,
    StartupRecoveryStageTransitionPorts,
)
from ae3lite.application.services.startup_recovery_failure import StartupRecoveryFailure, StartupRecoveryFailurePorts
from ae3lite.application.services.startup_recovery_reporting import (
    StartupRecoveryReporting,
    StartupRecoveryReportingPorts,
)


class StartupRecoveryUseCase:
    """Reconcilе'ит сохранённые in-flight tasks без новой публикации команды.

    В v2 использует topology registry для маршрутизации done-transition вместо payload keys.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        lease_repository: Any,
        command_gateway: Any,
        workflow_repository: Any | None = None,
        topology_registry: Optional[TopologyRegistry] = None,
        alert_repository: Any | None = None,
        use_startup_recovery_lock: bool = True,
        worker_owner: str | None = None,
        foreign_lease_skip_escalate_sec: int = 300,
        correction_interrupt_verify_grace_sec: int = DEFAULT_VERIFY_GRACE_SEC,
        command_repository: Any | None = None,
        pid_state_repository: Any | None = None,
        terminal_command_reconcile_limit: int = 100,
    ) -> None:
        self._startup_recovery_state = StartupRecoveryState()
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._command_gateway = command_gateway
        self._workflow_repository = workflow_repository
        self._transitions = TaskWorkflowTransition(
            task_repository=task_repository, workflow_repository=workflow_repository
        )
        self._registry = topology_registry or TopologyRegistry()
        self._alert_repository = alert_repository
        self._use_startup_recovery_lock = bool(use_startup_recovery_lock)
        self._worker_owner = str(worker_owner or "").strip() or None
        self._foreign_lease_skip_escalate_sec = max(1, int(foreign_lease_skip_escalate_sec))
        self._correction_interrupt_verify_grace_sec = max(
            15,
            int(correction_interrupt_verify_grace_sec or DEFAULT_VERIFY_GRACE_SEC),
        )
        self._command_repository = command_repository
        self._pid_state_repository = pid_state_repository
        self._terminal_command_reconcile_limit = max(
            1,
            min(1000, int(terminal_command_reconcile_limit)),
        )
        self._pending_correction_safety_checks: list[CorrectionInterruptPendingCheck] = []
        self._startup_recovery_scan = StartupRecoveryScan(
            StartupRecoveryScanPorts(
                alert_repository=lambda: self._alert_repository,
                lease_repository=lambda: self._lease_repository,
                reconcile_pending_vs_terminal_idle_workflow=lambda *args, **kwargs: (
                    self._reconcile_pending_vs_terminal_idle_workflow(*args, **kwargs)
                ),
                reconcile_terminal_task_commands=lambda *args, **kwargs: self._reconcile_terminal_task_commands(
                    *args, **kwargs
                ),
                record_startup_recovery_outcome=lambda *args, **kwargs: self._record_startup_recovery_outcome(
                    *args, **kwargs
                ),
                recover_task=lambda *args, **kwargs: self._recover_task(*args, **kwargs),
                resolve_foreign_owned_task=lambda *args, **kwargs: self._resolve_foreign_owned_task(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                use_startup_recovery_lock=lambda: self._use_startup_recovery_lock,
                worker_owner=lambda: self._worker_owner,
                global_load_open_pending_correction_interrupt_checks=lambda *args, **kwargs: (
                    load_open_pending_correction_interrupt_checks(*args, **kwargs)
                ),
                global_try_session_advisory_lock=lambda *args, **kwargs: try_session_advisory_lock(*args, **kwargs),
            ),
            self._startup_recovery_state,
        )
        self._startup_recovery_terminal_repair = StartupRecoveryTerminalRepair(
            StartupRecoveryTerminalRepairPorts(
                alert_repository=lambda: self._alert_repository,
                command_gateway=lambda: self._command_gateway,
                command_repository=lambda: self._command_repository,
                pid_state_repository=lambda: self._pid_state_repository,
                task_repository=lambda: self._task_repository,
                terminal_command_reconcile_limit=lambda: self._terminal_command_reconcile_limit,
                use_startup_recovery_lock=lambda: self._use_startup_recovery_lock,
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_try_session_advisory_lock=lambda *args, **kwargs: try_session_advisory_lock(*args, **kwargs),
            ),
            self._startup_recovery_state,
        )
        self._startup_recovery_command_recovery = StartupRecoveryCommandRecovery(
            StartupRecoveryCommandRecoveryPorts(
                apply_topology_done_transition=lambda *args, **kwargs: self._apply_topology_done_transition(
                    *args, **kwargs
                ),
                build_terminal_outcome=lambda *args, **kwargs: self._build_terminal_outcome(*args, **kwargs),
                command_gateway=lambda: self._command_gateway,
                correction_interrupt_verify_grace_sec=lambda: self._correction_interrupt_verify_grace_sec,
                emit_failed_task_alert=lambda *args, **kwargs: self._emit_failed_task_alert(*args, **kwargs),
                fail_task=lambda *args, **kwargs: self._fail_task(*args, **kwargs),
                finalize_recovery_failure=lambda *args, **kwargs: self._finalize_recovery_failure(*args, **kwargs),
                record_startup_recovery_outcome=lambda *args, **kwargs: self._record_startup_recovery_outcome(
                    *args, **kwargs
                ),
                registry=lambda: self._registry,
                release_lease_after_recovery_fail=lambda *args, **kwargs: self._release_lease_after_recovery_fail(
                    *args, **kwargs
                ),
                task_repository=lambda: self._task_repository,
                global_emit_correction_interrupt_pending_verify=lambda *args, **kwargs: (
                    emit_correction_interrupt_pending_verify(*args, **kwargs)
                ),
            ),
            self._startup_recovery_state,
        )
        self._startup_recovery_stage_transition = StartupRecoveryStageTransition(
            StartupRecoveryStageTransitionPorts(
                command_gateway=lambda: self._command_gateway,
                emit_failed_task_alert=lambda *args, **kwargs: self._emit_failed_task_alert(*args, **kwargs),
                fail_task=lambda *args, **kwargs: self._fail_task(*args, **kwargs),
                registry=lambda: self._registry,
                release_lease_after_recovery_fail=lambda *args, **kwargs: self._release_lease_after_recovery_fail(
                    *args, **kwargs
                ),
                release_lease_after_recovery_success=lambda *args, **kwargs: self._release_lease_after_recovery_success(
                    *args, **kwargs
                ),
                sync_workflow_failure_state=lambda *args, **kwargs: self._sync_workflow_failure_state(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                transitions=lambda: self._transitions,
                workflow_repository=lambda: self._workflow_repository,
            ),
            self._startup_recovery_state,
        )
        self._startup_recovery_failure = StartupRecoveryFailure(
            StartupRecoveryFailurePorts(
                alert_repository=lambda: self._alert_repository,
                command_gateway=lambda: self._command_gateway,
                foreign_lease_skip_escalate_sec=lambda: self._foreign_lease_skip_escalate_sec,
                lease_repository=lambda: self._lease_repository,
                sync_workflow_failure_state=lambda *args, **kwargs: self._sync_workflow_failure_state(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                worker_owner=lambda: self._worker_owner,
                workflow_repository=lambda: self._workflow_repository,
            ),
            self._startup_recovery_state,
        )
        self._startup_recovery_reporting = StartupRecoveryReporting(
            StartupRecoveryReportingPorts(
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
            ),
            self._startup_recovery_state,
        )

    async def run(self, *, now: datetime) -> StartupRecoveryResult:
        return await self._startup_recovery_scan.run(now=now)

    async def _run_scan_and_heal(
        self,
        *,
        now: datetime,
        released_expired_leases: int,
    ) -> StartupRecoveryResult:
        return await self._startup_recovery_scan.run_scan_and_heal(
            now=now, released_expired_leases=released_expired_leases
        )

    async def reconcile_terminal_commands(self, *, now: datetime) -> tuple[int, int]:
        return await self._startup_recovery_terminal_repair.reconcile_terminal_commands(now=now)

    async def _reconcile_terminal_task_commands(self, *, now: datetime) -> tuple[int, int]:
        return await self._startup_recovery_terminal_repair.reconcile_terminal_task_commands(now=now)

    _terminal_dose_pid_type = staticmethod(StartupRecoveryTerminalRepair.terminal_dose_pid_type)

    async def _reconcile_terminal_dose_pid_state(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        result: Mapping[str, Any],
        now: datetime,
    ) -> None:
        return await self._startup_recovery_terminal_repair.reconcile_terminal_dose_pid_state(
            task=task, ae_command=ae_command, result=result, now=now
        )

    async def _mark_terminal_dose_accounted(
        self,
        *,
        ae_command: Mapping[str, Any],
        now: datetime,
    ) -> None:
        return await self._startup_recovery_terminal_repair.mark_terminal_dose_accounted(ae_command=ae_command, now=now)

    async def _record_terminal_command_reconciled_event(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        return await self._startup_recovery_terminal_repair.record_terminal_command_reconciled_event(
            task=task, ae_command=ae_command, result=result
        )

    async def _emit_terminal_command_alert(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        state: str,
        result: Mapping[str, Any] | None,
        now: datetime,
    ) -> None:
        return await self._startup_recovery_terminal_repair.emit_terminal_command_alert(
            task=task, ae_command=ae_command, state=state, result=result, now=now
        )

    async def _merge_persisted_pending_correction_checks(self, *, now: datetime) -> None:
        return await self._startup_recovery_scan.merge_persisted_pending_correction_checks(now=now)

    async def reconcile_waiting_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "waiting_command_reconcile",
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._startup_recovery_command_recovery.reconcile_waiting_command_task(
            task=task, now=now, recovery_source=recovery_source
        )

    async def reconcile_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "stale_task_reconcile",
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._startup_recovery_command_recovery.reconcile_command_task(
            task=task, now=now, recovery_source=recovery_source
        )

    async def _reconcile_pending_vs_terminal_idle_workflow(
        self,
        *,
        now: datetime,
    ) -> tuple[int, list[StartupRecoveryTerminalOutcome]]:
        return await self._startup_recovery_command_recovery.reconcile_pending_vs_terminal_idle_workflow(now=now)

    async def _recover_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._startup_recovery_command_recovery.recover_task(task=task, now=now)

    async def _recover_native_two_tank_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._startup_recovery_command_recovery.recover_native_two_tank_task(task=task, now=now)

    async def _reconcile_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        # Коррекцию mid-dose не resume'им (fail-closed), но critical по железу
        # откладываем: после power-loss узлы часто ещё offline, актуаторы уже OFF.
        return await self._startup_recovery_command_recovery.reconcile_command_task(
            task=task, now=now, recovery_source=recovery_source
        )

    async def _handle_recovery_gateway_result(
        self,
        *,
        task: AutomationTask,
        result: Mapping[str, Any],
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._startup_recovery_command_recovery.handle_recovery_gateway_result(
            task=task, result=result, now=now, recovery_source=recovery_source
        )

    async def _persist_waiting_command_status(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> AutomationTask | None:
        return await self._startup_recovery_command_recovery.persist_waiting_command_status(task=task, now=now)

    async def _apply_topology_done_transition(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> AutomationTask:
        return await self._startup_recovery_stage_transition.apply_topology_done_transition(
            task=task, now=now, recovery_source=recovery_source
        )

    async def _requeue_recovered_command_stage(
        self,
        *,
        task: AutomationTask,
        stage_def: Any,
        now: datetime,
    ) -> AutomationTask:
        return await self._startup_recovery_stage_transition.requeue_recovered_command_stage(
            task=task, stage_def=stage_def, now=now
        )

    async def _task_repo_update_stage(
        self,
        *,
        task: AutomationTask,
        workflow: WorkflowState,
        now: datetime,
    ) -> Any:
        return await self._startup_recovery_stage_transition.task_repo_update_stage(
            task=task, workflow=workflow, now=now
        )

    async def _fail_task(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> AutomationTask:
        return await self._startup_recovery_failure.fail_task(
            task=task, error_code=error_code, error_message=error_message, now=now, recovery_source=recovery_source
        )

    async def _finalize_recovery_failure(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> None:
        return await self._startup_recovery_failure.finalize_recovery_failure(
            task=task, error_code=error_code, error_message=error_message, now=now, recovery_source=recovery_source
        )

    async def _maybe_fail_safe_shutdown_before_fail(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        return await self._startup_recovery_failure.maybe_fail_safe_shutdown_before_fail(task=task, now=now)

    async def _release_lease_after_recovery_success(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        return await self._startup_recovery_failure.release_lease_after_recovery_success(task=task, now=now)

    async def _release_lease_after_recovery_fail(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> None:
        return await self._startup_recovery_failure.release_lease_after_recovery_fail(task=task, now=now)

    async def _record_startup_recovery_outcome(
        self,
        *,
        zone_id: int,
        task_id: int,
        topology: str,
        stage: str,
        outcome: str,
        terminal_outcome: StartupRecoveryTerminalOutcome | None,
        recovery_source: str = "startup_recovery",
    ) -> None:
        return await self._startup_recovery_reporting.record_startup_recovery_outcome(
            zone_id=zone_id,
            task_id=task_id,
            topology=topology,
            stage=stage,
            outcome=outcome,
            terminal_outcome=terminal_outcome,
            recovery_source=recovery_source,
        )

    async def _emit_failed_task_alert(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> None:
        return await self._startup_recovery_failure.emit_failed_task_alert(
            task=task, error_code=error_code, error_message=error_message, now=now, recovery_source=recovery_source
        )

    async def _sync_workflow_failure_state(self, *, task: AutomationTask, now: datetime) -> None:
        return await self._startup_recovery_stage_transition.sync_workflow_failure_state(task=task, now=now)

    async def _safe_upsert_workflow_phase(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: dict[str, Any],
        scheduler_task_id: str,
        now: datetime,
    ) -> None:
        return await self._startup_recovery_stage_transition.safe_upsert_workflow_phase(
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def _resolve_foreign_owned_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[ForeignLeaseAction, ForeignLeaseContext | None]:
        return await self._startup_recovery_failure.resolve_foreign_owned_task(task=task, now=now)

    def _build_terminal_outcome(self, *, task: AutomationTask) -> StartupRecoveryTerminalOutcome | None:
        return self._startup_recovery_reporting.build_terminal_outcome(task=task)

    @property
    def _pending_correction_safety_checks(self):
        return self._startup_recovery_state.pending_correction_safety_checks

    @_pending_correction_safety_checks.setter
    def _pending_correction_safety_checks(self, value):
        self._startup_recovery_state.pending_correction_safety_checks = value
