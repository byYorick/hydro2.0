"""Controller execution helpers for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from infrastructure.circuit_breaker import CircuitBreakerOpenError


RecordSimulationEventFn = Callable[..., Awaitable[Any]]
EmitControllerCircuitOpenSignalFn = Callable[..., Awaitable[None]]
CreateZoneEventSafeFn = Callable[..., Awaitable[bool]]


async def check_phase_transitions(
    *,
    zone_id: int,
    sim_clock: Optional[Any],
    grow_cycle_repo: Any,
    record_simulation_event_fn: RecordSimulationEventFn,
    emit_controller_circuit_open_signal_fn: EmitControllerCircuitOpenSignalFn,
    logger: Any,
) -> None:
    if not sim_clock:
        return
    if sim_clock.mode == "live":
        return

    phase_info = await grow_cycle_repo.get_current_phase_timing(zone_id)
    if not phase_info:
        return

    duration_hours = phase_info.get("duration_hours")
    duration_days = phase_info.get("duration_days")
    if duration_hours is None and duration_days is None:
        return

    duration_hours_value = float(duration_hours) if duration_hours is not None else float(duration_days) * 24.0
    if duration_hours_value <= 0:
        return

    phase_started_at = phase_info.get("phase_started_at") or phase_info.get("recipe_started_at")
    if not phase_started_at:
        return

    sim_now = sim_clock.now()
    phase_start_sim = sim_clock.to_sim_time(phase_started_at)
    if sim_now < phase_start_sim:
        return

    elapsed_hours = (sim_now - phase_start_sim).total_seconds() / 3600.0
    if elapsed_hours < duration_hours_value:
        return

    grow_cycle_id = phase_info.get("grow_cycle_id")
    if not grow_cycle_id:
        return

    phase_index = phase_info.get("phase_index")
    max_phase_index = phase_info.get("max_phase_index")

    try:
        if max_phase_index is not None and phase_index is not None and phase_index >= max_phase_index:
            success = await grow_cycle_repo.harvest_cycle(int(grow_cycle_id))
            if success:
                await record_simulation_event_fn(
                    zone_id=zone_id,
                    service="automation-engine",
                    stage="phase_transition",
                    status="harvested",
                    message="Simulation cycle harvested",
                    payload={
                        "grow_cycle_id": grow_cycle_id,
                        "phase_index": phase_index,
                        "elapsed_hours": elapsed_hours,
                    },
                )
            return

        success = await grow_cycle_repo.advance_phase(int(grow_cycle_id))
        if success:
            await record_simulation_event_fn(
                zone_id=zone_id,
                service="automation-engine",
                stage="phase_transition",
                status="advanced",
                message="Simulation phase advanced",
                payload={
                    "grow_cycle_id": grow_cycle_id,
                    "phase_index": phase_index,
                    "elapsed_hours": elapsed_hours,
                },
            )
    except CircuitBreakerOpenError:
        logger.warning(
            "Zone %s: Circuit Breaker open during phase transition",
            zone_id,
            extra={"zone_id": zone_id},
        )
        await emit_controller_circuit_open_signal_fn(zone_id, "phase_transition")


def append_correlation_id(details: Dict[str, Any], correlation_id: Optional[str]) -> Dict[str, Any]:
    payload = dict(details)
    if correlation_id:
        payload["correlation_id"] = correlation_id
    return payload


async def publish_controller_action_with_event_integrity(
    *,
    zone_id: int,
    controller_name: str,
    command: Dict[str, Any],
    command_gateway: Any,
    create_zone_event_safe_fn: CreateZoneEventSafeFn,
    emit_controller_circuit_open_signal_fn: EmitControllerCircuitOpenSignalFn,
    append_correlation_id_fn: Callable[[Dict[str, Any], Optional[str]], Dict[str, Any]],
) -> bool:
    event_type = str(command.get("event_type") or "").strip()
    event_details = command.get("event_details") if isinstance(command.get("event_details"), dict) else {}

    try:
        published = await command_gateway.publish_controller_command(zone_id, command)
    except CircuitBreakerOpenError:
        if event_type:
            await create_zone_event_safe_fn(
                zone_id=zone_id,
                event_type=f"{event_type}_COMMAND_UNCONFIRMED",
                details={
                    **event_details,
                    "controller": controller_name,
                    "cmd": command.get("cmd"),
                    "node_uid": command.get("node_uid"),
                    "channel": command.get("channel"),
                    "reason": "publish_circuit_breaker_open",
                },
                signal_name=f"{controller_name}_command_unconfirmed",
            )
        await emit_controller_circuit_open_signal_fn(
            zone_id,
            controller_name,
            channel=command.get("channel"),
            cmd=command.get("cmd"),
        )
        return False

    correlation_id: Optional[str] = None
    raw_cmd_id = command.get("cmd_id")
    if isinstance(raw_cmd_id, str):
        normalized_cmd_id = raw_cmd_id.strip()
        if normalized_cmd_id:
            correlation_id = normalized_cmd_id

    dedupe_decision = str(command.get("dedupe_decision") or "").strip().lower()

    if not published:
        if event_type:
            await create_zone_event_safe_fn(
                zone_id=zone_id,
                event_type=f"{event_type}_COMMAND_REJECTED",
                details=append_correlation_id_fn(
                    {
                        **event_details,
                        "controller": controller_name,
                        "cmd": command.get("cmd"),
                        "node_uid": command.get("node_uid"),
                        "channel": command.get("channel"),
                        "reason": "publish_rejected",
                    },
                    correlation_id,
                ),
                signal_name=f"{controller_name}_command_rejected",
            )
        return False

    if event_type:
        if dedupe_decision in {"duplicate_blocked", "duplicate_no_effect"}:
            return True
        await create_zone_event_safe_fn(
            zone_id=zone_id,
            event_type=event_type,
            details=append_correlation_id_fn(event_details, correlation_id),
            signal_name=f"{controller_name}_action_confirmed",
        )
    return True


__all__ = [
    "append_correlation_id",
    "check_phase_transitions",
    "publish_controller_action_with_event_integrity",
]
