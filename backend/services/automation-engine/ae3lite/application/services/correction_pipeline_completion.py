"""Advance nutrient pipeline and finalize successful correction."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_pipeline import (
    maybe_advance_pipeline,
)
from ae3lite.domain.entities.workflow_state import CorrectionState


async def complete_pipeline_step(
    *,
    task: Any,
    corr: CorrectionState,
    current_ph: float,
    current_ec: float,
    target_ph: float,
    target_ec: float,
    now: datetime,
    current_stage: str,
    workflow_ready: bool,
    log_event: Callable[..., Awaitable[Any]],
    reset_ec_pid: Callable[..., Awaitable[Any]],
    pid_state_service: Any,
    transition: Callable[..., StageOutcome],
) -> StageOutcome:
    next_corr, finished, advance_payload = maybe_advance_pipeline(
        corr=corr,
        current_stage=current_stage,
    )
    if advance_payload:
        await log_event(
            zone_id=task.zone_id,
            event_type="PIPELINE_STEP_CHANGED",
            task=task,
            corr=next_corr,
            payload=advance_payload,
        )
    if advance_payload and advance_payload.get("reset_ec_pid"):
        await reset_ec_pid(
            task=task,
            corr=next_corr,
            reason="component_switch",
            now=now,
        )
        # Mid-pipeline component switch: stale no_effect_count from the
        # previous EC component must not block the next one.
        await pid_state_service.reset_no_effect_counts(
            task=task,
            corr=next_corr,
            context="PIPELINE_COMPONENT_SWITCH",
        )
    if not finished:
        return StageOutcome(
            kind="enter_correction",
            correction=next_corr,
            due_delay_sec=0,
        )
    await log_event(
        zone_id=task.zone_id,
        event_type="CORRECTION_COMPLETE",
        task=task,
        corr=next_corr,
        payload={
            "current_ph": current_ph,
            "current_ec": current_ec,
            "target_ph": target_ph,
            "target_ec": target_ec,
            "pipeline_phase": getattr(next_corr, "pipeline_phase", None),
            "targets_in_tolerance": True,
            "workflow_ready": workflow_ready,
        },
    )
    await pid_state_service.reset_no_effect_counts(
        task=task,
        corr=next_corr,
        context="CORRECTION_COMPLETE",
    )
    return transition(corr=next_corr, success=True)
