"""State/workflow runtime helpers for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Iterable, Optional


FetchFn = Callable[..., Awaitable[Any]]
CreateZoneEventFn = Callable[..., Awaitable[Any]]
UtcNowFn = Callable[[], Any]


def normalize_workflow_phase(raw: Any, *, workflow_phase_values: Iterable[str]) -> str:
    value = str(raw or "").strip().lower()
    allowed = set(workflow_phase_values)
    return value if value in allowed else "idle"


def get_zone_state(
    *,
    zone_id: int,
    zone_states: Dict[int, Dict[str, Any]],
    logger: Any,
) -> Dict[str, Any]:
    try:
        from api import get_zone_state_override

        state_override = get_zone_state_override(zone_id)
        if state_override:
            logger.debug(
                "[TEST_HOOK] Using state override for zone %s: %s",
                zone_id,
                state_override,
                extra={"zone_id": zone_id, "state_override": state_override},
            )
            zone_states.setdefault(zone_id, {})
            zone_states[zone_id].update(state_override)
    except ImportError:
        pass
    except Exception as error:
        logger.debug("[TEST_HOOK] Failed to get state override: %s", error)

    zone_states.setdefault(zone_id, {})
    state = zone_states[zone_id]
    state.setdefault("error_streak", 0)
    state.setdefault("next_allowed_run_at", None)
    state.setdefault("last_backoff_reported_until", None)
    # None means "unknown on cold-start", so resolver can perform one probe.
    state.setdefault("backoff_skip_alert_active", None)
    state.setdefault("degraded_alert_active", False)
    state.setdefault("last_missing_targets_report_at", None)
    state.setdefault("last_missing_correction_flags_report_at", None)
    state.setdefault("last_stale_correction_flags_report_at", None)
    # None means "unknown on cold-start", so resolver can perform one probe.
    state.setdefault("correction_missing_flags_active", None)
    state.setdefault("correction_stale_flags_active", None)
    state.setdefault("last_correction_skip_event_at", None)
    state.setdefault("last_correction_skip_reason", None)
    state.setdefault("last_correction_skip_signature", None)
    state.setdefault("suppressed_correction_skip_events", 0)
    state.setdefault("workflow_phase", "idle")
    state.setdefault("workflow_phase_updated_at", None)
    state.setdefault("workflow_phase_source", None)
    state.setdefault("workflow_phase_loaded", False)
    # None means "unknown on cold-start", so resolver can perform one probe.
    state.setdefault("required_nodes_offline_active", None)
    state.setdefault("required_nodes_offline_missing_types", [])
    state.setdefault("required_nodes_offline_required_types", [])
    state.setdefault("required_nodes_offline_since", None)
    state.setdefault("last_required_nodes_offline_report_at", None)
    return state


async def restore_workflow_phase_from_events(
    *,
    zone_id: int,
    fetch_fn: FetchFn,
    workflow_phase_event_type: str,
    normalize_workflow_phase_fn: Callable[[Any], str],
    logger: Any,
) -> str:
    try:
        rows = await fetch_fn(
            """
            SELECT payload_json AS details
            FROM zone_events
            WHERE zone_id = $1
              AND type = $2
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            workflow_phase_event_type,
        )
    except Exception:
        logger.warning(
            "Zone %s: failed to restore workflow_phase from zone_events",
            zone_id,
            exc_info=True,
            extra={"zone_id": zone_id},
        )
        return "idle"

    if not rows:
        return "idle"
    details = rows[0].get("details") if isinstance(rows[0], dict) else None
    if not isinstance(details, dict):
        return "idle"
    return normalize_workflow_phase_fn(details.get("workflow_phase"))


async def get_or_restore_workflow_phase(
    *,
    zone_id: int,
    state: Dict[str, Any],
    restore_workflow_phase_from_events_fn: Callable[[int], Awaitable[str]],
    normalize_workflow_phase_fn: Callable[[Any], str],
    utcnow_fn: UtcNowFn,
    logger: Any,
) -> str:
    if state.get("workflow_phase_loaded") is True:
        cached_phase = normalize_workflow_phase_fn(state.get("workflow_phase"))
        logger.debug(
            "Zone %s: workflow_phase loaded from cache",
            zone_id,
            extra={
                "zone_id": zone_id,
                "workflow_phase": cached_phase,
                "workflow_phase_source": state.get("workflow_phase_source"),
                "workflow_phase_updated_at": (
                    state.get("workflow_phase_updated_at").isoformat()
                    if state.get("workflow_phase_updated_at")
                    else None
                ),
            },
        )
        return cached_phase

    restored_phase = await restore_workflow_phase_from_events_fn(zone_id)
    state["workflow_phase"] = restored_phase
    state["workflow_phase_loaded"] = True
    state["workflow_phase_source"] = "restore"
    state["workflow_phase_updated_at"] = utcnow_fn()
    logger.info(
        "Zone %s: workflow_phase restored from zone_events",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": restored_phase,
            "workflow_phase_source": "restore",
        },
    )
    return restored_phase


