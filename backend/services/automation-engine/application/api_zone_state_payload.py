"""Zone automation-state payload assembler for API decomposition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict


async def build_zone_automation_state_payload(
    zone_id: int,
    *,
    load_latest_zone_task_fn: Callable[[int], Awaitable[Any]],
    derive_automation_state_fn: Callable[[Any], str],
    resolve_state_started_at_fn: Callable[[Any, str], Any],
    estimate_progress_percent_fn: Callable[[Any, str], int],
    load_zone_system_config_fn: Callable[[int, Dict[str, Any]], Awaitable[Dict[str, Any]]],
    load_zone_current_levels_fn: Callable[[int], Awaitable[Dict[str, Any]]],
    derive_active_processes_fn: Callable[[Any, str], Dict[str, bool]],
    load_automation_timeline_fn: Callable[[int], Awaitable[list[Dict[str, Any]]]],
    estimate_completion_seconds_fn: Callable[[Any], Any],
    automation_state_labels: Dict[str, str],
    automation_state_idle: str,
    automation_state_next: Dict[str, Any],
) -> Dict[str, Any]:
    task = await load_latest_zone_task_fn(zone_id)
    payload = task.get("payload") if isinstance(task, dict) and isinstance(task.get("payload"), dict) else {}
    state = derive_automation_state_fn(task)
    state_started_at = resolve_state_started_at_fn(task, state)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed_sec = int((now - state_started_at).total_seconds()) if state_started_at is not None else 0
    progress_percent = estimate_progress_percent_fn(task, state)

    system_config = await load_zone_system_config_fn(zone_id, payload)
    current_levels = await load_zone_current_levels_fn(zone_id)
    active_processes = derive_active_processes_fn(task, state)
    timeline = await load_automation_timeline_fn(zone_id)
    estimated_completion_sec = estimate_completion_seconds_fn(task)

    return {
        "zone_id": zone_id,
        "state": state,
        "state_label": automation_state_labels.get(state, automation_state_labels[automation_state_idle]),
        "state_details": {
            "started_at": state_started_at.isoformat() if state_started_at is not None else None,
            "elapsed_sec": elapsed_sec,
            "progress_percent": progress_percent,
        },
        "system_config": {
            "tanks_count": int(system_config.get("tanks_count") or 2),
            "system_type": str(system_config.get("system_type") or "drip"),
            "clean_tank_capacity_l": system_config.get("clean_tank_capacity_l"),
            "nutrient_tank_capacity_l": system_config.get("nutrient_tank_capacity_l"),
        },
        "current_levels": current_levels,
        "active_processes": active_processes,
        "timeline": timeline,
        "next_state": automation_state_next.get(state),
        "estimated_completion_sec": estimated_completion_sec,
    }


__all__ = ["build_zone_automation_state_payload"]
