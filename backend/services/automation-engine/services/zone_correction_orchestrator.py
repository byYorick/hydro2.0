"""Correction orchestration helpers for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from infrastructure.circuit_breaker import CircuitBreakerOpenError
from services.correction_bounds_policy import extract_bounds_overrides


BuildCorrectionGatingStateFn = Callable[..., Dict[str, Any]]
EmitCorrectionSkipEventThrottledFn = Callable[..., Awaitable[None]]
EmitCorrectionMissingFlagsSignalFn = Callable[[int, Dict[str, Any], Dict[str, Dict[str, Any]]], Awaitable[None]]
EmitCorrectionStaleFlagsSignalFn = Callable[[int, Dict[str, Any], Dict[str, Dict[str, Any]]], Awaitable[None]]
ApplySensorModePolicyFn = Callable[..., Awaitable[None]]
ResolveAllowedEcComponentsFn = Callable[[str], Optional[list[str]]]
EmitControllerCircuitOpenSignalFn = Callable[..., Awaitable[None]]


async def process_correction_controllers(
    *,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    telemetry_timestamps: Dict[str, Any],
    correction_flags: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
    capabilities: Dict[str, bool],
    workflow_phase: str,
    water_level_ok: bool,
    actuators: Dict[str, Dict[str, Any]],
    ph_controller: Any,
    ec_controller: Any,
    command_bus: Any,
    build_correction_gating_state_fn: BuildCorrectionGatingStateFn,
    emit_correction_skip_event_throttled_fn: EmitCorrectionSkipEventThrottledFn,
    emit_correction_missing_flags_signal_fn: EmitCorrectionMissingFlagsSignalFn,
    emit_correction_stale_flags_signal_fn: EmitCorrectionStaleFlagsSignalFn,
    apply_sensor_mode_policy_fn: ApplySensorModePolicyFn,
    resolve_allowed_ec_components_fn: ResolveAllowedEcComponentsFn,
    emit_controller_circuit_open_signal_fn: EmitControllerCircuitOpenSignalFn,
    logger: Any,
) -> None:
    bounds_overrides = extract_bounds_overrides(targets)
    logger.debug(
        "Zone %s: starting correction controllers evaluation",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "ph_control_enabled": bool(capabilities.get("ph_control", False)),
            "ec_control_enabled": bool(capabilities.get("ec_control", False)),
            "correction_flags": correction_flags,
            "bounds_overrides": bounds_overrides,
        },
    )
    gating_state = build_correction_gating_state_fn(
        telemetry=telemetry,
        telemetry_timestamps=telemetry_timestamps,
        correction_flags=correction_flags,
        workflow_phase=workflow_phase,
    )
    logger.info(
        "Zone %s: correction gating evaluated",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "can_run": gating_state.get("can_run"),
            "reason_code": gating_state.get("reason_code"),
            "missing_flags": gating_state.get("missing_flags"),
            "stale_flags": gating_state.get("stale_flags"),
            "stale_flag_reasons": gating_state.get("stale_flag_reasons"),
            "flag_age_seconds": gating_state.get("flag_age_seconds"),
            "require_timestamps": gating_state.get("require_timestamps"),
            "timestamp_diagnostics": gating_state.get("timestamp_diagnostics"),
            "workflow_phase_override": gating_state.get("workflow_phase_override"),
        },
    )
    if gating_state["missing_flags"]:
        logger.warning(
            "Zone %s: correction blocked by missing flags",
            zone_id,
            extra={
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "missing_flags": gating_state["missing_flags"],
                "require_timestamps": gating_state.get("require_timestamps"),
                "timestamp_diagnostics": gating_state.get("timestamp_diagnostics"),
                "correction_flags": gating_state.get("flags"),
            },
        )
        await emit_correction_skip_event_throttled_fn(
            zone_id=zone_id,
            event_type="CORRECTION_SKIPPED_MISSING_FLAGS",
            event_payload={
                "reason_code": "missing_flags",
                "missing_flags": gating_state["missing_flags"],
                "correction_flags": gating_state["flags"],
                "flag_age_seconds": gating_state.get("flag_age_seconds") or {},
                "require_timestamps": gating_state.get("require_timestamps"),
                "timestamp_diagnostics": gating_state.get("timestamp_diagnostics") or {},
                "workflow_phase": workflow_phase,
            },
            reason_code="missing_flags",
        )
        await emit_correction_missing_flags_signal_fn(zone_id, gating_state, nodes)
        await apply_sensor_mode_policy_fn(
            zone_id=zone_id,
            nodes=nodes,
            reason_code="missing_flags",
            can_run=False,
        )
        return

    if not gating_state["can_run"]:
        reason_code = str(gating_state["reason_code"] or "correction_flags_blocked")
        logger.warning(
            "Zone %s: correction blocked by gating",
            zone_id,
            extra={
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "reason_code": reason_code,
                "stale_flags": gating_state.get("stale_flags") or [],
                "stale_flag_reasons": gating_state.get("stale_flag_reasons") or {},
                "missing_flags": gating_state.get("missing_flags") or [],
                "flag_age_seconds": gating_state.get("flag_age_seconds") or {},
                "require_timestamps": gating_state.get("require_timestamps"),
                "timestamp_diagnostics": gating_state.get("timestamp_diagnostics") or {},
                "correction_flags": gating_state.get("flags"),
            },
        )
        event_type = (
            "CORRECTION_SKIPPED_STALE_FLAGS" if reason_code == "stale_flags" else "CORRECTION_SKIPPED_FLAGS_GATING"
        )
        await emit_correction_skip_event_throttled_fn(
            zone_id=zone_id,
            event_type=event_type,
            event_payload={
                "reason_code": reason_code,
                "stale_flags": gating_state.get("stale_flags") or [],
                "stale_flag_reasons": gating_state.get("stale_flag_reasons") or {},
                "correction_flags": gating_state["flags"],
                "flag_age_seconds": gating_state.get("flag_age_seconds") or {},
                "require_timestamps": gating_state.get("require_timestamps"),
                "timestamp_diagnostics": gating_state.get("timestamp_diagnostics") or {},
                "workflow_phase": workflow_phase,
            },
            reason_code=reason_code,
        )
        if reason_code == "stale_flags":
            await emit_correction_stale_flags_signal_fn(zone_id, gating_state, nodes)
        await apply_sensor_mode_policy_fn(
            zone_id=zone_id,
            nodes=nodes,
            reason_code=reason_code,
            can_run=False,
        )
        return

    await apply_sensor_mode_policy_fn(
        zone_id=zone_id,
        nodes=nodes,
        reason_code="gating_passed",
        can_run=True,
    )

    if capabilities.get("ph_control", False):
        ph_cmd = await ph_controller.check_and_correct(
            zone_id,
            targets,
            telemetry,
            telemetry_timestamps,
            nodes,
            water_level_ok,
            actuators,
            bounds_overrides=bounds_overrides,
        )
        if ph_cmd:
            logger.info(
                "Zone %s: PH correction command prepared",
                zone_id,
                extra={
                    "zone_id": zone_id,
                    "workflow_phase": workflow_phase,
                    "cmd": ph_cmd.get("cmd"),
                    "channel": ph_cmd.get("channel"),
                    "node_uid": ph_cmd.get("node_uid"),
                },
            )
            pid = ph_controller._pid_by_zone.get(zone_id)
            try:
                await ph_controller.apply_correction(ph_cmd, command_bus, pid)
                logger.info(
                    "Zone %s: PH correction command applied",
                    zone_id,
                    extra={"zone_id": zone_id, "workflow_phase": workflow_phase},
                )
            except CircuitBreakerOpenError:
                logger.warning(
                    "Zone %s: API Circuit Breaker is OPEN, skipping PH correction command",
                    zone_id,
                    extra={"zone_id": zone_id},
                )
                await emit_controller_circuit_open_signal_fn(
                    zone_id,
                    "ph_correction",
                    channel=ph_cmd.get("channel"),
                    cmd=ph_cmd.get("cmd"),
                )

    if capabilities.get("ec_control", False):
        allowed_ec_components = resolve_allowed_ec_components_fn(workflow_phase)
        logger.debug(
            "Zone %s: EC correction component policy resolved",
            zone_id,
            extra={
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "allowed_ec_components": allowed_ec_components,
            },
        )
        ec_cmd = await ec_controller.check_and_correct(
            zone_id,
            targets,
            telemetry,
            telemetry_timestamps,
            nodes,
            water_level_ok,
            actuators,
            bounds_overrides=bounds_overrides,
            allowed_ec_components=allowed_ec_components,
        )
        if ec_cmd:
            logger.info(
                "Zone %s: EC correction command prepared",
                zone_id,
                extra={
                    "zone_id": zone_id,
                    "workflow_phase": workflow_phase,
                    "cmd": ec_cmd.get("cmd"),
                    "channel": ec_cmd.get("channel"),
                    "node_uid": ec_cmd.get("node_uid"),
                    "allowed_ec_components": allowed_ec_components,
                },
            )
            pid = ec_controller._pid_by_zone.get(zone_id)
            try:
                await ec_controller.apply_correction(ec_cmd, command_bus, pid)
                logger.info(
                    "Zone %s: EC correction command applied",
                    zone_id,
                    extra={
                        "zone_id": zone_id,
                        "workflow_phase": workflow_phase,
                        "allowed_ec_components": allowed_ec_components,
                    },
                )
            except CircuitBreakerOpenError:
                logger.warning(
                    "Zone %s: API Circuit Breaker is OPEN, skipping EC correction command",
                    zone_id,
                    extra={"zone_id": zone_id},
                )
                await emit_controller_circuit_open_signal_fn(
                    zone_id,
                    "ec_correction",
                    channel=ec_cmd.get("channel"),
                    cmd=ec_cmd.get("cmd"),
                )


__all__ = ["process_correction_controllers"]