def reset_zone_pid_state(
    *,
    zone_id: int,
    ph_controller: Any,
    ec_controller: Any,
    logger: Any,
) -> None:
    had_ph_pid = zone_id in ph_controller._pid_by_zone
    had_ec_pid = zone_id in ec_controller._pid_by_zone
    ph_controller._pid_by_zone.pop(zone_id, None)
    ec_controller._pid_by_zone.pop(zone_id, None)
    ph_controller._last_pid_tick.pop(zone_id, None)
    ec_controller._last_pid_tick.pop(zone_id, None)
    logger.info(
        "Zone %s: reset PID state on workflow transition",
        zone_id,
        extra={
            "zone_id": zone_id,
            "had_ph_pid": had_ph_pid,
            "had_ec_pid": had_ec_pid,
        },
    )


def sync_sensor_mode_cache_with_workflow_phase(
    *,
    zone_id: int,
    previous_phase: str,
    normalized_phase: str,
    correction_sensor_mode_state: Dict[int, bool],
    workflow_sensor_mode_external_phases: Iterable[str],
    logger: Any,
) -> None:
    if normalized_phase == previous_phase:
        return
    external_phases = set(workflow_sensor_mode_external_phases)
    if normalized_phase not in external_phases:
        return
    previous_sensor_mode = correction_sensor_mode_state.pop(zone_id, None)
    logger.info(
        "Zone %s: reset correction sensor-mode cache on workflow transition",
        zone_id,
        extra={
            "zone_id": zone_id,
            "previous_workflow_phase": previous_phase,
            "workflow_phase": normalized_phase,
            "previous_sensor_mode_state": previous_sensor_mode,
            "external_sensor_mode_phases": sorted(external_phases),
        },
    )


async def update_workflow_phase(
    *,
    zone_id: int,
    workflow_phase: str,
    workflow_stage: Optional[str],
    source: str,
    reason_code: Optional[str],
    force_event: bool,
    state: Dict[str, Any],
    normalize_workflow_phase_fn: Callable[[Any], str],
    utcnow_fn: UtcNowFn,
    reset_zone_pid_state_fn: Callable[[int], None],
    sync_sensor_mode_cache_with_workflow_phase_fn: Callable[[int, str, str], None],
    create_zone_event_fn: CreateZoneEventFn,
    workflow_phase_event_type: str,
    logger: Any,
) -> str:
    previous_phase = normalize_workflow_phase_fn(state.get("workflow_phase"))
    normalized_phase = normalize_workflow_phase_fn(workflow_phase)
    changed = previous_phase != normalized_phase

    state["workflow_phase"] = normalized_phase
    state["workflow_phase_loaded"] = True
    state["workflow_phase_source"] = str(source or "scheduler")
    state["workflow_phase_updated_at"] = utcnow_fn()

    if normalized_phase == "irrigating" and previous_phase in {"tank_recirc", "ready"}:
        reset_zone_pid_state_fn(zone_id)

    sync_sensor_mode_cache_with_workflow_phase_fn(
        zone_id=zone_id,
        previous_phase=previous_phase,
        normalized_phase=normalized_phase,
    )

    logger.info(
        "Zone %s: workflow_phase update processed",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": normalized_phase,
            "previous_workflow_phase": previous_phase,
            "changed": changed,
            "workflow_stage": workflow_stage,
            "source": source,
            "reason_code": reason_code,
            "force_event": force_event,
        },
    )

    if changed or force_event:
        await create_zone_event_fn(
            zone_id,
            workflow_phase_event_type,
            {
                "workflow_phase": normalized_phase,
                "previous_workflow_phase": previous_phase,
                "workflow_stage": workflow_stage,
                "source": source,
                "reason_code": reason_code,
            },
        )
    return normalized_phase


def resolve_allowed_ec_components(
    *,
    workflow_phase: str,
    normalize_workflow_phase_fn: Callable[[Any], str],
    workflow_ec_components_by_phase: Dict[str, list[str]],
) -> Optional[list[str]]:
    normalized_phase = normalize_workflow_phase_fn(workflow_phase)
    components = workflow_ec_components_by_phase.get(normalized_phase)
    if components is None:
        return None
    return list(components)


__all__ = [
    "get_or_restore_workflow_phase",
    "get_zone_state",
    "normalize_workflow_phase",
    "reset_zone_pid_state",
    "resolve_allowed_ec_components",
    "restore_workflow_phase_from_events",
    "sync_sensor_mode_cache_with_workflow_phase",
    "update_workflow_phase",
]
