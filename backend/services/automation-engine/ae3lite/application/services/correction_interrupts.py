"""Correction interrupts: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_shared import _logger
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.infrastructure.metrics import (
    CORRECTION_CONTROL_MODE_BLOCKED,
    CORRECTION_ESTOP_INTERRUPT,
)


@dataclass(frozen=True)
class CorrectionInterruptsPorts:
    deadline_reached: Callable[[], Any]
    deadline_too_close_for_irr_probe: Callable[[], Any]
    handle_control_mode_flow_path_interrupt: Callable[[], Any]
    irr_probe_deadline_budget_sec: Callable[[], Any]
    log_correction_event: Callable[..., Awaitable[Any]]
    probe_irr_state: Callable[[], Any]
    read_recent_storage_event: Callable[[], Any]
    reconciled_estop_event_ids: Callable[[], Any]
    record_deadline_target_outcome: Callable[[], Any]
    remaining_stage_time_sec: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    target_outcome_on_deadline: Callable[[], Any]
    transition_policy: Callable[[], Any]


class CorrectionInterrupts:
    def __init__(self, ports: CorrectionInterruptsPorts) -> None:
        self._ports = ports

    async def interrupt_for_emergency_stop(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        """Controlled correction exit on recent EMERGENCY_STOP_ACTIVATED.

        Parent flow-path stages reconcile pump/valve state; correction only
        deactivates sensors it activated and returns through corr_deactivate.
        """
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None

        estop_event = await self._ports.read_recent_storage_event()(
            task=task,
            event_types=("EMERGENCY_STOP_ACTIVATED",),
            max_age_sec=86400,  # config-literal: one-day ESTOP replay window
        )
        if not isinstance(estop_event, Mapping):
            return None

        estop_event_id = int(estop_event.get("event_id") or 0)
        if estop_event_id > 0 and estop_event_id in self._ports.reconciled_estop_event_ids():
            return None

        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_SKIPPED_EMERGENCY_STOP",
            task=task,
            corr=corr,
            payload={"estop_event_id": estop_event_id},
        )
        CORRECTION_ESTOP_INTERRUPT.inc()
        if estop_event_id > 0:
            self._ports.reconciled_estop_event_ids().add(estop_event_id)

        return self.transition_to_deactivate_or_return(corr=corr, success=False)

    async def interrupt_for_control_mode_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> StageOutcome | None:
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        outcome = await self._ports.handle_control_mode_flow_path_interrupt()(
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
            reason="control_mode_manual",
        )
        if outcome is not None:
            CORRECTION_CONTROL_MODE_BLOCKED.inc()
        return outcome

    async def assert_flow_path_active(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        expected = self.expected_flow_path_state(current_stage=str(task.current_stage or ""))
        if expected is None:
            return
        await self._ports.probe_irr_state()(
            task=task,
            plan=plan,
            now=now,
            expected=expected,
        )

    def expected_flow_path_state(self, *, current_stage: str) -> Mapping[str, bool] | None:
        stage = str(current_stage or "").strip().lower()
        if stage == "solution_fill_check":
            return {
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            }
        if stage == "prepare_recirculation_check":
            return {
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            }
        return None

    async def interrupt_for_stage_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None
        deadline_reached = self._ports.deadline_reached()(
            now=now,
            deadline=task.workflow.stage_deadline_at,
        )
        if not deadline_reached:
            return None
        return await self.stage_deadline_transition_outcome(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
        )

    async def interrupt_after_command_admission_failure(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        exc: TaskExecutionError,
    ) -> StageOutcome | None:
        """Convert a pre-publish dose admission refusal into stage outcome.

        A real command poll timeout is always fail-closed: publication already
        happened and the physical outcome is unknown. Only the admission guard,
        which runs before any History Logger side effect, may end the correction
        window through the ordinary stage-deadline policy.
        """
        if str(getattr(exc, "code", "") or "").strip().lower() != ErrorCodes.AE3_COMMAND_STAGE_BUDGET_INSUFFICIENT:
            return None
        if corr.corr_step in {"corr_deactivate", "corr_done"}:
            return None
        outcome = await self.stage_deadline_transition_outcome(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            completion_reason="stage_budget_exhausted",
        )
        if outcome is None:
            return None
        _logger.info(
            "AE3 correction: dose rejected by stage admission → graceful interrupt "
            "zone_id=%s task_id=%s stage=%s corr_step=%s next_stage=%s",
            getattr(task, "zone_id", None),
            getattr(task, "id", None),
            getattr(task, "current_stage", None),
            corr.corr_step,
            outcome.next_stage,
        )
        return outcome

    async def stage_deadline_transition_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        completion_reason: str = "stage_deadline",
    ) -> StageOutcome | None:
        current_stage = str(task.current_stage).strip().lower()
        targets_reached: bool | None = None
        if current_stage == "irrigation_check":
            target_snapshot = await self._ports.target_outcome_on_deadline()(
                task=task,
                plan=plan,
                now=now,
            )
            await self._ports.record_deadline_target_outcome()(
                task=task,
                snapshot=target_snapshot,
                reason=completion_reason,
            )
            raw_targets_reached = target_snapshot.get("targets_reached")
            targets_reached = bool(raw_targets_reached) if raw_targets_reached is not None else None
        return self._ports.transition_policy().decide_stage_deadline_transition(
            corr=corr,
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            deadline_reached=True,
            targets_reached=targets_reached,
        )

    def interrupt_for_imminent_flow_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> StageOutcome | None:
        current_stage = str(task.current_stage).strip().lower()
        if self.expected_flow_path_state(current_stage=current_stage) is None:
            return None
        runtime = self._ports.require_runtime_plan()(plan=plan)
        deadline_too_close = self._ports.deadline_too_close_for_irr_probe()(
            now=now,
            deadline=task.workflow.stage_deadline_at,
            runtime=runtime,
        )
        return self._ports.transition_policy().decide_imminent_flow_probe_transition(
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            expects_flow_path=True,
            deadline_too_close=deadline_too_close,
        )

    def enter_correction_after_delay_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome:
        retry_deadline_outcome = self.interrupt_for_imminent_retry_then_probe_deadline(
            task=task_override or task,
            plan=plan,
            now=now,
            due_delay_sec=due_delay_sec,
            task_override=task_override,
        )
        if retry_deadline_outcome is not None:
            return retry_deadline_outcome
        return StageOutcome(
            kind="enter_correction",
            correction=corr,
            due_delay_sec=due_delay_sec,
            task_override=task_override,
        )

    def interrupt_for_imminent_retry_then_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome | None:
        current_stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        # Short-circuit: flow-path probe protection only applies during stages
        # that drive valves/pumps; other stages' fixtures may not even carry a
        # stage_deadline_at, so we must avoid touching base helpers below.
        if self.expected_flow_path_state(current_stage=current_stage) is None:
            return None

        runtime = self._ports.require_runtime_plan()(plan=plan)
        remaining = self._ports.remaining_stage_time_sec()(
            now=now,
            deadline=task.workflow.stage_deadline_at,
        )
        required_budget = max(0.0, float(due_delay_sec)) + self._ports.irr_probe_deadline_budget_sec()(
            runtime=runtime,
        )
        return self._ports.transition_policy().decide_imminent_retry_then_probe_transition(
            current_stage=current_stage,
            stage_retry_count=task.workflow.stage_retry_count,
            expects_flow_path=True,
            remaining_sec=remaining,
            required_budget_sec=required_budget,
            task_override=task_override,
        )

    def transition_to_deactivate_or_return(
        self,
        *,
        corr: CorrectionState,
        success: bool,
    ) -> StageOutcome:
        return self._ports.transition_policy().transition_to_deactivate_or_return(
            corr=corr,
            success=success,
        )
