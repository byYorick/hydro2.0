"""WorkflowRouter — pure orchestrator for AE3-Lite v2 topology-driven workflow.

Dispatches to handler classes based on ``StageDef.handler``, interprets the
returned ``StageOutcome``, updates task state via repository, records
transitions in the audit trail, and updates the zone workflow phase.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.handlers.await_ready import AwaitReadyHandler
from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.application.handlers.command import CommandHandler
from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler
from ae3lite.application.handlers.irrigation_recovery import IrrigationRecoveryCheckHandler
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
from common.db import create_zone_event


logger = logging.getLogger(__name__)


class WorkflowRouter:
    """Topology-driven orchestrator: dispatch → handler → apply outcome → requeue.

    This class does NOT contain domain logic. All sensor reads, level checks,
    and correction calculations live in handler classes.
    """

    # Handler key → handler class mapping
    HANDLER_MAP: dict[str, type[BaseStageHandler]] = {
        "startup": StartupHandler,
        "await_ready": AwaitReadyHandler,
        "decision_gate": DecisionGateHandler,
        "command": CommandHandler,
        "clean_fill": CleanFillCheckHandler,
        "solution_fill": SolutionFillCheckHandler,
        "irrigation_check": IrrigationCheckHandler,
        "irrigation_recovery": IrrigationRecoveryCheckHandler,
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
        decision_controller: Any = None,
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
            if key in {"await_ready", "decision_gate", "irrigation_check"}:
                kwargs["task_repository"] = task_repository
            if key == "decision_gate":
                kwargs["decision_controller"] = decision_controller
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

        # ready-style terminal stages are handled centrally
        if current_stage == "complete_ready" and str(getattr(task, "task_type", "") or "") == "irrigation_start":
            if int(getattr(task, "irrigation_replay_count", 0) or 0) > 0:
                return await self._apply_transition(
                    task=task,
                    plan=plan,
                    outcome=StageOutcome(kind="transition", next_stage="irrigation_start"),
                    now=now,
                )
            return await self._complete_task(task=task, now=now)
        if handler_key == "ready":
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

        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=workflow,
            correction=task.correction,
            due_at=due_at,
            now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_poll_apply_failed",
            error_message=f"Task {task.id} could not persist poll outcome",
        )
        await self._safe_upsert_workflow_phase(
            task=resolved_task,
            workflow_phase=workflow.workflow_phase,
            now=now,
        )
        return resolved_task

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
        same_stage = next_stage == task.current_stage

        # Record metrics for completed stage
        if not same_stage:
            self._record_stage_duration(task=task, now=now)
            STAGE_ENTERED.labels(topology=topology, stage=next_stage).inc()
        if (outcome.stage_retry_count or 0) > 0:
            STAGE_RETRY.labels(topology=topology, stage=next_stage).inc()

        # Compute new workflow state
        runtime = plan.runtime if isinstance(plan.runtime, Mapping) else {}
        deadline = (
            task.workflow.stage_deadline_at
            if same_stage
            else self._compute_deadline(task=task, stage_def=next_def, runtime=runtime, now=now)
        )
        clean_fill_cycle = (
            outcome.clean_fill_cycle
            if outcome.clean_fill_cycle is not None
            else task.workflow.clean_fill_cycle
        )
        stage_retry_count = (
            outcome.stage_retry_count
            if outcome.stage_retry_count is not None
            else (task.workflow.stage_retry_count if same_stage else 0)
        )
        stage_entered_at = task.workflow.stage_entered_at if same_stage else now

        new_workflow = WorkflowState(
            current_stage=next_stage,
            workflow_phase=next_def.workflow_phase,
            stage_deadline_at=deadline,
            stage_retry_count=stage_retry_count,
            stage_entered_at=stage_entered_at,
            clean_fill_cycle=clean_fill_cycle,
            control_mode=task.workflow.control_mode,
            pending_manual_step=None,
        )

        due_at = now + timedelta(seconds=max(0, outcome.due_delay_sec))
        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=new_workflow,
            correction=None,  # Clear correction on transition
            due_at=due_at,
            now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_transition_apply_failed",
            error_message=f"Task {task.id} could not transition to {next_stage}",
        )
        await self._safe_record_transition(
            task_id=task.id,
            from_stage=task.current_stage,
            to_stage=next_stage,
            workflow_phase=next_def.workflow_phase,
            now=now,
        )
        await self._safe_upsert_workflow_phase(
            task=resolved_task,
            workflow_phase=next_def.workflow_phase,
            stage=next_stage,
            now=now,
        )
        return resolved_task

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
        due_at = now + timedelta(seconds=max(0, outcome.due_delay_sec))
        updated_task = await self._task_repo.update_stage(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            workflow=workflow,
            correction=corr,
            due_at=due_at,
            now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=updated_task,
            error_code="ae3_correction_apply_failed",
            error_message=f"Task {task.id} could not persist correction state",
        )
        await self._safe_upsert_workflow_phase(
            task=resolved_task,
            workflow_phase=workflow.workflow_phase,
            now=now,
        )
        return resolved_task

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

        if (
            str(outcome.next_stage or "").strip().lower() == "irrigation_check"
            and str(task.current_stage or "").strip().lower() == "irrigation_check"
        ):
            try:
                await create_zone_event(
                    int(task.zone_id),
                    "IRRIGATION_CORRECTION_COMPLETED",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "topology": str(getattr(task, "topology", "") or ""),
                        "success": bool(success),
                    },
                )
            except Exception:
                logger.warning(
                    "AE3 failed to log IRRIGATION_CORRECTION_COMPLETED zone_id=%s task_id=%s",
                    int(getattr(task, "zone_id", 0) or 0),
                    int(getattr(task, "id", 0) or 0),
                    exc_info=True,
                )

        # Delegate to normal transition
        return await self._apply_transition(
            task=task, plan=plan, outcome=outcome, now=now,
        )

    # ── Terminal states ─────────────────────────────────────────────

    async def _complete_task(self, *, task: Any, now: datetime) -> Any:
        TASK_COMPLETED.labels(topology=task.topology).inc()
        completed = await self._task_repo.mark_completed(
            task_id=task.id, owner=str(task.claimed_by or ""), now=now,
        )
        resolved_task = await self._resolve_inactive_terminal_task(
            task_id=task.id,
            updated_task=completed,
            error_code="ae3_complete_transition_failed",
            error_message=f"Task {task.id} could not transition to completed",
        )
        await self._safe_upsert_workflow_phase(
            task=resolved_task, workflow_phase="ready", now=now,
        )
        return resolved_task

    async def _fail_task(
        self, *, task: Any, now: datetime, error_code: str, error_message: str,
    ) -> Any:
        TASK_FAILED.labels(topology=task.topology, error_code=error_code).inc()
        raise TaskExecutionError(error_code, error_message)

    # ── Helpers ─────────────────────────────────────────────────────

    def _compute_deadline(
        self, *, task: Any, stage_def: Any, runtime: Mapping[str, Any], now: datetime,
    ) -> Optional[datetime]:
        """Compute stage_deadline_at from runtime config timeout keys."""
        if stage_def.name == "irrigation_check":
            irrigation_runtime = runtime.get("irrigation_execution")
            irrigation_runtime = irrigation_runtime if isinstance(irrigation_runtime, Mapping) else {}
            explicit_timeout = irrigation_runtime.get("stage_timeout_sec")
            if explicit_timeout is not None:
                try:
                    return now + timedelta(seconds=max(1, int(explicit_timeout)))
                except (TypeError, ValueError):
                    pass
            requested_duration_sec = getattr(task, "irrigation_requested_duration_sec", None)
            if requested_duration_sec is None:
                requested_duration_sec = runtime.get("irrigation_requested_duration_sec")
            if requested_duration_sec is None:
                requested_duration_sec = irrigation_runtime.get("duration_sec")
            if requested_duration_sec is None:
                return None
            slack_raw = irrigation_runtime.get("correction_slack_sec")
            if slack_raw is None:
                slack = (
                    900
                    if bool(irrigation_runtime.get("correction_during_irrigation", True))
                    else 0
                )
            else:
                try:
                    slack = max(0, min(7200, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = 900 if bool(irrigation_runtime.get("correction_during_irrigation", True)) else 0
            total_sec = int(requested_duration_sec) + slack
            total_sec = min(max(1, total_sec), 86400)
            return now + timedelta(seconds=total_sec)
        if stage_def.name == "solution_fill_check":
            base_raw = runtime.get("solution_fill_timeout_sec")
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = runtime.get("solution_fill_correction_slack_sec")
            if slack_raw is None:
                slack = 900
            else:
                try:
                    slack = max(0, min(7200, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = 900
            total_sec = min(base_sec + slack, 86400)
            return now + timedelta(seconds=total_sec)
        if stage_def.name == "prepare_recirculation_check":
            # Base window from retry config; inline EC/pH corrections need extra wall time on real HL→MQTT→node.
            base_raw = runtime.get("prepare_recirculation_timeout_sec")
            if base_raw is None:
                return None
            try:
                base_sec = max(1, int(base_raw))
            except (TypeError, ValueError):
                return None
            slack_raw = runtime.get("prepare_recirculation_correction_slack_sec")
            if slack_raw is None:
                slack = 900
            else:
                try:
                    slack = max(0, min(7200, int(slack_raw)))
                except (TypeError, ValueError):
                    slack = 900
            total_sec = min(base_sec + slack, 86400)
            return now + timedelta(seconds=total_sec)
        if stage_def.name == "irrigation_recovery_check":
            recovery_runtime = runtime.get("irrigation_recovery")
            recovery_runtime = recovery_runtime if isinstance(recovery_runtime, Mapping) else {}
            timeout_sec = recovery_runtime.get("timeout_sec")
            if timeout_sec is None and stage_def.timeout_key is not None:
                timeout_sec = runtime.get(stage_def.timeout_key)
            if timeout_sec is None:
                return None
            return now + timedelta(seconds=int(timeout_sec))
        if stage_def.timeout_key is None:
            return None
        timeout_sec = runtime.get(stage_def.timeout_key)
        if timeout_sec is None:
            return None
        return now + timedelta(seconds=int(timeout_sec))

    def _record_stage_duration(self, *, task: Any, now: datetime) -> None:
        entered = task.workflow.stage_entered_at
        if entered is not None:
            now_cmp = self._normalize_utc_naive(now)
            entered_cmp = self._normalize_utc_naive(entered)
            duration = (now_cmp - entered_cmp).total_seconds()
            STAGE_DURATION.labels(
                topology=task.topology, stage=task.current_stage,
            ).observe(max(0, duration))

    def _normalize_utc_naive(self, value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value

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

    async def _safe_upsert_workflow_phase(
        self, *, task: Any, workflow_phase: str, stage: str | None = None, now: datetime,
    ) -> None:
        try:
            await self._upsert_workflow_phase(
                task=task,
                workflow_phase=workflow_phase,
                stage=stage,
                now=now,
            )
        except Exception:
            logger.warning(
                "AE3 failed to sync zone_workflow_state zone_id=%s task_id=%s phase=%s stage=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                workflow_phase,
                stage if stage is not None else str(getattr(task, "current_stage", "") or ""),
                exc_info=True,
            )

    async def _safe_record_transition(
        self,
        *,
        task_id: int,
        from_stage: str | None,
        to_stage: str,
        workflow_phase: str | None,
        now: datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            await self._task_repo.record_transition(
                task_id=task_id,
                from_stage=from_stage,
                to_stage=to_stage,
                workflow_phase=workflow_phase,
                metadata=metadata,
                now=now,
            )
        except Exception:
            logger.warning(
                "AE3 failed to record stage transition task_id=%s from=%s to=%s",
                task_id,
                from_stage,
                to_stage,
                exc_info=True,
            )

    async def _resolve_inactive_terminal_task(
        self,
        *,
        task_id: int,
        updated_task: Any,
        error_code: str,
        error_message: str,
    ) -> Any:
        if updated_task is not None:
            return updated_task
        get_task_by_id = getattr(self._task_repo, "get_by_id", None)
        if callable(get_task_by_id):
            current_task = await get_task_by_id(task_id=task_id)
            if current_task is not None and not bool(getattr(current_task, "is_active", False)):
                return current_task
        raise TaskExecutionError(error_code, error_message)
