"""Helpers for core device-task execution branch."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Sequence

from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome
from services.resilience_contract import INFRA_TASK_NO_ONLINE_NODES

GetZoneNodesFn = Callable[[int, Sequence[str]], Awaitable[Sequence[Dict[str, Any]]]]
ResolveCommandNameFn = Callable[[Dict[str, Any], SchedulerTaskMapping], str | None]
ResolveCommandParamsFn = Callable[[Dict[str, Any], SchedulerTaskMapping], Dict[str, Any]]
PublishBatchFn = Callable[..., Awaitable[Dict[str, Any]]]
SendInfraAlertFn = Callable[..., Awaitable[Any]]


def _filter_nodes_for_command(nodes: Sequence[Dict[str, Any]], cmd: str | None) -> list[Dict[str, Any]]:
    command = str(cmd or "").strip().lower()
    if command != "run_pump":
        return list(nodes)

    filtered: list[Dict[str, Any]] = []
    for node in nodes:
        channel = str(node.get("channel") or "").strip().lower()
        if channel.startswith("valve"):
            continue
        filtered.append(node)

    return filtered


async def execute_device_task_core(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    mapping: SchedulerTaskMapping,
    context: Dict[str, Any],
    decision: DecisionOutcome,
    get_zone_nodes_fn: GetZoneNodesFn,
    resolve_command_name_fn: ResolveCommandNameFn,
    resolve_command_params_fn: ResolveCommandParamsFn,
    publish_batch_fn: PublishBatchFn,
    send_infra_alert_fn: SendInfraAlertFn,
    err_mapping_not_found: str,
    err_no_online_nodes: str,
) -> Dict[str, Any]:
    if not mapping.node_types:
        return {
            "success": False,
            "task_type": mapping.task_type,
            "error": "mapping_has_no_node_types",
            "error_code": err_mapping_not_found,
        }

    nodes = await get_zone_nodes_fn(zone_id, mapping.node_types)
    if not nodes:
        await send_infra_alert_fn(
            code=INFRA_TASK_NO_ONLINE_NODES,
            alert_type="Scheduler Task No Online Nodes",
            message=f"Задача {mapping.task_type} не выполнена: нет online-нод целевых типов",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=err_no_online_nodes,
            details={
                "task_type": mapping.task_type,
                "node_types": list(mapping.node_types),
            },
        )
        return {
            "success": False,
            "task_type": mapping.task_type,
            "error": f"no_online_nodes_for_{mapping.task_type}",
            "error_code": err_no_online_nodes,
        }

    cmd = resolve_command_name_fn(payload, mapping)
    if not cmd:
        return {
            "success": False,
            "task_type": mapping.task_type,
            "error": "command_not_configured",
            "error_code": err_mapping_not_found,
        }
    nodes = _filter_nodes_for_command(nodes, cmd)
    if not nodes:
        await send_infra_alert_fn(
            code=INFRA_TASK_NO_ONLINE_NODES,
            alert_type="Scheduler Task No Online Nodes",
            message=f"Задача {mapping.task_type} не выполнена: нет online-нод целевых типов",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=err_no_online_nodes,
            details={
                "task_type": mapping.task_type,
                "node_types": list(mapping.node_types),
                "command": cmd,
                "reason": "filtered_nodes_for_command",
            },
        )
        return {
            "success": False,
            "task_type": mapping.task_type,
            "error": f"no_online_nodes_for_{mapping.task_type}",
            "error_code": err_no_online_nodes,
        }

    params = resolve_command_params_fn(payload, mapping)
    return await publish_batch_fn(
        zone_id=zone_id,
        task_type=mapping.task_type,
        nodes=nodes,
        cmd=cmd,
        params=params,
        context=context,
        decision=decision,
    )


__all__ = ["execute_device_task_core"]
