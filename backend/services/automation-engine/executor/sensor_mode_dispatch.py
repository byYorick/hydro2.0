"""Helpers for sensor-mode command dispatch."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Sequence

from domain.models.decision_models import DecisionOutcome

ResolveOnlineNodeForChannelFn = Callable[..., Awaitable[Dict[str, Any] | None]]
PublishBatchFn = Callable[..., Awaitable[Dict[str, Any]]]


async def dispatch_sensor_mode_command_for_nodes(
    *,
    zone_id: int,
    context: Dict[str, Any],
    decision: DecisionOutcome,
    activate: bool,
    reason_code: str,
    resolve_online_node_for_channel_fn: ResolveOnlineNodeForChannelFn,
    publish_batch_fn: PublishBatchFn,
) -> Dict[str, Any]:
    cmd = "activate_sensor_mode" if activate else "deactivate_sensor_mode"
    params: Dict[str, Any] = {"reason": reason_code}
    if activate:
        params["stabilization_time_sec"] = 60

    nodes: List[Dict[str, Any]] = []
    for node_type in ("ph", "ec"):
        node = await resolve_online_node_for_channel_fn(
            zone_id=zone_id,
            channel="system",
            node_types=[node_type],
        )
        if node is not None:
            nodes.append(node)

    if not nodes:
        return {
            "success": True,
            "commands_total": 0,
            "commands_failed": 0,
            "commands_submitted": 0,
            "commands_effect_confirmed": 0,
            "command_statuses": [],
        }

    return await publish_batch_fn(
        zone_id=zone_id,
        task_type="diagnostics",
        nodes=nodes,
        cmd=cmd,
        params=params,
        context=context,
        decision=decision,
        accepted_terminal_statuses=("DONE", "NO_EFFECT"),
        dedupe_bypass=True,
    )


__all__ = ["dispatch_sensor_mode_command_for_nodes"]
