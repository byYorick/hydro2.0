"""Откат workflow_phase после terminal failure AE3 task."""

from __future__ import annotations

from typing import Any, Mapping

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

    if task_type == "solution_topup":
        return "ready"

    if task_type == "solution_change":
        return "idle"

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


def resolve_diagnostic_stage_after_rollback(
    *,
    workflow_phase: str | None,
    payload: Any,
    raw_stage: str | None,
) -> str | None:
    """После failure rollback payload хранит этап сбоя; для UI показываем macro ready."""
    stage = str(raw_stage or "").strip() or None
    wf = str(workflow_phase or "").strip().lower()
    normalized_payload = payload if isinstance(payload, Mapping) else {}
    if bool(normalized_payload.get("ae3_failure_rollback")):
        if wf in {"ready", "irrig_recirc"}:
            return "complete_ready"
        if wf == "idle":
            return None
    return stage


__all__ = [
    "is_active_workflow_phase",
    "resolve_diagnostic_stage_after_rollback",
    "resolve_workflow_phase_after_task_failure",
    "resolve_workflow_rollback_phase_for_stale_state",
]
