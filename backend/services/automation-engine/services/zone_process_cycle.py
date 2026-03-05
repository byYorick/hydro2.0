"""High-level zone processing cycle orchestration helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from infrastructure.circuit_breaker import CircuitBreakerOpenError


async def process_zone_cycle(
    *,
    zone_id: int,
    sim_clock: Optional[Any],
    should_process_zone_fn: Callable[[int], bool],
    emit_backoff_skip_signal_fn: Callable[[int], Awaitable[None]],
    is_degraded_mode_fn: Callable[[int], bool],
    check_zone_deletion_fn: Callable[[int], Awaitable[None]],
    check_pid_config_updates_fn: Callable[[int], Awaitable[None]],
    check_phase_transitions_fn: Callable[[int, Optional[Any]], Awaitable[None]],
    grow_cycle_repo: Any,
    recipe_repo: Any,
    infrastructure_repo: Any,
    actuator_registry: Any,
    record_zone_error_fn: Callable[[int], None],
    emit_zone_data_unavailable_signal_fn: Callable[[int], Awaitable[None]],
    get_or_restore_workflow_phase_fn: Callable[[int], Awaitable[str]],
    safe_process_controller_fn: Callable[[str, Any, int], Awaitable[None]],
    process_light_controller_fn: Callable[..., Awaitable[None]],
    process_climate_controller_fn: Callable[..., Awaitable[None]],
    process_irrigation_controller_fn: Callable[..., Awaitable[None]],
    process_recirculation_controller_fn: Callable[..., Awaitable[None]],
    process_correction_controllers_fn: Callable[..., Awaitable[None]],
    load_zone_control_mode_fn: Callable[[int], Awaitable[str]],
    load_latest_zone_task_fn: Callable[[int], Awaitable[Optional[Dict[str, Any]]]],
    evaluate_required_nodes_recovery_gate_fn: Callable[[int, Dict[str, Any]], Awaitable[bool]],
    update_zone_health_fn: Callable[[int], Awaitable[None]],
    emit_missing_targets_signal_fn: Callable[[int, Optional[Dict[str, Any]]], Awaitable[None]],
    emit_degraded_mode_signal_fn: Callable[[int], Awaitable[None]],
    reset_zone_error_streak_fn: Callable[[int], int],
    emit_zone_recovered_signal_fn: Callable[[int, int], Awaitable[None]],
    get_error_streak_fn: Callable[[int], int],
    get_next_allowed_run_at_fn: Callable[[int], Any],
    create_zone_event_fn: Callable[..., Awaitable[Any]],
    check_water_level_fn: Callable[..., Awaitable[tuple[bool, Optional[float]]]],
    ensure_water_level_alert_fn: Callable[[int, float], Awaitable[Any]],
    utcnow_fn: Callable[[], Any],
    check_latency_metric: Any,
    zone_checks_metric: Any,
    logger: Any,
) -> None:
    if not should_process_zone_fn(zone_id):
        await emit_backoff_skip_signal_fn(zone_id)
        return

    is_degraded = is_degraded_mode_fn(zone_id)

    try:
        with check_latency_metric.time():
            zone_checks_metric.inc()
            await check_zone_deletion_fn(zone_id)
            await check_pid_config_updates_fn(zone_id)
            await check_phase_transitions_fn(zone_id, sim_clock)

        try:
            grow_cycle = await grow_cycle_repo.get_active_grow_cycle(zone_id)
            targets = grow_cycle.get("targets") if grow_cycle else None

            if not targets or not isinstance(targets, dict):
                await emit_missing_targets_signal_fn(zone_id, grow_cycle)
                return

            zone_data = await recipe_repo.get_zone_data_batch(zone_id)
            telemetry = zone_data.get("telemetry", {})
            telemetry_timestamps = zone_data.get("telemetry_timestamps", {})
            correction_flags = zone_data.get("correction_flags", {})
            nodes = zone_data.get("nodes", {})
            capabilities = zone_data.get("capabilities", {})
            bindings = await infrastructure_repo.get_zone_bindings_by_role(zone_id)
            actuators = actuator_registry.resolve(zone_id, bindings, nodes)
        except CircuitBreakerOpenError:
            logger.warning(
                "Zone %s: Database Circuit Breaker is OPEN, skipping zone processing",
                zone_id,
                extra={"zone_id": zone_id},
            )
            record_zone_error_fn(zone_id)
            await emit_zone_data_unavailable_signal_fn(zone_id)
            return

        normalized_correction_flags = correction_flags if isinstance(correction_flags, dict) else {}
        required_nodes_ready = await evaluate_required_nodes_recovery_gate_fn(zone_id, capabilities)
        if not required_nodes_ready:
            record_zone_error_fn(zone_id)
            return
        workflow_phase = await get_or_restore_workflow_phase_fn(zone_id)
        logger.info(
            "Zone %s: starting processing cycle with workflow_phase=%s",
            zone_id,
            workflow_phase,
            extra={
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "is_degraded": is_degraded,
                "targets_keys": sorted(targets.keys()) if isinstance(targets, dict) else [],
                "telemetry_keys": sorted(telemetry.keys()) if isinstance(telemetry, dict) else [],
                "capabilities": capabilities,
            },
        )

        water_level_ok, water_level = await check_water_level_fn(zone_id, workflow_phase=workflow_phase)
        if water_level is not None:
            await ensure_water_level_alert_fn(zone_id, water_level)

        sim_now = sim_clock.now() if sim_clock else utcnow_fn()
        time_scale = sim_clock.time_scale if sim_clock else None
        latest_zone_task = await load_latest_zone_task_fn(zone_id)
        control_mode = str(await load_zone_control_mode_fn(zone_id) or "").strip().lower() or "auto"
        latest_zone_task_status = (
            str(latest_zone_task.get("status") or "").strip().lower()
            if isinstance(latest_zone_task, dict)
            else ""
        )
        active_scheduler_task = latest_zone_task_status in {"accepted", "running"}

        if control_mode == "manual":
            logger.info(
                "Zone %s: automation controllers skipped in manual control mode",
                zone_id,
                extra={
                    "zone_id": zone_id,
                    "workflow_phase": workflow_phase,
                    "control_mode": control_mode,
                    "active_task_id": (
                        str(latest_zone_task.get("task_id") or "").strip()
                        if isinstance(latest_zone_task, dict)
                        else None
                    ),
                    "active_task_status": latest_zone_task_status or None,
                },
            )
            await safe_process_controller_fn("health", update_zone_health_fn(zone_id), zone_id)
            previous_error_streak = reset_zone_error_streak_fn(zone_id)
            await emit_zone_recovered_signal_fn(zone_id, previous_error_streak)
            return

        if is_degraded:
            await emit_degraded_mode_signal_fn(zone_id)
            logger.warning(
                "Zone %s: Running in DEGRADED mode (error_streak=%s). Only safety checks and health monitoring enabled.",
                zone_id,
                get_error_streak_fn(zone_id),
                extra={"zone_id": zone_id, "error_streak": get_error_streak_fn(zone_id)},
            )

            await safe_process_controller_fn("health", update_zone_health_fn(zone_id), zone_id)
            previous_error_streak = reset_zone_error_streak_fn(zone_id)
            await emit_zone_recovered_signal_fn(zone_id, previous_error_streak)
            return

        await safe_process_controller_fn(
            "light",
            process_light_controller_fn(zone_id, targets, capabilities, bindings, sim_now),
            zone_id,
        )
        await safe_process_controller_fn(
            "climate",
            process_climate_controller_fn(zone_id, targets, telemetry, capabilities, bindings),
            zone_id,
        )
        if active_scheduler_task:
            logger.info(
                "Zone %s: skip irrigation/recirculation controllers while scheduler task is active",
                zone_id,
                extra={
                    "zone_id": zone_id,
                    "workflow_phase": workflow_phase,
                    "active_task_id": (
                        str(latest_zone_task.get("task_id") or "").strip()
                        if isinstance(latest_zone_task, dict)
                        else None
                    ),
                    "active_task_status": latest_zone_task_status,
                },
            )
        else:
            await safe_process_controller_fn(
                "irrigation",
                process_irrigation_controller_fn(
                    zone_id,
                    targets,
                    telemetry,
                    capabilities,
                    workflow_phase,
                    water_level_ok,
                    bindings,
                    actuators,
                    sim_now,
                    time_scale,
                    sim_clock,
                ),
                zone_id,
            )
            await safe_process_controller_fn(
                "recirculation",
                process_recirculation_controller_fn(
                    zone_id,
                    targets,
                    telemetry,
                    capabilities,
                    water_level_ok,
                    bindings,
                    actuators,
                    sim_now,
                    time_scale,
                    sim_clock,
                ),
                zone_id,
            )
        correction_targets = targets
        if isinstance(targets, dict):
            correction_targets = dict(targets)
            correction_meta_raw = correction_targets.get("_meta")
            correction_meta = dict(correction_meta_raw) if isinstance(correction_meta_raw, dict) else {}
            correction_meta.setdefault("cycle_id", grow_cycle.get("id") if isinstance(grow_cycle, dict) else None)
            if isinstance(grow_cycle, dict) and grow_cycle.get("intent_id") is not None:
                correction_meta["intent_id"] = grow_cycle.get("intent_id")
            correction_meta.setdefault("workflow_phase", workflow_phase)
            correction_targets["_meta"] = correction_meta
        if active_scheduler_task:
            logger.info(
                "Zone %s: skip correction controllers while scheduler task is active",
                zone_id,
                extra={
                    "zone_id": zone_id,
                    "workflow_phase": workflow_phase,
                    "active_task_id": str(latest_zone_task.get("task_id") or "").strip() if isinstance(latest_zone_task, dict) else None,
                    "active_task_status": latest_zone_task_status,
                },
            )
        else:
            await safe_process_controller_fn(
                "correction",
                process_correction_controllers_fn(
                    zone_id,
                    correction_targets,
                    telemetry,
                    telemetry_timestamps,
                    normalized_correction_flags,
                    nodes,
                    capabilities,
                    workflow_phase,
                    water_level_ok,
                    bindings,
                    actuators,
                ),
                zone_id,
            )
        await safe_process_controller_fn("health", update_zone_health_fn(zone_id), zone_id)

        previous_error_streak = reset_zone_error_streak_fn(zone_id)
        await emit_zone_recovered_signal_fn(zone_id, previous_error_streak)

    except Exception as error:
        record_zone_error_fn(zone_id)
        logger.error(
            "Zone %s: Error in process_zone: %s",
            zone_id,
            error,
            exc_info=True,
            extra={"zone_id": zone_id, "error_streak": get_error_streak_fn(zone_id)},
        )
        try:
            await create_zone_event_fn(
                zone_id,
                "ZONE_PROCESSING_FAILED",
                {
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "error_streak": get_error_streak_fn(zone_id),
                    "next_allowed_run_at": (
                        get_next_allowed_run_at_fn(zone_id).isoformat() if get_next_allowed_run_at_fn(zone_id) else None
                    ),
                },
            )
        except Exception as event_error:
            logger.error(
                "Zone %s: Failed to create ZONE_PROCESSING_FAILED event: %s",
                zone_id,
                event_error,
                exc_info=True,
            )
        raise


__all__ = ["process_zone_cycle"]
