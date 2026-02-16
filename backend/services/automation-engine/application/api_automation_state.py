"""Automation state/timeline helpers for API layer decomposition."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional


def derive_automation_state(
    task: Optional[Dict[str, Any]],
    *,
    extract_workflow: Callable[[Dict[str, Any]], str],
    state_idle: str,
    state_tank_filling: str,
    state_tank_recirc: str,
    state_ready: str,
    state_irrigating: str,
    state_irrig_recirc: str,
) -> str:
    if not task:
        return state_idle

    status = str(task.get("status") or "").strip().lower()
    task_type = str(task.get("task_type") or "").strip().lower()
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}

    workflow = extract_workflow(payload)
    mode = str(result.get("mode") or "").strip().lower()
    reason_code = str(result.get("reason_code") or "").strip().lower()

    if status in {"accepted", "running"}:
        if task_type == "irrigation":
            if "recovery" in workflow or "recovery" in mode:
                return state_irrig_recirc
            return state_irrigating
        if task_type == "diagnostics":
            if workflow in {"prepare_recirculation", "prepare_recirculation_check"}:
                return state_tank_recirc
            if workflow in {"irrigation_recovery", "irrigation_recovery_check"}:
                return state_irrig_recirc
            return state_tank_filling

    if status == "completed":
        if task_type == "diagnostics":
            if mode in {"two_tank_startup_completed", "two_tank_prepare_recirculation_completed"}:
                return state_ready
            if reason_code in {"prepare_targets_reached", "solution_fill_completed"}:
                return state_ready
        if task_type == "irrigation":
            return state_ready

    return state_idle


def resolve_state_started_at(
    task: Optional[Dict[str, Any]],
    state: str,
    *,
    coerce_datetime: Callable[[Any], Optional[datetime]],
    state_tank_filling: str,
    state_tank_recirc: str,
    state_irrig_recirc: str,
    state_irrigating: str,
) -> Optional[datetime]:
    if not task:
        return None
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}

    candidate_keys = []
    if state == state_tank_filling:
        candidate_keys = ["clean_fill_started_at", "solution_fill_started_at", "started_at"]
    elif state == state_tank_recirc:
        candidate_keys = ["prepare_recirculation_started_at", "started_at"]
    elif state == state_irrig_recirc:
        candidate_keys = ["irrigation_recovery_started_at", "started_at"]
    elif state == state_irrigating:
        candidate_keys = ["started_at"]

    for key in candidate_keys:
        parsed = coerce_datetime(payload.get(key))
        if parsed is not None:
            return parsed
        parsed = coerce_datetime(result.get(key))
        if parsed is not None:
            return parsed

    return coerce_datetime(task.get("created_at")) or coerce_datetime(task.get("updated_at"))


def estimate_progress_percent(
    task: Optional[Dict[str, Any]],
    state: str,
    *,
    extract_workflow: Callable[[Dict[str, Any]], str],
    to_optional_int: Callable[[Any], Optional[int]],
    state_idle: str,
    state_ready: str,
    state_tank_filling: str,
    state_tank_recirc: str,
    state_irrigating: str,
    state_irrig_recirc: str,
) -> int:
    if state == state_idle:
        return 0
    if state == state_ready:
        return 100

    payload = task.get("payload") if isinstance(task, dict) and isinstance(task.get("payload"), dict) else {}
    result = task.get("result") if isinstance(task, dict) and isinstance(task.get("result"), dict) else {}
    explicit_progress = to_optional_int(result.get("progress_percent"))
    if explicit_progress is None:
        explicit_progress = to_optional_int(payload.get("progress_percent"))
    if explicit_progress is not None:
        return max(0, min(100, explicit_progress))

    workflow = extract_workflow(payload)
    if state == state_tank_filling:
        if workflow == "clean_fill_check":
            return 30
        if workflow == "solution_fill_check":
            return 60
        return 20
    if state == state_tank_recirc:
        return 80
    if state == state_irrigating:
        return 55
    if state == state_irrig_recirc:
        return 75
    return 0


def estimate_completion_seconds(
    task: Optional[Dict[str, Any]],
    *,
    now: datetime,
    coerce_datetime: Callable[[Any], Optional[datetime]],
) -> Optional[int]:
    if not task:
        return None

    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}

    candidates = [
        payload.get("clean_fill_timeout_at"),
        payload.get("solution_fill_timeout_at"),
        payload.get("prepare_recirculation_timeout_at"),
        payload.get("irrigation_recovery_timeout_at"),
        result.get("next_due_at"),
    ]
    for candidate in candidates:
        parsed = coerce_datetime(candidate)
        if parsed is None:
            continue
        delta = int((parsed - now).total_seconds())
        if delta > 0:
            return delta

    due_at = coerce_datetime(task.get("due_at"))
    if due_at is not None:
        delta = int((due_at - now).total_seconds())
        if delta > 0:
            return delta
    return None


def derive_active_processes(
    task: Optional[Dict[str, Any]],
    state: str,
    *,
    extract_workflow: Callable[[Dict[str, Any]], str],
    state_tank_filling: str,
    state_tank_recirc: str,
    state_irrigating: str,
    state_irrig_recirc: str,
) -> Dict[str, bool]:
    payload = task.get("payload") if isinstance(task, dict) and isinstance(task.get("payload"), dict) else {}
    workflow = extract_workflow(payload)

    pump_in = state in {state_tank_filling, state_irrigating}
    circulation = state in {state_tank_recirc, state_irrig_recirc}

    if workflow in {"prepare_recirculation", "prepare_recirculation_check", "irrigation_recovery", "irrigation_recovery_check"}:
        circulation = True
        pump_in = False
    if workflow in {"startup", "clean_fill_check", "solution_fill_check"}:
        pump_in = True

    ph_correction = state in {state_tank_filling, state_tank_recirc, state_irrig_recirc}
    ec_correction = state in {state_tank_filling, state_tank_recirc}

    return {
        "pump_in": pump_in,
        "circulation_pump": circulation,
        "ph_correction": ph_correction,
        "ec_correction": ec_correction,
    }


def extract_timeline_reason(payload: Dict[str, Any]) -> Optional[str]:
    reason_code = payload.get("reason_code")
    if isinstance(reason_code, str) and reason_code.strip():
        return reason_code.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        nested_reason_code = result.get("reason_code")
        if isinstance(nested_reason_code, str) and nested_reason_code.strip():
            return nested_reason_code.strip()
    return None


def build_timeline_label(
    event_type: str,
    reason_code: Optional[str],
    *,
    event_labels: Dict[str, str],
) -> str:
    base = event_labels.get(event_type, event_type)
    if isinstance(reason_code, str) and reason_code:
        return f"{base} ({reason_code})"
    return base


__all__ = [
    "build_timeline_label",
    "derive_active_processes",
    "derive_automation_state",
    "estimate_completion_seconds",
    "estimate_progress_percent",
    "extract_timeline_reason",
    "resolve_state_started_at",
]
