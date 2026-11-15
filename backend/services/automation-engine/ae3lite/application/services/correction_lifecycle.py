"""Correction lifecycle: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.decision_window_reader import (
    DecisionWindowResult,
)
from ae3lite.domain.entities.workflow_state import CorrectionState


@dataclass(frozen=True)
class CorrectionLifecyclePorts:
    completion_clock: Callable[..., Any]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    run_command_batch_checked: Callable[[], Any]
    run_wait_observe: Callable[..., Awaitable[Any]]
    sensor_mode_controller: Callable[[], Any]


class CorrectionLifecycle:
    def __init__(self, ports: CorrectionLifecyclePorts) -> None:
        self._ports = ports

    async def run_activate(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        sensor_cmds = self._ports.sensor_mode_controller().build_commands(
            plan=plan,
            cmd="activate_sensor_mode",
            params={"stabilization_time_sec": corr.stabilization_sec},
        )
        current_task = task
        if sensor_cmds:
            result = await self._ports.run_command_batch_checked()(
                task=current_task,
                commands=sensor_cmds,
                now=now,
            )
            current_task = result.get("task") or current_task
        _, _, stabilization_delay_sec = self.completion_anchored_window(
            now=now,
            wait_sec=corr.stabilization_sec,
        )
        next_corr = replace(corr, corr_step="corr_wait_stable")
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=stabilization_delay_sec,
            task_override=current_task if current_task is not task else None,
        )

    def run_wait_stable(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        next_corr = replace(corr, corr_step="corr_check")
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
        )

    async def run_wait_ec(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._ports.run_wait_observe(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type="ec",
            sensor_type="EC",
        )

    async def run_wait_ph(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._ports.run_wait_observe(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type="ph",
            sensor_type="PH",
        )

    async def run_deactivate(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        current_task = task
        if corr.activated_here:
            sensor_cmds = self._ports.sensor_mode_controller().build_commands(
                plan=plan,
                cmd="deactivate_sensor_mode",
                params={},
            )
            if sensor_cmds:
                result = await self._ports.run_command_batch_checked()(
                    task=current_task,
                    commands=sensor_cmds,
                    now=now,
                )
                current_task = result.get("task") or current_task

        next_corr = replace(corr, corr_step="corr_done")
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
            task_override=current_task if current_task is not task else None,
        )

    def run_done(self, *, corr: CorrectionState) -> StageOutcome:
        success = corr.outcome_success if corr.outcome_success is not None else False
        next_stage = corr.return_stage_success if success else corr.return_stage_fail
        return StageOutcome(kind="exit_correction", next_stage=next_stage, correction=corr)

    async def ensure_sensor_mode_active_for_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        failed_node_uid: str | None,
        failed_channel: str | None,
        retry_cmd: str,
    ) -> Any:
        return await self._ports.sensor_mode_controller().ensure_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=failed_node_uid,
            failed_channel=failed_channel,
            retry_cmd=retry_cmd,
        )

    async def maybe_reactivate_sensor_mode_after_empty_window(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        ph: DecisionWindowResult,
        ec: DecisionWindowResult,
    ) -> StageOutcome | None:
        return await self._ports.sensor_mode_controller().maybe_reactivate_after_empty_window(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            ph=ph,
            ec=ec,
        )

    def resolve_dose_completed_at(self) -> datetime:
        """Anchor ``last_dose_at`` at terminal DONE time, not tick start."""
        completed = self._ports.completion_clock()
        if completed.tzinfo is not None:
            completed = completed.astimezone(timezone.utc).replace(tzinfo=None)
        return completed

    def completion_anchored_window(
        self,
        *,
        now: datetime,
        wait_sec: float,
    ) -> tuple[datetime, datetime, float]:
        """Return one safe wall-clock anchor for persistence and requeue.

        ``WorkflowRouter`` computes ``due_at`` from the tick's original
        ``now``.  Therefore the returned delay includes time spent waiting for
        terminal ``DONE``; otherwise command latency silently shortens hold,
        stabilization and dilute windows.
        """
        normalized_now = self.normalize_timestamp(now)
        completed_at = self.resolve_dose_completed_at()
        if normalized_now is None:
            normalized_now = completed_at
        # A wall-clock rollback must not move the safety window before the
        # handler tick that issued the command.
        anchor = max(normalized_now, completed_at)
        wait_until_naive = anchor + timedelta(seconds=max(0.0, float(wait_sec)))
        due_delay_sec = max(0.0, (wait_until_naive - normalized_now).total_seconds())
        wait_until = wait_until_naive.replace(tzinfo=timezone.utc) if now.tzinfo is not None else wait_until_naive
        return anchor, wait_until, due_delay_sec

    def normalize_timestamp(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
