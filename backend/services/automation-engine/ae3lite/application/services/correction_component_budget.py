"""Irrigation component budget boundary before dose planning."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_pipeline import (
    irrigation_component_budget_guard,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.hydraulics.failure_report import note_upward_report


async def apply_component_budget(
    *,
    task: Any,
    corr: CorrectionState,
    current_ph: float,
    current_ec: float,
    target_ph: float,
    target_ec: float,
    runtime: Any,
    correction_cfg: Mapping[str, Any],
    current_stage: str,
    planner: Any,
    log_event: Callable[..., Awaitable[Any]],
) -> float | StageOutcome:
    pipeline_phase = str(getattr(corr, "pipeline_phase", None) or "").strip().lower()
    if pipeline_phase in {"irrigation_calcium", "irrigation_npk"}:
        full_target_ec = float(target_ec)
        resolved_deadbands = planner.resolve_deadbands(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
        )
        component_budget = irrigation_component_budget_guard(
            corr=corr,
            current_ec=current_ec,
            full_target_ec=full_target_ec,
            ec_deadband=float(resolved_deadbands["ec"]),
        )
    else:
        resolved_deadbands = {}
        component_budget = {"allowed": True}
    if not bool(component_budget.get("allowed", True)):
        await log_event(
            zone_id=task.zone_id,
            event_type="IRRIGATION_EC_COMPONENT_BUDGET_EXHAUSTED",
            task=task,
            corr=corr,
            payload={
                **dict(component_budget),
                "current_ec": current_ec,
                "full_target_ec": full_target_ec,
                "ec_deadband": float(resolved_deadbands["ec"]),
            },
        )
        await note_upward_report(
            code="biz_ae3_irrigation_ec_component_budget_exhausted",
            message="EC top-up остановлен пределом выбранного nutrient component",
            severity="warning",
            zone_id=int(task.zone_id),
            alert_type="automation",
            dedupe_key=f"ae3:component-budget:{int(task.id)}:{component_budget.get('component')}",
            details={
                "task_id": int(task.id),
                "stage": current_stage,
                **dict(component_budget),
                "current_ec": current_ec,
                "ec_deadband": float(resolved_deadbands["ec"]),
            },
            scope_parts=(str(int(task.id)), str(component_budget.get("component") or "unknown")),
        )
        ph_only_corr = replace(
            corr,
            pipeline_phase="irrigation_ph",
            active_component="ph",
            ec_pid_frozen=True,
            corr_step="corr_check",
            needs_ec=False,
            ec_duration_ms=None,
            wait_until=None,
        )
        return StageOutcome(
            kind="enter_correction",
            correction=ph_only_corr,
            due_delay_sec=0,
        )
    if pipeline_phase in {"irrigation_calcium", "irrigation_npk"}:
        target_ec = float(component_budget["effective_target_ec"])
    return target_ec
