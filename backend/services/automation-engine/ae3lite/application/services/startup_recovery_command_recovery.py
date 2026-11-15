"""StartupRecoveryUseCase command recovery: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto import StartupRecoveryTerminalOutcome
from ae3lite.application.services.correction_interrupt_safety import (
    build_pending_check_from_task,
    is_dose_correction_step,
)
from ae3lite.application.services.startup_recovery_shared import logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import StartupRecoveryError, TaskExecutionError
from ae3lite.infrastructure.metrics import (
    STARTUP_RECOVERY_TASK,
)


@dataclass(frozen=True)
class StartupRecoveryCommandRecoveryPorts:
    apply_topology_done_transition: Callable[..., Awaitable[Any]]
    build_terminal_outcome: Callable[..., Any]
    command_gateway: Callable[[], Any]
    correction_interrupt_verify_grace_sec: Callable[[], Any]
    emit_failed_task_alert: Callable[..., Awaitable[Any]]
    fail_task: Callable[..., Awaitable[Any]]
    finalize_recovery_failure: Callable[..., Awaitable[Any]]
    record_startup_recovery_outcome: Callable[..., Awaitable[Any]]
    registry: Callable[[], Any]
    release_lease_after_recovery_fail: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    global_emit_correction_interrupt_pending_verify: Callable[..., Any]


class StartupRecoveryCommandRecovery:
    def __init__(self, ports: StartupRecoveryCommandRecoveryPorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

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

        outcome, terminal_outcome, observability_task = await self.reconcile_command_task(
            task=task,
            now=now,
            recovery_source=recovery_source,
        )
        report_task = observability_task or task
        await self._ports.record_startup_recovery_outcome(
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
        outcome, terminal_outcome, observability_task = await self.reconcile_command_task(
            task=task,
            now=now,
            recovery_source=recovery_source,
        )
        report_task = observability_task or task
        await self._ports.record_startup_recovery_outcome(
            zone_id=int(report_task.zone_id),
            task_id=int(report_task.id),
            topology=str(report_task.topology or ""),
            stage=str(report_task.current_stage or ""),
            outcome=outcome,
            terminal_outcome=terminal_outcome,
            recovery_source=recovery_source,
        )
        return outcome, terminal_outcome, observability_task

    async def reconcile_pending_vs_terminal_idle_workflow(
        self,
        *,
        now: datetime,
    ) -> tuple[int, list[StartupRecoveryTerminalOutcome]]:
        """Снимает «осиротевшие» pending-задачи при idle workflow с терминальным *_stop stage в payload."""
        rows = await self._ports.task_repository().fetch_pending_with_idle_zone_workflow_rows()
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
            if not self._ports.registry().has_topology(topo):
                topo = "two_tank"
            try:
                st = self._ports.registry().get(topo, snapshot_stage)
            except KeyError:
                continue
            if st.terminal_error is None:
                continue
            failed = await self._ports.task_repository().fail_pending_or_active_for_recovery(
                task_id=task.id,
                error_code="startup_recovery_pending_vs_terminal_workflow",
                error_message=(
                    f"Отмена pending {task.task_type}: zone_workflow в терминальном stage "
                    f"{snapshot_stage} после остановки цикла"
                ),
                now=now,
                claim_generation=int(getattr(task, "claim_generation", 0) or 0),
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
            await self._ports.emit_failed_task_alert(
                task=failed,
                error_code="startup_recovery_pending_vs_terminal_workflow",
                error_message=str(failed.error_message or ""),
                now=now,
                recovery_source="startup_recovery",
            )
            await self._ports.release_lease_after_recovery_fail(task=task, now=now)
            terminal_outcome = self._ports.build_terminal_outcome(task=failed)
            if terminal_outcome is not None:
                outcomes.append(terminal_outcome)
            await self._ports.record_startup_recovery_outcome(
                zone_id=int(failed.zone_id),
                task_id=int(failed.id),
                topology=str(failed.topology or ""),
                stage=str(failed.current_stage or ""),
                outcome="failed",
                terminal_outcome=terminal_outcome,
                recovery_source="startup_recovery",
            )
        return failed_count, outcomes

    async def recover_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        if not task.claimed_by:
            failed_task = await self._ports.fail_task(
                task=task,
                error_code="startup_recovery_missing_owner",
                error_message=f"У задачи {task.id} отсутствует claimed_by во время startup recovery",
                now=now,
                recovery_source="startup_recovery",
            )
            return "failed", self._ports.build_terminal_outcome(task=failed_task), failed_task

        return await self.recover_native_two_tank_task(task=task, now=now)

    async def recover_native_two_tank_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        return await self.reconcile_command_task(
            task=task,
            now=now,
            recovery_source="startup_recovery",
        )

    async def reconcile_command_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        # Коррекцию mid-dose не resume'им (fail-closed), но critical по железу
        # откладываем: после power-loss узлы часто ещё offline, актуаторы уже OFF.
        if task.correction is not None:
            pending_check = None
            if is_dose_correction_step(getattr(task.correction, "corr_step", None)):
                pending_check = build_pending_check_from_task(
                    task=task,
                    now=now,
                    recovery_source=recovery_source,
                    verify_grace_sec=self._ports.correction_interrupt_verify_grace_sec(),
                )
            failed_task = await self._ports.fail_task(
                task=task,
                error_code="startup_recovery_correction_interrupted",
                error_message=(f"Коррекция задачи {task.id} была прервана на шаге {task.correction.corr_step}"),
                now=now,
                recovery_source=recovery_source,
            )
            if pending_check is not None:
                await self._ports.global_emit_correction_interrupt_pending_verify(check=pending_check, now=now)
                self._state.pending_correction_safety_checks.append(pending_check)
            return "failed", self._ports.build_terminal_outcome(task=failed_task), failed_task

        try:
            result = await self._ports.command_gateway().recover_waiting_command(task=task, now=now)
        except TaskExecutionError as exc:
            error_code = exc.code
            if task.status in {"claimed", "running"} and exc.code == "ae3_missing_ae_command":
                error_code = "startup_recovery_unconfirmed_command"
            failed_task = await self._ports.fail_task(
                task=task,
                error_code=error_code,
                error_message=str(exc),
                now=now,
                recovery_source=recovery_source,
            )
            return "failed", self._ports.build_terminal_outcome(task=failed_task), failed_task

        return await self.handle_recovery_gateway_result(
            task=task,
            result=result,
            now=now,
            recovery_source=recovery_source,
        )

    async def handle_recovery_gateway_result(
        self,
        *,
        task: AutomationTask,
        result: Mapping[str, Any],
        now: datetime,
        recovery_source: str,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None, AutomationTask | None]:
        if result["state"] == "waiting_command":
            poll_deadline_exceeded = getattr(
                self._ports.command_gateway(),
                "waiting_command_poll_deadline_exceeded",
                None,
            )
            if callable(poll_deadline_exceeded) and await poll_deadline_exceeded(task=task, now=now):
                failed_task = await self._ports.fail_task(
                    task=task,
                    error_code="ae3_command_poll_deadline_exceeded",
                    error_message=(f"Опрос команды превысил дедлайн для задачи {task.id} stage={task.current_stage}"),
                    now=now,
                    recovery_source=recovery_source,
                )
                return "failed", self._ports.build_terminal_outcome(task=failed_task), failed_task
            if task.status in {"claimed", "running"}:
                await self.persist_waiting_command_status(task=task, now=now)
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
            await self._ports.finalize_recovery_failure(
                task=failed_task,
                error_code=error_code,
                error_message=error_message,
                now=now,
                recovery_source=recovery_source,
            )
            return "failed", self._ports.build_terminal_outcome(task=failed_task), failed_task
        if result["state"] != "done":
            logger.error(
                "Startup recovery: неподдерживаемое native recovery state=%s task_id=%s zone_id=%s",
                result["state"],
                task.id,
                task.zone_id,
            )
            raise StartupRecoveryError(f"Неподдерживаемое состояние native recovery={result['state']}")

        progressed_task = await self._ports.apply_topology_done_transition(
            task=result["task"],
            now=now,
            recovery_source=recovery_source,
        )
        if progressed_task.status == "completed":
            return "completed", self._ports.build_terminal_outcome(task=progressed_task), progressed_task
        if progressed_task.status == "failed":
            return "failed", self._ports.build_terminal_outcome(task=progressed_task), progressed_task
        return "recovered_waiting_command", None, progressed_task

    async def persist_waiting_command_status(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> AutomationTask | None:
        """Фиксирует `waiting_command` для in-flight задачи после reconcile legacy-команды."""
        if task.status == "waiting_command":
            return task
        recover_waiting_command = getattr(self._ports.task_repository(), "recover_waiting_command", None)
        if not callable(recover_waiting_command):
            return None
        owner = str(task.claimed_by or "").strip()
        if not owner:
            return None
        try:
            return await recover_waiting_command(
                task_id=task.id,
                now=now,
                owner=owner,
                claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to persist waiting_command task_id=%s zone_id=%s",
                task.id,
                task.zone_id,
                exc_info=True,
            )
            return None
