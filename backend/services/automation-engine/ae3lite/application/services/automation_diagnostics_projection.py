"""automation diagnostics projection: one cohesive policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.application.services.automation_diagnostics_values import _ACTIVE_TASK_STATUSES
from ae3lite.domain.services.workflow_failure_rollback import resolve_diagnostic_stage_after_rollback


def _build_runtime_view(*, zone_id: Any, task: Any, workflow_state: Any, now: Any) -> Any:
    runtime: dict[str, Any] = {
        "zone_id": zone_id,
        "task_id": None,
        "task_status": None,
        "task_is_active": False,
        "current_stage": None,
        "workflow_phase": None,
        "stage_entered_at": None,
        "stage_elapsed_sec": 0,
        "stage_deadline_at": None,
        "stage_deadline_remaining_sec": None,
        "waiting_command": False,
        "correction_step": None,
        "pending_manual_step": None,
        "topology": None,
        "workflow_snapshot_updated_at": None,
        "workflow_snapshot_age_sec": None,
        "waiting_elapsed_sec": 0,
        "task_updated_age_sec": None,
    }

    status = ""
    wf = None
    task_updated_at: datetime | None = None
    if task is not None:
        status = str(getattr(task, "status", "") or "").strip().lower()
        wf = getattr(task, "workflow", None)
        runtime["task_id"] = getattr(task, "id", None)
        runtime["task_status"] = status or None
        runtime["task_is_active"] = status in _ACTIVE_TASK_STATUSES
        runtime["topology"] = getattr(task, "topology", None)
        runtime["current_stage"] = getattr(wf, "current_stage", None) if wf is not None else None
        runtime["workflow_phase"] = getattr(wf, "workflow_phase", None) if wf is not None else None
        runtime["pending_manual_step"] = getattr(wf, "pending_manual_step", None) if wf is not None else None

        stage_entered_at = _normalize_utc_naive(getattr(wf, "stage_entered_at", None) if wf is not None else None)
        runtime["stage_entered_at"] = _iso_or_none(stage_entered_at)
        if stage_entered_at is not None:
            if status == "failed":
                completed_at = _normalize_utc_naive(getattr(task, "completed_at", None))
                end_at = completed_at if completed_at is not None else now
                runtime["stage_elapsed_sec"] = max(0, int((end_at - stage_entered_at).total_seconds()))
            else:
                runtime["stage_elapsed_sec"] = max(0, int((now - stage_entered_at).total_seconds()))

        stage_deadline_at = _normalize_utc_naive(getattr(wf, "stage_deadline_at", None) if wf is not None else None)
        runtime["stage_deadline_at"] = _iso_or_none(stage_deadline_at)
        if stage_deadline_at is not None and status != "failed":
            runtime["stage_deadline_remaining_sec"] = int((stage_deadline_at - now).total_seconds())

        runtime["waiting_command"] = status == "waiting_command"

        task_updated_at = _normalize_utc_naive(getattr(task, "updated_at", None))
        if task_updated_at is not None:
            runtime["task_updated_age_sec"] = max(0, int((now - task_updated_at).total_seconds()))

        correction = getattr(task, "correction", None)
        if correction is not None and status in _ACTIVE_TASK_STATUSES:
            runtime["correction_step"] = str(getattr(correction, "corr_step", "") or "").strip() or None
            wait_until = _normalize_utc_naive(getattr(correction, "wait_until", None))
            runtime["correction_wait_until"] = _iso_or_none(wait_until)
            if wait_until is not None:
                runtime["correction_wait_remaining_sec"] = int((wait_until - now).total_seconds())
            stabilization_sec = getattr(correction, "stabilization_sec", None)
            if stabilization_sec is not None:
                try:
                    runtime["correction_stabilization_sec"] = int(stabilization_sec)
                except (TypeError, ValueError):
                    pass

    if workflow_state is not None:
        wf_updated = _normalize_utc_naive(getattr(workflow_state, "updated_at", None))
        runtime["workflow_snapshot_updated_at"] = _iso_or_none(wf_updated)
        if wf_updated is not None:
            runtime["workflow_snapshot_age_sec"] = max(0, int((now - wf_updated).total_seconds()))
        if runtime.get("workflow_phase") in (None, "", "idle"):
            wf_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
            if wf_phase:
                runtime["workflow_phase"] = wf_phase
        if not runtime.get("current_stage"):
            payload = getattr(workflow_state, "payload", None)
            if isinstance(payload, Mapping):
                stage_from_payload = str(payload.get("ae3_cycle_start_stage") or "").strip()
                wf_phase = str(getattr(workflow_state, "workflow_phase", "") or "").strip().lower()
                display_stage = resolve_diagnostic_stage_after_rollback(
                    workflow_phase=wf_phase,
                    payload=payload,
                    raw_stage=stage_from_payload or None,
                )
                if display_stage:
                    runtime["current_stage"] = display_stage
    return runtime, status


def _normalize_utc_naive(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None
