"""Recover AE3-Lite v2 in-flight tasks safely after runtime restart."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from ae3lite.application.dto import StartupRecoveryResult, StartupRecoveryTerminalOutcome
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import CommandReconcileError, StartupRecoveryError, TaskExecutionError
from ae3lite.domain.services.topology_registry import TopologyRegistry

logger = logging.getLogger(__name__)


class StartupRecoveryUseCase:
    """Reconciles persisted in-flight tasks without issuing a new publish.

    v2: Uses topology registry for done-transition routing instead of payload keys.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        lease_repository: Any,
        reconcile_command_use_case: Any,
        command_gateway: Any | None = None,
        workflow_repository: Any | None = None,
        topology_registry: Optional[TopologyRegistry] = None,
    ) -> None:
        self._task_repository = task_repository
        self._lease_repository = lease_repository
        self._reconcile_command_use_case = reconcile_command_use_case
        self._command_gateway = command_gateway
        self._workflow_repository = workflow_repository
        self._registry = topology_registry or TopologyRegistry()

    async def run(self, *, now: datetime) -> StartupRecoveryResult:
        released_expired_leases = await self._lease_repository.release_expired(now=now)
        tasks = await self._task_repository.list_for_startup_recovery()

        completed_tasks = 0
        failed_tasks = 0
        waiting_command_tasks = 0
        recovered_waiting_command_tasks = 0
        terminal_outcomes: list[StartupRecoveryTerminalOutcome] = []

        for task in tasks:
            outcome, terminal_outcome = await self._recover_task(task=task, now=now)
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
                    "Startup recovery: unsupported outcome=%s task_id=%s zone_id=%s",
                    outcome,
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                )
                raise StartupRecoveryError(f"Unsupported startup recovery outcome={outcome}")
            if terminal_outcome is not None:
                terminal_outcomes.append(terminal_outcome)

        return StartupRecoveryResult(
            released_expired_leases=released_expired_leases,
            scanned_tasks=len(tasks),
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            waiting_command_tasks=waiting_command_tasks,
            recovered_waiting_command_tasks=recovered_waiting_command_tasks,
            terminal_outcomes=tuple(terminal_outcomes),
        )

    async def _recover_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None]:
        if not task.claimed_by:
            failed_task = await self._fail_task(
                task=task,
                error_code="startup_recovery_missing_owner",
                error_message=f"Task {task.id} has no claimed_by during startup recovery",
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        if self._command_gateway is not None and self._is_two_tank_task(task):
            return await self._recover_native_two_tank_task(task=task, now=now)

        try:
            result = await self._reconcile_command_use_case.run(task=task, now=now)
        except CommandReconcileError as exc:
            failed_task = await self._fail_task(
                task=task,
                error_code=self._reconcile_error_code(task),
                error_message=str(exc),
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        if result.is_terminal:
            if result.terminal_status == "DONE":
                return "completed", self._build_terminal_outcome(task=result.task)
            return "failed", self._build_terminal_outcome(task=result.task)

        if result.legacy_status is None:
            failed_task = await self._fail_task(
                task=task,
                error_code=self._missing_command_error_code(task),
                error_message=self._missing_command_error_message(task),
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        if task.status in {"claimed", "running"}:
            recovered_task = await self._task_repository.recover_waiting_command(
                task_id=task.id,
                now=now,
            )
            if recovered_task is None:
                logger.error(
                    "Startup recovery: recover_waiting_command returned None task_id=%s zone_id=%s status=%s",
                    task.id,
                    task.zone_id,
                    task.status,
                )
                raise StartupRecoveryError(f"Unable to recover task_id={task.id} into waiting_command")
            return "recovered_waiting_command", None

        return "waiting_command", None

    async def _recover_native_two_tank_task(
        self,
        *,
        task: AutomationTask,
        now: datetime,
    ) -> tuple[str, StartupRecoveryTerminalOutcome | None]:
        if task.status in {"claimed", "running"}:
            failed_task = await self._fail_task(
                task=task,
                error_code="startup_recovery_unconfirmed_command",
                error_message=f"Task {task.id} has no confirmed external command during startup recovery",
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        # Correction in-flight during a command batch → cannot safely resume dosing
        if task.correction is not None:
            failed_task = await self._fail_task(
                task=task,
                error_code="startup_recovery_correction_interrupted",
                error_message=(
                    f"Task {task.id} correction interrupted during {task.correction.corr_step}"
                ),
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        try:
            result = await self._command_gateway.recover_waiting_command(task=task, now=now)
        except TaskExecutionError as exc:
            failed_task = await self._fail_task(
                task=task,
                error_code=exc.code,
                error_message=str(exc),
                now=now,
            )
            return "failed", self._build_terminal_outcome(task=failed_task)

        if result["state"] == "waiting_command":
            return "waiting_command", None
        if result["state"] == "failed":
            return "failed", self._build_terminal_outcome(task=result["task"])
        if result["state"] != "done":
            logger.error(
                "Startup recovery: unsupported native recovery state=%s task_id=%s zone_id=%s",
                result["state"],
                task.id,
                task.zone_id,
            )
            raise StartupRecoveryError(f"Unsupported native recovery state={result['state']}")

        progressed_task = await self._apply_topology_done_transition(task=result["task"], now=now)
        if progressed_task.status == "completed":
            return "completed", self._build_terminal_outcome(task=progressed_task)
        if progressed_task.status == "failed":
            return "failed", self._build_terminal_outcome(task=progressed_task)
        return "recovered_waiting_command", None

    async def _apply_topology_done_transition(
        self, *, task: AutomationTask, now: datetime,
    ) -> AutomationTask:
        """v2 recovery: use topology registry to determine next stage after command DONE.

        1. Read task.current_stage
        2. Lookup StageDef from registry
        3. If terminal_error → fail
        4. If next_stage → transition to next stage
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
                error_message=f"Unknown stage {current_stage} in topology {topology}",
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
                    f"Unable to fail task_id={task.id} for unknown stage",
                )
            return failed

        # Terminal error stage
        if stage_def.terminal_error is not None:
            error_code, error_message = stage_def.terminal_error
            await self._safe_upsert_workflow_phase(
                zone_id=task.zone_id,
                workflow_phase="idle",
                payload={"ae3_cycle_start_stage": "failed"},
                scheduler_task_id=str(task.id),
                now=now,
            )
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
                    f"Unable to fail task_id={task.id} after recovery DONE",
                )
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
                    f"Unable to requeue task_id={task.id} after recovery DONE",
                )
            return requeued

        # No next_stage, no terminal_error → complete
        await self._safe_upsert_workflow_phase(
            zone_id=task.zone_id,
            workflow_phase="ready",
            payload={"ae3_cycle_start_stage": "complete_ready"},
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
                f"Unable to complete task_id={task.id} after recovery DONE",
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
                f"Unable to fail task_id={task.id} during startup recovery with error_code={error_code}"
            )
        return failed_task

    async def _sync_workflow_failure_state(self, *, task: AutomationTask, now: datetime) -> None:
        await self._safe_upsert_workflow_phase(
            zone_id=task.zone_id,
            workflow_phase="idle",
            payload={"ae3_cycle_start_stage": "failed"},
            scheduler_task_id=str(task.id),
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

    def _missing_command_error_code(self, task: AutomationTask) -> str:
        if task.status == "waiting_command":
            return "startup_recovery_inconsistent_command_state"
        return "startup_recovery_unconfirmed_command"

    def _reconcile_error_code(self, task: AutomationTask) -> str:
        if task.status == "waiting_command":
            return "startup_recovery_inconsistent_command_state"
        return "startup_recovery_unconfirmed_command"

    def _missing_command_error_message(self, task: AutomationTask) -> str:
        if task.status == "waiting_command":
            return f"Task {task.id} is waiting_command without resolvable legacy command"
        return f"Task {task.id} has no confirmed external command during startup recovery"

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

    def _is_two_tank_task(self, task: AutomationTask) -> bool:
        return task.topology in ("two_tank", "two_tank_drip_substrate_trays")
