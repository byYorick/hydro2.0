"""automation diagnostics workflow sensors: one cohesive policy."""

from __future__ import annotations

from typing import Any

from ae3lite.application.services.automation_diagnostics_hints import _append_hint
from ae3lite.application.services.automation_diagnostics_values import _HANG_HINT_LABELS


def _append_workflow_sensor_hints(
    *,
    runtime: Any,
    workflow_state: Any,
    workflow_phase: Any,
    task: Any,
    hints: Any,
    cfg: Any,
    telemetry_fetch_ok: Any,
    telemetry: Any,
    current_stage: Any,
    stage_elapsed: Any,
) -> Any:
    wf_age = runtime.get("workflow_snapshot_age_sec")
    # Live topology phases only (irrig_recirc removed with post-irrigation chemistry).
    active_phases = {"tank_filling", "tank_recirc", "irrigating"}
    db_workflow_phase = ""
    if workflow_state is not None:
        db_workflow_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
    stale_phase = db_workflow_phase if db_workflow_phase else workflow_phase
    if (
        isinstance(wf_age, int)
        and wf_age >= cfg["workflow_snapshot_stale_warn_sec"]
        and stale_phase in active_phases
        and runtime.get("task_is_active")
    ):
        _append_hint(
            hints,
            code="workflow_snapshot_stale",
            severity="warning" if wf_age < cfg["workflow_snapshot_stale_critical_sec"] else "critical",
            message=_HANG_HINT_LABELS["workflow_snapshot_stale"],
            details={"workflow_snapshot_age_sec": wf_age, "workflow_phase": workflow_phase},
        )

    if (
        task is None
        and workflow_state is not None
        and stale_phase in active_phases
        and runtime.get("task_status") != "failed"
    ):
        _append_hint(
            hints,
            code="no_active_task_during_workflow",
            severity="warning",
            message=_HANG_HINT_LABELS["no_active_task_during_workflow"],
            details={"workflow_phase": workflow_phase},
        )

    # Level sensors: only for active tasks on relevant check-stages.
    if runtime["task_is_active"] and telemetry_fetch_ok:
        clean_max = bool(telemetry.get("clean_max_triggered"))
        solution_max = bool(telemetry.get("solution_max_triggered"))
        if (
            current_stage in {"clean_fill_check", "clean_fill_start"}
            and not clean_max
            and stage_elapsed >= cfg["level_clean_max_unlatched_sec"]
        ):
            _append_hint(
                hints,
                code="level_clean_max_unlatched",
                severity="warning",
                message=_HANG_HINT_LABELS["level_clean_max_unlatched"],
                details={"clean_max_triggered": clean_max, "current_stage": current_stage},
            )
        if (
            current_stage in {"solution_fill_check"}
            and not solution_max
            and stage_elapsed >= cfg["level_solution_max_unlatched_sec"]
        ):
            _append_hint(
                hints,
                code="level_solution_max_unlatched",
                severity="warning",
                message=_HANG_HINT_LABELS["level_solution_max_unlatched"],
                details={"solution_max_triggered": solution_max, "current_stage": current_stage},
            )
