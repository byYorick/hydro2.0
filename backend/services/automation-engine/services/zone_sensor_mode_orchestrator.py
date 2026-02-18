"""Helpers for correction sensor-mode orchestration in zone automation."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from infrastructure.circuit_breaker import CircuitBreakerOpenError


ResolveSensorNodesFn = Callable[[Dict[str, Dict[str, Any]]], List[Dict[str, Any]]]
EmitControllerCircuitOpenSignalFn = Callable[..., Awaitable[None]]
SetSensorModeFn = Callable[..., Awaitable[None]]
ResolveActionFn = Callable[[str, bool], str]


def resolve_correction_sensor_nodes(nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for node in (nodes or {}).values():
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "").strip().lower()
        if node_type not in {"ph", "ec"}:
            continue
        node_uid = str(node.get("node_uid") or "").strip()
        if not node_uid or node_uid in seen:
            continue
        seen.add(node_uid)
        result.append({"node_uid": node_uid, "type": node_type})
    return result


def resolve_sensor_mode_action(
    reason_code: str,
    can_run: bool,
    *,
    sensor_mode_policy: Dict[str, str],
) -> str:
    normalized_reason = str(reason_code or "").strip().lower()
    default_action = "noop" if can_run else "deactivate"
    return sensor_mode_policy.get(normalized_reason, default_action)


async def apply_sensor_mode_policy(
    *,
    zone_id: int,
    nodes: Dict[str, Dict[str, Any]],
    reason_code: str,
    can_run: bool,
    resolve_sensor_mode_action_fn: ResolveActionFn,
    set_sensor_mode_fn: SetSensorModeFn,
    logger: logging.Logger,
) -> None:
    action = resolve_sensor_mode_action_fn(reason_code, can_run)
    logger.info(
        "Zone %s: sensor mode policy resolved",
        zone_id,
        extra={
            "zone_id": zone_id,
            "reason_code": reason_code,
            "can_run": can_run,
            "action": action,
        },
    )
    if action == "activate":
        await set_sensor_mode_fn(zone_id=zone_id, nodes=nodes, activate=True, reason=reason_code)
        return
    if action == "deactivate":
        await set_sensor_mode_fn(zone_id=zone_id, nodes=nodes, activate=False, reason=reason_code)
        return
    logger.debug(
        "Zone %s: sensor mode policy noop",
        zone_id,
        extra={"zone_id": zone_id, "reason_code": reason_code, "can_run": can_run},
    )


async def set_sensor_mode(
    *,
    zone_id: int,
    nodes: Dict[str, Dict[str, Any]],
    activate: bool,
    reason: str,
    command_bus: Any,
    correction_sensor_mode_state: Dict[int, bool],
    emit_controller_circuit_open_signal_fn: EmitControllerCircuitOpenSignalFn,
    logger: logging.Logger,
    resolve_correction_sensor_nodes_fn: ResolveSensorNodesFn,
    stabilization_time_sec: int = 60,
) -> None:
    previous_state = correction_sensor_mode_state.get(zone_id)
    if previous_state is not None and previous_state == activate:
        logger.info(
            "Zone %s: skip sensor mode command due to local debounce cache",
            zone_id,
            extra={
                "zone_id": zone_id,
                "activate": activate,
                "reason": reason,
                "cached_state": previous_state,
            },
        )
        return

    sensor_nodes = resolve_correction_sensor_nodes_fn(nodes)
    if not sensor_nodes:
        logger.info(
            "Zone %s: no sensor nodes resolved for sensor mode command",
            zone_id,
            extra={"zone_id": zone_id, "activate": activate, "reason": reason},
        )
        return

    cmd = "activate_sensor_mode" if activate else "deactivate_sensor_mode"
    params: Dict[str, Any] = {"reason": reason}
    if activate:
        params["stabilization_time_sec"] = stabilization_time_sec

    publish_failed_nodes: List[str] = []
    for sensor_node in sensor_nodes:
        command = {
            "node_uid": sensor_node["node_uid"],
            "channel": "system",
            "cmd": cmd,
            "params": params,
        }
        try:
            published = await command_bus.publish_controller_command(zone_id, command)
        except CircuitBreakerOpenError:
            logger.warning(
                "Zone %s: API Circuit Breaker is OPEN, skipping sensor mode command",
                zone_id,
                extra={"zone_id": zone_id, "cmd": cmd, "node_uid": sensor_node["node_uid"]},
            )
            await emit_controller_circuit_open_signal_fn(
                zone_id,
                "correction_sensor_mode",
                channel="system",
                cmd=cmd,
            )
            return
        if not published:
            publish_failed_nodes.append(sensor_node["node_uid"])

    if publish_failed_nodes:
        logger.warning(
            "Zone %s: sensor mode command batch not confirmed, cache not updated",
            zone_id,
            extra={
                "zone_id": zone_id,
                "activate": activate,
                "reason": reason,
                "failed_node_uids": publish_failed_nodes,
                "sensor_node_uids": [item.get("node_uid") for item in sensor_nodes],
            },
        )
        return

    correction_sensor_mode_state[zone_id] = activate
    logger.info(
        "Zone %s: sensor mode command batch completed",
        zone_id,
        extra={
            "zone_id": zone_id,
            "activate": activate,
            "reason": reason,
            "sensor_node_uids": [item.get("node_uid") for item in sensor_nodes],
            "cached_state": correction_sensor_mode_state.get(zone_id),
        },
    )


__all__ = [
    "apply_sensor_mode_policy",
    "resolve_correction_sensor_nodes",
    "resolve_sensor_mode_action",
    "set_sensor_mode",
]
