"""Controller processor helpers for ZoneAutomationService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional


PublishControllerActionFn = Callable[..., Awaitable[bool]]
CheckAndControlLightingFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]
CheckAndControlClimateFn = Callable[..., Awaitable[list[Dict[str, Any]]]]
CheckAndControlIrrigationFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]
CheckAndControlRecirculationFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]
CanRunPumpFn = Callable[[int, str], Awaitable[tuple[bool, str]]]
SendInfraAlertFn = Callable[..., Awaitable[bool]]


async def process_light_controller(
    *,
    zone_id: int,
    targets: Dict[str, Any],
    capabilities: Dict[str, bool],
    bindings: Dict[str, Dict[str, Any]],
    current_time: datetime,
    check_and_control_lighting_fn: CheckAndControlLightingFn,
    publish_controller_action_with_event_integrity_fn: PublishControllerActionFn,
) -> None:
    if not capabilities.get("light_control", False):
        return

    light_cmd = await check_and_control_lighting_fn(zone_id, targets, bindings, current_time)
    if light_cmd:
        await publish_controller_action_with_event_integrity_fn(
            zone_id=zone_id,
            controller_name="light",
            command=light_cmd,
        )


async def process_climate_controller(
    *,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    capabilities: Dict[str, bool],
    bindings: Dict[str, Dict[str, Any]],
    check_and_control_climate_fn: CheckAndControlClimateFn,
    publish_controller_action_with_event_integrity_fn: PublishControllerActionFn,
) -> None:
    if not capabilities.get("climate_control", False):
        return

    climate_commands = await check_and_control_climate_fn(zone_id, targets, telemetry, bindings)
    for command in climate_commands:
        await publish_controller_action_with_event_integrity_fn(
            zone_id=zone_id,
            controller_name="climate",
            command=command,
        )


async def process_irrigation_controller(
    *,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    capabilities: Dict[str, bool],
    workflow_phase: str,
    bindings: Dict[str, Dict[str, Any]],
    actuators: Dict[str, Dict[str, Any]],
    current_time: datetime,
    time_scale: Optional[float],
    sim_clock: Optional[Any],
    check_and_control_irrigation_fn: CheckAndControlIrrigationFn,
    can_run_pump_fn: CanRunPumpFn,
    send_infra_alert_fn: SendInfraAlertFn,
    publish_controller_action_with_event_integrity_fn: PublishControllerActionFn,
    logger: Any,
) -> None:
    if not capabilities.get("irrigation_control", False):
        logger.debug(
            "Zone %s: irrigation controller skipped, capability disabled",
            zone_id,
            extra={"zone_id": zone_id, "workflow_phase": workflow_phase},
        )
        return

    logger.debug(
        "Zone %s: evaluating irrigation command for workflow_phase=%s",
        zone_id,
        workflow_phase,
        extra={"zone_id": zone_id, "workflow_phase": workflow_phase},
    )

    irrigation_cmd = await check_and_control_irrigation_fn(
        zone_id,
        targets,
        telemetry,
        bindings,
        actuators,
        current_time=current_time,
        time_scale=time_scale,
        sim_clock=sim_clock,
        workflow_phase=workflow_phase,
    )
    if not irrigation_cmd:
        logger.debug(
            "Zone %s: irrigation controller produced no command (workflow_phase=%s)",
            zone_id,
            workflow_phase,
            extra={"zone_id": zone_id, "workflow_phase": workflow_phase},
        )
        return

    logger.info(
        "Zone %s: irrigation command candidate prepared",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "cmd": irrigation_cmd.get("cmd"),
            "channel": irrigation_cmd.get("channel"),
            "node_uid": irrigation_cmd.get("node_uid"),
            "event_type": irrigation_cmd.get("event_type"),
        },
    )

    pump_channel = irrigation_cmd.get("channel", "default")
    can_run, error_msg = await can_run_pump_fn(zone_id, pump_channel)
    if not can_run:
        logger.warning(
            "Zone %s: Cannot run irrigation pump %s in workflow_phase=%s: %s",
            zone_id,
            pump_channel,
            workflow_phase,
            error_msg,
            extra={
                "zone_id": zone_id,
                "workflow_phase": workflow_phase,
                "channel": pump_channel,
                "cmd": irrigation_cmd.get("cmd"),
            },
        )
        await send_infra_alert_fn(
            code="infra_irrigation_pump_blocked",
            alert_type="Irrigation Pump Blocked",
            message=f"Zone {zone_id}: irrigation pump blocked by safety rules",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="controller:irrigation",
            channel=pump_channel,
            cmd="run_pump",
            error_type="PumpSafetyBlocked",
            details={"reason": error_msg},
        )
        return

    logger.info(
        "Zone %s: publishing irrigation command",
        zone_id,
        extra={
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "cmd": irrigation_cmd.get("cmd"),
            "channel": irrigation_cmd.get("channel"),
            "node_uid": irrigation_cmd.get("node_uid"),
        },
    )
    await publish_controller_action_with_event_integrity_fn(
        zone_id=zone_id,
        controller_name="irrigation",
        command=irrigation_cmd,
    )


async def process_recirculation_controller(
    *,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    capabilities: Dict[str, bool],
    bindings: Dict[str, Dict[str, Any]],
    actuators: Dict[str, Dict[str, Any]],
    current_time: datetime,
    time_scale: Optional[float],
    sim_clock: Optional[Any],
    check_and_control_recirculation_fn: CheckAndControlRecirculationFn,
    publish_controller_action_with_event_integrity_fn: PublishControllerActionFn,
) -> None:
    if not capabilities.get("recirculation", False):
        return

    recirculation_cmd = await check_and_control_recirculation_fn(
        zone_id,
        targets,
        telemetry,
        bindings,
        actuators,
        current_time=current_time,
        time_scale=time_scale,
        sim_clock=sim_clock,
    )
    if recirculation_cmd:
        await publish_controller_action_with_event_integrity_fn(
            zone_id=zone_id,
            controller_name="recirculation",
            command=recirculation_cmd,
        )


__all__ = [
    "process_climate_controller",
    "process_irrigation_controller",
    "process_light_controller",
    "process_recirculation_controller",
]
