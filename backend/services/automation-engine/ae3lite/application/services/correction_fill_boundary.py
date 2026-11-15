"""Correction fill boundary: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_shared import _logger
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


@dataclass(frozen=True)
class CorrectionFillBoundaryPorts:
    check_sensor_consistency: Callable[[], Any]
    log_correction_event: Callable[..., Awaitable[Any]]
    read_level: Callable[[], Any]
    read_recent_storage_event: Callable[[], Any]
    readiness_event_payload: Callable[..., Any]
    require_runtime_plan: Callable[[], Any]
    resolve_correction_readiness_flags: Callable[..., Awaitable[Any]]


class CorrectionFillBoundary:
    def __init__(self, ports: CorrectionFillBoundaryPorts) -> None:
        self._ports = ports

    async def interrupt_for_solution_fill_completion(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        if str(task.current_stage).strip().lower() != "solution_fill_check":
            return None

        recent_storage_event = await self._ports.read_recent_storage_event()(
            task=task,
            event_types=("SOLUTION_FILL_COMPLETED",),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "SOLUTION_FILL_COMPLETED":
            return await self.solution_fill_completion_outcome(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
            )

        runtime = self._ports.require_runtime_plan()(plan=plan)
        # Fail-closed: unavailable/stale max-level must not silently continue dosing.
        # Interrupt (exit correction) only when max is confirmed triggered + consistency OK.
        solution_max = await self._ports.read_level()(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            prefer_probe_snapshot=True,
        )

        if not bool(solution_max.get("is_triggered")):
            return None

        await self._ports.check_sensor_consistency()(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
        )

        readiness = await self._ports.resolve_correction_readiness_flags(
            task=task,
            plan=plan,
            now=now,
            runtime=runtime,
        )
        if readiness is None:
            targets_in_tolerance = False
            workflow_ready = False
        else:
            targets_in_tolerance, workflow_ready = readiness
        next_stage = self.solution_fill_completion_next_stage(
            task=task,
            workflow_ready=workflow_ready,
        )
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_INTERRUPTED_STAGE_COMPLETE",
            task=task,
            corr=corr,
            payload=self._ports.readiness_event_payload(
                targets_in_tolerance=targets_in_tolerance,
                workflow_ready=workflow_ready,
                next_stage=next_stage,
                reason="solution_tank_full",
            ),
        )
        _logger.info(
            "zone %s: solution fill completed during correction; interrupting corr_step=%s -> %s",
            task.zone_id,
            corr.corr_step,
            next_stage,
        )
        return StageOutcome(kind="transition", next_stage=next_stage)

    @staticmethod
    def solution_fill_completion_next_stage(*, task: Any, workflow_ready: bool) -> str:
        if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
            return "solution_fill_stop_to_refill_confirm"
        return "solution_fill_stop_to_ready" if workflow_ready else "solution_fill_stop_to_prepare"

    async def solution_fill_completion_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        readiness = await self._ports.resolve_correction_readiness_flags(task=task, plan=plan, now=now)
        if readiness is None:
            targets_in_tolerance = False
            workflow_ready = False
        else:
            targets_in_tolerance, workflow_ready = readiness
        next_stage = self.solution_fill_completion_next_stage(
            task=task,
            workflow_ready=workflow_ready,
        )
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_INTERRUPTED_STAGE_COMPLETE",
            task=task,
            corr=corr,
            payload=self._ports.readiness_event_payload(
                targets_in_tolerance=targets_in_tolerance,
                workflow_ready=workflow_ready,
                next_stage=next_stage,
                reason="solution_tank_full",
            ),
        )
        _logger.info(
            "zone %s: solution fill completed during correction; interrupting corr_step=%s -> %s",
            task.zone_id,
            corr.corr_step,
            next_stage,
        )
        return StageOutcome(kind="transition", next_stage=next_stage)

    async def interrupt_for_raced_solution_fill_completion(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        exc: TaskExecutionError,
    ) -> StageOutcome | None:
        if exc.code != "irr_state_mismatch":
            return None
        if str(task.current_stage).strip().lower() != "solution_fill_check":
            return None

        raced_completion_event = await self._ports.read_recent_storage_event()(
            task=task,
            event_types=("SOLUTION_FILL_COMPLETED",),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
        )
        raced_event_type = str((raced_completion_event or {}).get("event_type") or "").strip().upper()
        if raced_event_type != "SOLUTION_FILL_COMPLETED":
            return None

        _logger.info(
            "zone %s: corr probe увидел уже выключенный fill-state, но node успела опубликовать completion; corr_step=%s",
            task.zone_id,
            corr.corr_step,
        )
        return await self.solution_fill_completion_outcome(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
        )
