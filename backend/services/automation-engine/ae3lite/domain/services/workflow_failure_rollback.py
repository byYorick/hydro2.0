"""Откат workflow_phase после terminal failure AE3 task."""

from __future__ import annotations

from typing import Any

_SCHEDULABLE_PHASES = frozenset({"ready", "irrig_recirc"})
_ACTIVE_WORKFLOW_PHASES = frozenset({"tank_filling", "tank_recirc", "irrigating", "irrig_recirc"})


def resolve_workflow_phase_after_task_failure(task: Any) -> str:
    """Возвращает целевую workflow_phase после fail-closed task."""
    task_type = str(getattr(task, "task_type", "") or "").strip().lower()
    workflow_phase = str(getattr(task, "workflow_phase", "") or "").strip().lower()

    if task_type == "irrigation_start":
        return "ready"

    if task_type == "lighting_tick":
        if workflow_phase in _SCHEDULABLE_PHASES:
            return workflow_phase
        return "ready"

    if workflow_phase in {"irrigating", "irrig_recirc"}:
        return "ready"

    if workflow_phase in _SCHEDULABLE_PHASES:
        return workflow_phase

    return "idle"


def is_active_workflow_phase(workflow_phase: str | None) -> bool:
    normalized = str(workflow_phase or "").strip().lower()
    return normalized in _ACTIVE_WORKFLOW_PHASES


def resolve_workflow_rollback_phase_for_stale_state(*, workflow_phase: str | None) -> str | None:
    """Laravel watchdog: откат zombie workflow без active ae_task."""
    normalized = str(workflow_phase or "").strip().lower()
    if normalized not in _ACTIVE_WORKFLOW_PHASES:
        return None
    if normalized in {"irrigating", "irrig_recirc"}:
        return "ready"
    return "idle"


__all__ = [
    "is_active_workflow_phase",
    "resolve_workflow_phase_after_task_failure",
    "resolve_workflow_rollback_phase_for_stale_state",
]
