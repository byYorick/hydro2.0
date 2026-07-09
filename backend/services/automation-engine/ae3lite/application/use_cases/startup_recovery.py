"""Безопасно восстанавливает in-flight задачи AE3-Lite v2 после рестарта runtime."""

from __future__ import annotations

import logging
from datetime import datetime, timezone as _tz
from typing import Any, Mapping, Optional

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
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
from ae3lite.application.handlers.flow_path_guard import emit_correction_interrupted_hardware_risk
from common.db import create_zone_event
from common.service_logs import send_service_log

logger = logging.getLogger(__name__)

_STARTUP_RECOVERY_OUTCOME_EVENT = "AE_STARTUP_RECOVERY_OUTCOME"


class StartupRecoveryUseCase:
    """Reconcilе'ит сохранённые in-flight задачи без новой публикации команды.

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
    ) -> None:
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._command_gateway = command_gateway
        self._workflow_repository = workflow_repository
        self._registry = topology_registry or TopologyRegistry()
        self._alert_repository = alert_repository
        self._use_startup_recovery_lock = bool(use_startup_recovery_lock)
        self._worker_owner = str(worker_owner or "").strip() or None

    async def run(self, *, now: datetime) -> StartupRecoveryResult:
        STARTUP_RECOVERY_RUN.inc()
        # release_expired выполняется каждой репликой без advisory lock (R7):
        # просроченные lease не должны блокироваться, пока leader держит recovery lock.
        released_expired_leases = await self._lease_repository.release_expired(now=now)
        if not self._use_startup_recovery_lock:
            return await self._run_scan_and_heal(
                now=now,
                released_expired_leases=released_expired_leases,
            )
        async with try_session_advisory_lock(AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY) as acquired:
            if not acquired:
                STARTUP_RECOVERY_SKIPPED.labels(reason="lock_not_acquired").inc()
                logger.info(
                    "Startup recovery: пропуск scan/heal — advisory lock удерживается другим экземпляром AE "
                    "(release_expired уже выполнен)",
                )
                return StartupRecoveryResult(
                    released_expired_leases=released_expired_leases,
                    scanned_tasks=0,
                    completed_tasks=0,
                    failed_tasks=0,
                    waiting_command_tasks=0,
                    recovered_waiting_command_tasks=0,
                    skipped_due_to_lock=True,
                )
            return await self._run_scan_and_heal(
                now=now,
                released_expired_leases=released_expired_leases,
            )

    async def _run_scan_and_heal(
        self,
        *,
        now: datetime,
        released_expired_leases: int,
    ) -> StartupRecoveryResult:
        list_for_recovery = self._task_repository.list_for_startup_recovery
        if self._worker_owner:
            tasks = await list_for_recovery(worker_owner=self._worker_owner, now=now)
        else:
            tasks = await list_for_recovery()

        completed_tasks = 0
        failed_tasks = 0
        waiting_command_tasks = 0
        recovered_waiting_command_tasks = 0
        terminal_outcomes: list[StartupRecoveryTerminalOutcome] = []

        for task in tasks:
            if await self._should_skip_foreign_owned_task(task=task, now=now):
                STARTUP_RECOVERY_SKIPPED.labels(reason="foreign_lease_task").inc()
                logger.info(
                    "Startup recovery: skip foreign-lease task task_id=%s zone_id=%s claimed_by=%s worker=%s",
                    task.id,
                    task.zone_id,
                    task.claimed_by,
                    self._worker_owner,
                )
                continue

            outcome, terminal_outcome, observability_task = await self._recover_task(task=task, now=now)
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
            await self._record_startup_recovery_outcome(
                zone_id=int(report_task.zone_id),
                task_id=int(report_task.id),
                topology=str(report_task.topology or ""),
                stage=str(report_task.current_stage or ""),
                outcome=outcome,
                terminal_outcome=terminal_outcome,
                recovery_source="startup_recovery",
            )

        rec_failed, rec_outcomes = await self._reconcile_pending_vs_terminal_idle_workflow(now=now)
        failed_tasks += rec_failed
        terminal_outcomes.extend(rec_outcomes)

        return StartupRecoveryResult(
            released_expired_leases=released_expired_leases,
            scanned_tasks=len(tasks),
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            waiting_command_tasks=waiting_command_tasks,
            recovered_waiting_command_tasks=recovered_waiting_command_tasks,
            terminal_outcomes=tuple(terminal_outcomes),
        )

    async def reconcile_waiting_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "waiting_command_reconcile",
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        """Фоновый reconcile одной `waiting_command` задачи без republish."""
        if str(task.status or "").strip().lower() != "waiting_command":
            logger.debug(
                "Waiting command reconcile: skip non-waiting task_id=%s status=%s",
                task.id,
                task.status,
            )
            return "skipped", None, None

        outcome, terminal_outcome, observability_task = await self._reconcile_command_task(
            task=task,
            now=now,
            recovery_source=recovery_source,
        )
        report_task = observability_task or task
        await self._record_startup_recovery_outcome(
            zone_id=int(report_task.zone_id),
            task_id=int(report_task.id),
            topology=str(report_task.topology or ""),
            stage=str(report_task.current_stage or ""),
            outcome=outcome,
            terminal_outcome=terminal_outcome,
            recovery_source=recovery_source,
        )
        return outcome, terminal_outcome, observability_task

    async def reconcile_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "stale_task_reconcile",
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        """Reconcile command state для active задачи (running/claimed/waiting_command)."""
        outcome, terminal_outcome, observability_task = await self._reconcile_command_task(
            task=task,
            now=now,
            recovery_source=recovery_source,
        )
        report_task = observability_task or task
        await self._record_startup_recovery_outcome(
            zone_id=int(report_task.zone_id),
            task_id=int(report_task.id),
            topology=str(report_task.topology or ""),
            stage=str(report_task.current_stage or ""),
            outcome=outcome,
            terminal_outcome=terminal_outcome,
            recovery_source=recovery_source,
        )
        return outcome, terminal_outcome, observability_task

    async def _reconcile_pending_vs_terminal_idle_workflow(
        self,
        *,
        now: datetime,
    ) -> tuple[int, list[StartupRecoveryTerminalOutcome]]:
        """Снимает «осиротевшие» pending-задачи при idle workflow с терминальным *_stop stage в payload."""
        rows = await self._task_repository.fetch_pending_with_idle_zone_workflow_rows()
        failed_count = 0
        outcomes: list[StartupRecoveryTerminalOutcome] = []
        for row in rows:
            row_map = dict(row)
            snap = row_map.pop("snapshot_stage", None)
            snapshot_stage = str(snap).strip() if snap else ""
            if not snapshot_stage:
                continue
            task = AutomationTask.from_row(row_map)
            topo = str(task.topology or "two_tank").strip()
            if not self._registry.has_topology(topo):
                topo = "two_tank"
            try:
                st = self._registry.get(topo, snapshot_stage)
            except KeyError:
                continue
            if st.terminal_error is None:
                continue
            failed = await self._task_repository.fail_pending_or_active_for_recovery(
                task_id=task.id,
                error_code="startup_recovery_pending_vs_terminal_workflow",
                error_message=(
                    f"Отмена pending {task.task_type}: zone_workflow в терминальном stage "
                    f"{snapshot_stage} после остановки цикла"
                ),
                now=now,
            )
            if failed is None:
                logger.warning(
                    "Startup recovery: reconcile fail_pending noop task_id=%s zone_id=%s",
                    task.id,
                    task.zone_id,
                )
                continue
            failed_count += 1
            STARTUP_RECOVERY_TASK.labels(outcome="failed").inc()
            await self._emit_failed_task_alert(
                task=failed,
                error_code="startup_recovery_pending_vs_terminal_workflow",
                error_message=str(failed.error_message or ""),
                now=now,
                recovery_source="startup_recovery",
            )
            await self._release_lease_after_recovery_fail(task=failed, now=now)
            terminal_outcome = self._build_terminal_outcome(task=failed)
            if terminal_outcome is not None:
                outcomes.append(terminal_outcome)
            await self._record_startup_recovery_outcome(
                zone_id=int(failed.zone_id),
                task_id=int(failed.id),
                topology=str(failed.topology or ""),
                stage=str(failed.current_stage or ""),
                outcome="failed",
                terminal_outcome=terminal_outcome,
                recovery_source="startup_recovery",
            )
        return failed_count, outcomes

    async def _recover_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        if not task.claimed_by:
            failed_task = await self._fail_task(
                task=task,
                error_code="startup_recovery_missing_owner",
                error_message=f"У задачи {task.id} отсутствует claimed_by во время startup recovery",
                now=now,
                recovery_source="startup_recovery",
            )
            return "failed", self._build_terminal_outcome(task=failed_task), failed_task

        return await self._recover_native_two_tank_task(task=task, now=now)

    async def _recover_native_two_tank_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self._reconcile_command_task(
            task=task,
            now=now,
            recovery_source="startup_recovery",
        )

    async def _reconcile_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        # Если коррекция прервалась внутри command batch, безопасно продолжать дозирование нельзя
        if task.correction is not None:
            failed_task = await self._fail_task(
                task=task,
                error_code="startup_recovery_correction_interrupted",
                error_message=(
                    f"Коррекция задачи {task.id} была прервана на шаге {task.correction.corr_step}"
                ),
                now=now,
                recovery_source=recovery_source,
            )
            await emit_correction_interrupted_hardware_risk(
                task=failed_task,
                now=now,
                recovery_source=recovery_source,
            )
            return "failed", self._build_terminal_outcome(task=failed_task), failed_task

        try:
            result = await self._command_gateway.recover_waiting_command(task=task, now=now)
        except TaskExecutionError as exc:
            error_code = exc.code
            if task.status in {"claimed", "running"} and exc.code == "ae3_missing_ae_command":
                error_code = "startup_recovery_unconfirmed_command"
            failed_task = await self._fail_task(
                task=task,
                error_code=error_code,
                error_message=str(exc),
                now=now,
                recovery_source=recovery_source,
            )
            return "failed", self._build_terminal_outcome(task=failed_task), failed_task

        return await self._handle_recovery_gateway_result(
            task=task,
            result=result,
            now=now,
            recovery_source=recovery_source,
        )

    async def _handle_recovery_gateway_result(
        self,
        *,
        task: AutomationTask,
        result: Mapping[str, Any],
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        if result["state"] == "waiting_command":
            poll_deadline_exceeded = getattr(
                self._command_gateway,
                "waiting_command_poll_deadline_exceeded",
                None,
            )
            if callable(poll_deadline_exceeded) and await poll_deadline_exceeded(task=task, now=now):
                failed_task = await self._fail_task(
                    task=task,
                    error_code="ae3_command_poll_deadline_exceeded",
                    error_message=(
                        f"Опрос команды превысил дедлайн для задачи {task.id} "
                        f"stage={task.current_stage}"
                    ),
                    now=now,
                    recovery_source=recovery_source,
                )
                return "failed", self._build_terminal_outcome(task=failed_task), failed_task
            if task.status in {"claimed", "running"}:
                await self._persist_waiting_command_status(task=task, now=now)
            return "waiting_command", None, None
        if result["state"] == "failed":
            failed_task = result["task"]
            error_code = str(
                result.get("error_code")
                or getattr(failed_task, "error_code", None)
                or "startup_recovery_command_failed"
            )
            error_message = str(
                result.get("error_message")
                or getattr(failed_task, "error_message", None)
                or f"Команда задачи {task.id} завершилась ошибкой во время startup recovery"
            )
            await self._finalize_recovery_failure(
                task=failed_task,
                error_code=error_code,
                error_message=error_message,
                now=now,
                recovery_source=recovery_source,
            )
            return "failed", self._build_terminal_outcome(task=failed_task), failed_task
        if result["state"] != "done":
            logger.error(
                "Startup recovery: неподдерживаемое native recovery state=%s task_id=%s zone_id=%s",
                result["state"],
                task.id,
                task.zone_id,
            )
            raise StartupRecoveryError(f"Неподдерживаемое состояние native recovery={result['state']}")

        progressed_task = await self._apply_topology_done_transition(
            task=result["task"],
            now=now,
            recovery_source=recovery_source,
        )
        if progressed_task.status == "completed":
            return "completed", self._build_terminal_outcome(task=progressed_task), progressed_task
        if progressed_task.status == "failed":
            return "failed", self._build_terminal_outcome(task=progressed_task), progressed_task
        return "recovered_waiting_command", None, progressed_task

    async def _persist_waiting_command_status(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> AutomationTask | None:
        """Фиксирует `waiting_command` для in-flight задачи после reconcile legacy-команды."""
        if task.status == "waiting_command":
            return task
        recover_waiting_command = getattr(self._task_repository, "recover_waiting_command", None)
        if not callable(recover_waiting_command):
            return None
        owner = str(task.claimed_by or "").strip()
        if not owner:
            return None
        try:
            return await recover_waiting_command(task_id=task.id, now=now, owner=owner)
        except Exception:
            logger.warning(
                "Startup recovery: failed to persist waiting_command task_id=%s zone_id=%s",
                task.id,
                task.zone_id,
                exc_info=True,
            )
            return None

    async def _apply_topology_done_transition(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> AutomationTask:
        """Recovery v2: использует topology registry, чтобы определить следующий stage после command DONE.

        1. Прочитать ``task.current_stage``.
        2. Найти ``StageDef`` в registry.
        3. Если задан ``terminal_error`` -> завершить ошибкой.
        4. Если задан ``next_stage`` -> перейти в следующий stage.
        """
        topology = task.topology
        current_stage = task.current_stage

        try:
            stage_def = self._registry.get(topology, current_stage)
        except KeyError:
            if self._workflow_repository is not None:
                await self._sync_workflow_failure_state(task=task, now=now)
            failed = await self._task_repository.fail_for_recovery(
                task_id=task.id,
                error_code="startup_recovery_unknown_stage",
                error_message=f"Неизвестный stage {current_stage} в topology {topology}",
                now=now,
            )
            if failed is None:
                logger.error(
                    "Startup recovery: fail_for_recovery returned None for unknown stage task_id=%s zone_id=%s stage=%s topology=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    topology,
                )
                raise StartupRecoveryError(
                    f"Не удалось перевести task_id={task.id} в failed для неизвестного stage",
                )
            await self._emit_failed_task_alert(
                task=failed,
                error_code="startup_recovery_unknown_stage",
                error_message=f"Неизвестный stage {current_stage} в topology {topology}",
                now=now,
                recovery_source=recovery_source,
            )
            await self._release_lease_after_recovery_fail(task=failed, now=now)
            return failed

        # Terminal error stage
        if stage_def.terminal_error is not None:
            error_code, error_message = stage_def.terminal_error
            await self._sync_workflow_failure_state(task=task, now=now)
            failed = await self._task_repository.fail_for_recovery(
                task_id=task.id,
                error_code=error_code,
                error_message=error_message,
                now=now,
            )
            if failed is None:
                logger.error(
                    "Startup recovery: fail_for_recovery returned None on terminal_error stage task_id=%s zone_id=%s stage=%s error_code=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    error_code,
                )
                raise StartupRecoveryError(
                    f"Не удалось перевести task_id={task.id} в failed после recovery DONE",
                )
            await self._emit_failed_task_alert(
                task=failed,
                error_code=error_code,
                error_message=error_message,
                now=now,
                recovery_source=recovery_source,
            )
            await self._release_lease_after_recovery_fail(task=failed, now=now)
            return failed

        # Has next_stage — transition
        if stage_def.next_stage is not None:
            next_stage = stage_def.next_stage
            try:
                next_def = self._registry.get(topology, next_stage)
            except KeyError:
                next_def = None

            next_phase = next_def.workflow_phase if next_def else "idle"

            await self._safe_upsert_workflow_phase(
                zone_id=task.zone_id,
                workflow_phase=next_phase,
                payload={"ae3_cycle_start_stage": next_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )

            # Record transition in audit trail
            await self._task_repository.record_transition(
                task_id=task.id,
                from_stage=current_stage,
                to_stage=next_stage,
                workflow_phase=next_phase,
                metadata={"recovery": True},
                now=now,
            )

            new_workflow = WorkflowState(
                current_stage=next_stage,
                workflow_phase=next_phase,
                stage_deadline_at=None,  # Will be computed on next handler run
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=task.workflow.clean_fill_cycle,
            )

            requeued = await self._task_repo_update_stage(
                task=task, workflow=new_workflow, now=now,
            )
            if requeued is None:
                logger.error(
                    "Startup recovery: update_stage returned None on requeue task_id=%s zone_id=%s stage=%s next_stage=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                    next_stage,
                )
                raise StartupRecoveryError(
                    f"Не удалось повторно поставить task_id={task.id} в очередь после recovery DONE",
                )
            return requeued

        # Single-command terminal success (e.g. generic_cycle_start startup):
        # command DONE без next_stage/terminal_error завершает задачу.
        if (
            stage_def.handler == "command"
            and stage_def.next_stage is None
            and stage_def.terminal_error is None
        ):
            await self._safe_upsert_workflow_phase(
                zone_id=task.zone_id,
                workflow_phase=stage_def.workflow_phase,
                payload={"ae3_cycle_start_stage": current_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )
            completed = await self._task_repository.mark_completed(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if completed is None:
                logger.error(
                    "Startup recovery: mark_completed returned None task_id=%s zone_id=%s stage=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                )
                raise StartupRecoveryError(
                    f"Не удалось завершить task_id={task.id} после recovery DONE",
                )
            return completed

        # Poll/handler stages (handler != "command" and != "ready") have no static
        # next_stage — transitions are decided by the handler at runtime. A stale
        # DONE from the previous command batch must not terminal-complete the task.
        if stage_def.handler != "ready":
            await self._safe_upsert_workflow_phase(
                zone_id=task.zone_id,
                workflow_phase=stage_def.workflow_phase,
                payload={"ae3_cycle_start_stage": current_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )
            continued_workflow = WorkflowState(
                current_stage=current_stage,
                workflow_phase=stage_def.workflow_phase,
                stage_deadline_at=task.workflow.stage_deadline_at,
                stage_retry_count=task.workflow.stage_retry_count,
                stage_entered_at=task.workflow.stage_entered_at,
                clean_fill_cycle=task.workflow.clean_fill_cycle,
            )
            requeued = await self._task_repo_update_stage(
                task=task,
                workflow=continued_workflow,
                now=now,
            )
            if requeued is None:
                logger.error(
                    "Startup recovery: update_stage returned None on poll-stage requeue task_id=%s zone_id=%s stage=%s",
                    task.id,
                    task.zone_id,
                    current_stage,
                )
                raise StartupRecoveryError(
                    f"Не удалось повторно поставить task_id={task.id} в очередь после recovery DONE на poll-stage",
                )
            return requeued

        # Terminal success stages (complete_ready, completed_run, completed_skip)
        await self._safe_upsert_workflow_phase(
            zone_id=task.zone_id,
            workflow_phase=stage_def.workflow_phase,
            payload={"ae3_cycle_start_stage": current_stage},
            scheduler_task_id=str(task.id),
            now=now,
        )
        completed = await self._task_repository.mark_completed(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            now=now,
        )
        if completed is None:
            logger.error(
                "Startup recovery: mark_completed returned None task_id=%s zone_id=%s stage=%s",
                task.id,
                task.zone_id,
                current_stage,
            )
            raise StartupRecoveryError(
                f"Не удалось завершить task_id={task.id} после recovery DONE",
            )
        return completed

    async def _task_repo_update_stage(
        self, *, task: AutomationTask, workflow: WorkflowState, now: datetime,
    ) -> Any:
        """Wrapper for update_stage during recovery."""
        return await self._task_repository.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=workflow,
            correction=None,
            due_at=now,
            now=now,
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
        if self._workflow_repository is not None:
            await self._sync_workflow_failure_state(task=task, now=now)
        failed_task = await self._task_repository.fail_for_recovery(
            task_id=task.id,
            error_code=error_code,
            error_message=error_message,
            now=now,
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
        await self._emit_failed_task_alert(
            task=failed_task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            recovery_source=recovery_source,
        )
        await self._release_lease_after_recovery_fail(task=failed_task, now=now)
        return failed_task

    async def _finalize_recovery_failure(
        self,
        *,
        task: AutomationTask,
        error_code: str,
        error_message: str,
        now: datetime,
        recovery_source: str = "startup_recovery",
    ) -> None:
        """Синхронизирует workflow/alert/lease для уже переведённой в failed задачи."""
        if self._workflow_repository is not None:
            await self._sync_workflow_failure_state(task=task, now=now)
        await self._emit_failed_task_alert(
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            recovery_source=recovery_source,
        )
        await self._release_lease_after_recovery_fail(task=task, now=now)

    async def _release_lease_after_recovery_fail(
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
                self._lease_repository,
                "release_if_owner_or_expired",
                None,
            )
            if callable(release_if_owner_or_expired):
                released = await release_if_owner_or_expired(
                    zone_id=int(task.zone_id),
                    owner=owner,
                    now=now,
                )
            else:
                release = getattr(self._lease_repository, "release", None)
                if not callable(release):
                    return
                released = await release(zone_id=int(task.zone_id), owner=owner)
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
        payload: dict[str, Any] = {
            "task_id": task_id,
            "outcome": outcome,
            "topology": topology,
            "stage": stage,
            "recovery_source": recovery_source,
        }
        if terminal_outcome is not None:
            payload["intent_id"] = int(terminal_outcome.intent_id)
            payload["success"] = bool(terminal_outcome.success)
            if terminal_outcome.error_code:
                payload["error_code"] = str(terminal_outcome.error_code)
            if terminal_outcome.error_message:
                payload["error_message"] = str(terminal_outcome.error_message)
        log_level = "warning" if outcome == "failed" else "info"
        try:
            await create_zone_event(zone_id, _STARTUP_RECOVERY_OUTCOME_EVENT, payload)
        except Exception:
            logger.warning(
                "Startup recovery: failed to write zone_event zone_id=%s task_id=%s outcome=%s",
                zone_id,
                task_id,
                outcome,
                exc_info=True,
            )
        try:
            send_service_log(
                service="automation-engine",
                level=log_level,
                message="AE3 startup recovery outcome",
                context={"zone_id": zone_id, **payload},
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to write service log zone_id=%s task_id=%s outcome=%s",
                zone_id,
                task_id,
                outcome,
                exc_info=True,
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
        await emit_task_failed_alert(
            alert_repository=self._alert_repository,
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            extra_details={"recovery_source": recovery_source},
        )

    async def _sync_workflow_failure_state(self, *, task: AutomationTask, now: datetime) -> None:
        from ae3lite.domain.services.workflow_failure_rollback import (
            resolve_workflow_phase_after_task_failure,
        )

        rollback_phase = resolve_workflow_phase_after_task_failure(task)
        scheduler_task_id = (
            None
            if rollback_phase in {"ready", "irrig_recirc"}
            else str(task.id)
        )
        payload = {
            "ae3_cycle_start_stage": str(getattr(task, "current_stage", "") or ""),
            "ae3_failure_rollback": True,
            "ae3_failed_task_id": int(getattr(task, "id", 0) or 0) or None,
        }
        await self._safe_upsert_workflow_phase(
            zone_id=task.zone_id,
            workflow_phase=rollback_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )

    async def _safe_upsert_workflow_phase(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: dict[str, Any],
        scheduler_task_id: str,
        now: datetime,
    ) -> None:
        if self._workflow_repository is None:
            return
        try:
            await self._workflow_repository.upsert_phase(
                zone_id=zone_id,
                workflow_phase=workflow_phase,
                payload=payload,
                scheduler_task_id=scheduler_task_id,
                now=now,
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to sync zone_workflow_state zone_id=%s task_id=%s phase=%s",
                zone_id,
                scheduler_task_id,
                workflow_phase,
                exc_info=True,
            )

    async def _should_skip_foreign_owned_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> bool:
        worker_owner = self._worker_owner
        if not worker_owner:
            return False

        task_owner = str(task.claimed_by or "").strip()
        if not task_owner or task_owner == worker_owner:
            return False

        return await self._foreign_lease_blocks_recovery(zone_id=int(task.zone_id), now=now)

    async def _foreign_lease_blocks_recovery(
        self,
        *,
        zone_id: int,
        now: datetime,
    ) -> bool:
        worker_owner = self._worker_owner
        if not worker_owner:
            return False

        get_lease = getattr(self._lease_repository, "get", None)
        if not callable(get_lease):
            return False

        lease = await get_lease(zone_id=zone_id)
        if lease is None:
            return False

        lease_owner = str(getattr(lease, "owner", "") or "").strip()
        if lease_owner == "" or lease_owner == worker_owner:
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

    def _build_terminal_outcome(self, *, task: AutomationTask) -> StartupRecoveryTerminalOutcome | None:
        intent_id = task.intent_id or 0
        if intent_id <= 0:
            return None
        return StartupRecoveryTerminalOutcome(
            task_id=task.id,
            intent_id=intent_id,
            success=task.status == "completed",
            error_code=task.error_code,
            error_message=task.error_message,
        )
