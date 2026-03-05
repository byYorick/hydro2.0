"""Zone automation-state payload assembler for API decomposition."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

_IRR_STATE_STALE_SECONDS = 120
_IRR_ACTUATOR_FIELDS = (
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
    "pump_main",
)


def _coerce_utc_datetime(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value
        return raw_value.astimezone(timezone.utc).replace(tzinfo=None)
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _sanitize_stale_irr_state_for_idle(
    *,
    state: str,
    idle_state: str,
    irr_node_state: Dict[str, Any] | None,
    now_utc: datetime,
) -> Dict[str, Any] | None:
    if state != idle_state or not isinstance(irr_node_state, dict):
        return irr_node_state
    updated_at = _coerce_utc_datetime(irr_node_state.get("updated_at"))
    if updated_at is None:
        return irr_node_state
    age_seconds = (now_utc - updated_at).total_seconds()
    if age_seconds <= float(_IRR_STATE_STALE_SECONDS):
        return irr_node_state

    sanitized = dict(irr_node_state)
    for field in _IRR_ACTUATOR_FIELDS:
        sanitized[field] = False
    sanitized["stale"] = True
    sanitized["stale_age_sec"] = round(age_seconds, 3)
    return sanitized


def _sync_active_processes_with_irr_state(
    *,
    active_processes: Dict[str, bool],
    irr_node_state: Dict[str, Any] | None,
) -> Dict[str, bool]:
    result = {
        "pump_in": bool(active_processes.get("pump_in")),
        "circulation_pump": bool(active_processes.get("circulation_pump")),
        "ph_correction": bool(active_processes.get("ph_correction")),
        "ec_correction": bool(active_processes.get("ec_correction")),
    }
    if not isinstance(irr_node_state, dict):
        return result

    pump_main = irr_node_state.get("pump_main")
    if pump_main is False:
        result["pump_in"] = False
        result["circulation_pump"] = False
        return result
    if pump_main is not True:
        return result

    valve_clean_fill = irr_node_state.get("valve_clean_fill")
    valve_irrigation = irr_node_state.get("valve_irrigation")
    valve_solution_fill = irr_node_state.get("valve_solution_fill")
    valve_solution_supply = irr_node_state.get("valve_solution_supply")

    if isinstance(valve_clean_fill, bool) or isinstance(valve_irrigation, bool):
        result["pump_in"] = bool(valve_clean_fill) or bool(valve_irrigation)

    if isinstance(valve_solution_fill, bool) and isinstance(valve_solution_supply, bool):
        is_irrigation_path = bool(valve_irrigation) if isinstance(valve_irrigation, bool) else False
        result["circulation_pump"] = bool(valve_solution_fill and valve_solution_supply and not is_irrigation_path)
    else:
        result["circulation_pump"] = True
    return result


async def build_zone_automation_state_payload(
    zone_id: int,
    *,
    load_latest_zone_task_fn: Callable[[int], Awaitable[Any]],
    derive_automation_state_fn: Callable[[Any], str],
    resolve_state_started_at_fn: Callable[[Any, str], Any],
    estimate_progress_percent_fn: Callable[[Any, str], int],
    load_zone_system_config_fn: Callable[[int, Dict[str, Any]], Awaitable[Dict[str, Any]]],
    load_zone_current_levels_fn: Callable[[int], Awaitable[Dict[str, Any]]],
    load_latest_irr_node_state_fn: Callable[[int], Awaitable[Dict[str, Any] | None]],
    derive_active_processes_fn: Callable[[Any, str], Dict[str, bool]],
    load_automation_timeline_fn: Callable[[int], Awaitable[list[Dict[str, Any]]]],
    estimate_completion_seconds_fn: Callable[[Any], Any],
    derive_failed_state_fn: Callable[[Any], bool],
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
    failed = derive_failed_state_fn(task)

    system_config = await load_zone_system_config_fn(zone_id, payload)
    current_levels = await load_zone_current_levels_fn(zone_id)
    irr_node_state = await load_latest_irr_node_state_fn(zone_id)
    irr_node_state = _sanitize_stale_irr_state_for_idle(
        state=state,
        idle_state=automation_state_idle,
        irr_node_state=irr_node_state,
        now_utc=now,
    )
    active_processes = _sync_active_processes_with_irr_state(
        active_processes=derive_active_processes_fn(task, state),
        irr_node_state=irr_node_state,
    )
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
            "failed": failed,
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
        "irr_node_state": irr_node_state,
    }


__all__ = ["build_zone_automation_state_payload"]
