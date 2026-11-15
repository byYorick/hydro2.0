"""automation diagnostics timing: one cohesive policy."""

from __future__ import annotations

from typing import Any

from ae3lite.application.services.automation_diagnostics_hints import _append_hint, _severity_for_elapsed
from ae3lite.application.services.automation_diagnostics_values import _DISPATCH_STUCK_STATUSES, _HANG_HINT_LABELS
from common.observability_thresholds import (
    should_skip_correction_substep_stalled_hint,
    should_skip_stage_elapsed_long_hint,
    stage_threshold_pair,
)


def _append_task_timing_hints(*, runtime: Any, cfg: Any, hints: Any, status: Any) -> Any:
    current_stage = str(runtime.get("current_stage") or "").strip().lower()
    stage_elapsed = int(runtime.get("stage_elapsed_sec") or 0)
    workflow_phase = str(runtime.get("workflow_phase") or "").strip().lower()
    task_updated_age = runtime.get("task_updated_age_sec")
    waiting_elapsed = stage_elapsed
    if runtime["waiting_command"] and isinstance(task_updated_age, int):
        waiting_elapsed = task_updated_age
    runtime["waiting_elapsed_sec"] = waiting_elapsed

    if runtime["waiting_command"]:
        severity = _severity_for_elapsed(
            waiting_elapsed,
            cfg["waiting_command_warn_sec"],
            cfg["waiting_command_critical_sec"],
        )
        if severity is not None:
            _append_hint(
                hints,
                code="waiting_command_stuck",
                severity=severity,
                message=_HANG_HINT_LABELS["waiting_command_stuck"],
                details={
                    "waiting_elapsed_sec": waiting_elapsed,
                    "stage_elapsed_sec": stage_elapsed,
                    "task_status": status,
                },
            )

    if status in _DISPATCH_STUCK_STATUSES and isinstance(task_updated_age, int):
        severity = _severity_for_elapsed(
            task_updated_age,
            cfg["task_dispatch_warn_sec"],
            cfg["task_dispatch_critical_sec"],
        )
        if severity is not None:
            _append_hint(
                hints,
                code="task_dispatch_stuck",
                severity=severity,
                message=_HANG_HINT_LABELS["task_dispatch_stuck"],
                details={"task_status": status, "task_updated_age_sec": task_updated_age},
            )

    stage_deadline_remaining = runtime.get("stage_deadline_remaining_sec")
    if isinstance(stage_deadline_remaining, int) and stage_deadline_remaining < 0 and runtime["task_is_active"]:
        _append_hint(
            hints,
            code="stage_deadline_exceeded",
            severity="critical",
            message=_HANG_HINT_LABELS["stage_deadline_exceeded"],
            details={
                "overdue_sec": abs(stage_deadline_remaining),
                "current_stage": current_stage or None,
            },
        )

    stage_pair = stage_threshold_pair(cfg, current_stage)
    deadline_remaining = runtime.get("stage_deadline_remaining_sec")
    skip_elapsed_long = should_skip_stage_elapsed_long_hint(
        stage=current_stage,
        stage_deadline_remaining_sec=deadline_remaining if isinstance(deadline_remaining, int) else None,
    )
    if stage_pair is not None and runtime["task_is_active"] and not skip_elapsed_long:
        severity = _severity_for_elapsed(stage_elapsed, stage_pair[0], stage_pair[1])
        if severity is not None:
            _append_hint(
                hints,
                code="stage_elapsed_long",
                severity=severity,
                message=f"{_HANG_HINT_LABELS['stage_elapsed_long']}: {current_stage}",
                details={"stage_elapsed_sec": stage_elapsed, "current_stage": current_stage},
            )

    corr_step = str(runtime.get("correction_step") or "").strip().lower()
    if corr_step.startswith("corr_wait") and runtime["task_is_active"]:
        wait_remaining = runtime.get("correction_wait_remaining_sec")
        wait_remaining_int = wait_remaining if isinstance(wait_remaining, int) else None
        substep_elapsed = task_updated_age if isinstance(task_updated_age, int) else stage_elapsed
        skip_correction_stall = should_skip_correction_substep_stalled_hint(
            correction_step=corr_step,
            correction_wait_remaining_sec=wait_remaining_int,
            substep_elapsed_sec=substep_elapsed,
            stabilization_sec=runtime.get("correction_stabilization_sec")
            if isinstance(runtime.get("correction_stabilization_sec"), int)
            else None,
        )
        if not skip_correction_stall and substep_elapsed >= cfg["correction_substep_warn_sec"]:
            _append_hint(
                hints,
                code="correction_substep_stalled",
                severity="warning" if substep_elapsed < cfg["correction_substep_critical_sec"] else "critical",
                message=f"{_HANG_HINT_LABELS['correction_substep_stalled']} ({corr_step})",
                details={
                    "correction_step": corr_step,
                    "substep_elapsed_sec": substep_elapsed,
                    "stage_elapsed_sec": stage_elapsed,
                    "correction_wait_remaining_sec": wait_remaining_int,
                },
            )
    return current_stage, stage_elapsed, workflow_phase
