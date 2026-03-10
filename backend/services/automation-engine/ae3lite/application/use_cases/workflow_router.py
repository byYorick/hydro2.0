"""WorkflowRouter — pure orchestrator for AE3-Lite v2 topology-driven workflow.

Dispatches to handler classes based on ``StageDef.handler``, interprets the
returned ``StageOutcome``, updates task state via repository, records
transitions in the audit trail, and updates the zone workflow phase.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.application.handlers.command import CommandHandler
from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import TopologyRegistry
from ae3lite.infrastructure.metrics import (
    COMMAND_TERMINAL,
    CORRECTION_COMPLETED,
    CORRECTION_STARTED,
    STAGE_DURATION,
    STAGE_ENTERED,
    STAGE_RETRY,
    TASK_COMPLETED,
    TASK_FAILED,
    TICK_DURATION,
)


class WorkflowRouter:
    """Topology-driven orchestrator: dispatch → handler → apply outcome → requeue.

    This class does NOT contain domain logic. All sensor reads, level checks,
    and correction calculations live in handler classes.
    """

    # Handler key → handler class mapping
    HANDLER_MAP: dict[str, type[BaseStageHandler]] = {
        "startup": StartupHandler,
        "command": CommandHandler,
        "clean_fill": CleanFillCheckHandler,
        "solution_fill": SolutionFillCheckHandler,
        "prepare_recirc": PrepareRecircCheckHandler,
        "prepare_recirc_window": PrepareRecircWindowHandler,
        "correction": CorrectionHandler,
    }

    def __init__(
        self,
        *,
        task_repository: Any,
        workflow_repository: Any,
        topology_registry: Optional[TopologyRegistry] = None,
        runtime_monitor: Any,
        command_gateway: Any,
        correction_planner: Any = None,
        alert_repository: Any = None,
        pid_state_repository: Any = None,
    ) -> None:
        self._task_repo = task_repository
        self._workflow_repo = workflow_repository
        self._registry = topology_registry or TopologyRegistry()
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway

        # Pre-instantiate handlers
        self._handlers: dict[str, BaseStageHandler] = {}
        for key, cls in self.HANDLER_MAP.items():
            kwargs: dict[str, Any] = {
                "runtime_monitor": runtime_monitor,
                "command_gateway": command_gateway,
            }
            if key == "correction":
                if correction_planner is not None:
                    kwargs["planner"] = correction_planner
                kwargs["pid_state_repository"] = pid_state_repository
            if key == "prepare_recirc_window":
                kwargs["alert_repository"] = alert_repository
            self._handlers[key] = cls(**kwargs)

    async def run(self, *, task: Any, plan: Any, now: datetime) -> Any:
        """Execute one stage of the workflow and return the updated task.

        Called by ExecuteTaskUseCase after claiming and marking the task running.
        """
        topology = task.topology
        current_stage = task.current_stage

        # Correction sub-machine takes priority
        if task.correction is not None:
            handler = self._handlers["correction"]
            stage_def = self._registry.get(topology, current_stage)
            outcome = await handler.run(
                task=task, plan=plan, stage_def=stage_def, now=now,
            )
            return await self._apply_outcome(
                task=task, plan=plan, outcome=outcome, now=now,
            )

        # Normal stage dispatch
        stage_def = self._registry.get(topology, current_stage)
        handler_key = stage_def.handler

        # complete_ready is terminal — no handler, just complete
        if current_stage == "complete_ready":
            return await self._complete_task(task=task, now=now)

        handler = self._handlers.get(handler_key)
        if handler is None:
            raise TaskExecutionError(
                "ae3_unknown_handler",
                f"No handler for key={handler_key!r} (stage={current_stage})",
            )

        outcome = await handler.run(
            task=task, plan=plan, stage_def=stage_def, now=now,
        )
        return await self._apply_outcome(
            task=task, plan=plan, outcome=outcome, now=now,
        )

    # ── Outcome application ─────────────────────────────────────────

    async def _apply_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        topology = task.topology
        owner = str(task.claimed_by or "")

        if outcome.kind == "poll":
            return await self._apply_poll(task=task, outcome=outcome, now=now)

        if outcome.kind == "transition":
            return await self._apply_transition(
                task=task, plan=plan, outcome=outcome, now=now,
            )

        if outcome.kind == "enter_correction":
            return await self._apply_enter_correction(
                task=task, outcome=outcome, now=now,
            )

        if outcome.kind == "exit_correction":
            return await self._apply_exit_correction(
                task=task, plan=plan, outcome=outcome, now=now,
            )

        if outcome.kind == "complete":
            return await self._complete_task(task=task, now=now)

        if outcome.kind == "fail":
            return await self._fail_task(
                task=task, now=now,
                error_code=outcome.error_code or "ae3_stage_failed",
                error_message=outcome.error_message or "Stage failed",
            )

        raise TaskExecutionError(
            "ae3_unknown_outcome_kind",
            f"Unknown StageOutcome.kind={outcome.kind!r}",
        )

    async def _apply_poll(
        self, *, task: Any, outcome: StageOutcome, now: datetime,
    ) -> Any:
        """Stay in the same stage, re-enqueue with delay."""
        workflow = task.workflow
        due_at = now + timedelta(seconds=max(0, outcome.due_delay_sec))

        await self._upsert_workflow_phase(
            task=task, workflow_phase=workflow.workflow_phase, now=now,
        )
        return await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=workflow,
            correction=task.correction,
            due_at=due_at,
            now=now,
        )

    async def _apply_transition(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Move to a new stage, clear correction state, compute deadline."""
        next_stage = outcome.next_stage
        if next_stage is None:
            raise TaskExecutionError(
                "ae3_transition_no_next_stage",
                "Transition outcome requires next_stage",
            )

        topology = task.topology
        next_def = self._registry.get(topology, next_stage)

        # Record metrics for completed stage
        self._record_stage_duration(task=task, now=now)
        STAGE_ENTERED.labels(topology=topology, stage=next_stage).inc()

        # Compute new workflow state
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        deadline = self._compute_deadline(
            stage_def=next_def, runtime=runtime, now=now,
        )
        clean_fill_cycle = (
            outcome.clean_fill_cycle
            if outcome.clean_fill_cycle is not None
            else task.workflow.clean_fill_cycle
        )

        new_workflow = WorkflowState(
            current_stage=next_stage,
            workflow_phase=next_def.workflow_phase,
            stage_deadline_at=deadline,
            stage_retry_count=outcome.stage_retry_count or 0,
            stage_entered_at=now,
            clean_fill_cycle=clean_fill_cycle,
        )

        # Record transition in audit trail
        await self._task_repo.record_transition(
            task_id=task.id,
            from_stage=task.current_stage,
            to_stage=next_stage,
            workflow_phase=next_def.workflow_phase,
            now=now,
        )

        # Update zone workflow phase (pass next_stage explicitly so payload reflects new stage)
        await self._upsert_workflow_phase(
            task=task, workflow_phase=next_def.workflow_phase, stage=next_stage, now=now,
        )

        due_at = now + timedelta(seconds=max(0, outcome.due_delay_sec))
        return await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=new_workflow,
            correction=None,  # Clear correction on transition
            due_at=due_at,
            now=now,
        )

    async def _apply_enter_correction(
        self,
        *,
        task: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Enter or continue correction sub-machine within current stage."""
        corr = outcome.correction
        if corr is None:
            raise TaskExecutionError(
                "ae3_enter_correction_no_state",
                "enter_correction outcome requires correction state",
            )

        # Record metrics on first entry
        if task.correction is None:
            CORRECTION_STARTED.labels(topology=task.topology).inc()

        workflow = task.workflow
        await self._upsert_workflow_phase(
            task=task, workflow_phase=workflow.workflow_phase, now=now,
        )

        due_at = now + timedelta(seconds=max(0, outcome.due_delay_sec))
        return await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=workflow,
            correction=corr,
            due_at=due_at,
            now=now,
        )

    async def _apply_exit_correction(
        self,
        *,
        task: Any,
        plan: Any,
        outcome: StageOutcome,
        now: datetime,
    ) -> Any:
        """Correction finished — transition to return stage."""
        final_corr = outcome.correction if outcome.correction is not None else task.correction
        success = (
            final_corr.outcome_success
            if final_corr and final_corr.outcome_success is not None
            else False
        )
        CORRECTION_COMPLETED.labels(
            topology=task.topology,
            outcome="success" if success else "fail",
        ).inc()

        # Delegate to normal transition
        return await self._apply_transition(
            task=task, plan=plan, outcome=outcome, now=now,
        )

    # ── Terminal states ─────────────────────────────────────────────

    async def _complete_task(self, *, task: Any, now: datetime) -> Any:
        await self._upsert_workflow_phase(
            task=task, workflow_phase="ready", now=now,
        )
        TASK_COMPLETED.labels(topology=task.topology).inc()
        completed = await self._task_repo.mark_completed(
            task_id=task.id, owner=str(task.claimed_by or ""), now=now,
        )
        if completed is None:
            raise TaskExecutionError(
                "ae3_complete_transition_failed",
                f"Task {task.id} could not transition to completed",
            )
        return completed

    async def _fail_task(
        self, *, task: Any, now: datetime, error_code: str, error_message: str,
    ) -> Any:
        await self._upsert_workflow_phase(
            task=task, workflow_phase="idle", now=now,
        )
        TASK_FAILED.labels(topology=task.topology, error_code=error_code).inc()
        raise TaskExecutionError(error_code, error_message)

    # ── Helpers ─────────────────────────────────────────────────────

    def _compute_deadline(
        self, *, stage_def: Any, runtime: Mapping[str, Any], now: datetime,
    ) -> Optional[datetime]:
        """Compute stage_deadline_at from runtime config timeout keys."""
        if stage_def.timeout_key is None:
            return None
        timeout_sec = runtime.get(stage_def.timeout_key)
        if timeout_sec is None:
            return None
        return now + timedelta(seconds=int(timeout_sec))

    def _record_stage_duration(self, *, task: Any, now: datetime) -> None:
        entered = task.workflow.stage_entered_at
        if entered is not None:
            now_cmp = now.replace(tzinfo=None) if now.tzinfo is not None else now
            entered_cmp = entered.replace(tzinfo=None) if entered.tzinfo is not None else entered
            duration = (now_cmp - entered_cmp).total_seconds()
            STAGE_DURATION.labels(
                topology=task.topology, stage=task.current_stage,
            ).observe(max(0, duration))

    async def _upsert_workflow_phase(
        self, *, task: Any, workflow_phase: str, stage: str | None = None, now: datetime,
    ) -> None:
        """Update zone workflow state (external visibility).

        ``stage`` overrides the stage written to payload when calling during a
        transition (where task.current_stage is still the OLD stage).
        """
        if self._workflow_repo is not None:
            await self._workflow_repo.upsert_phase(
                zone_id=task.zone_id,
                workflow_phase=workflow_phase,
                payload={"ae3_cycle_start_stage": stage if stage is not None else task.current_stage},
                scheduler_task_id=str(task.id),
                now=now,
            )
