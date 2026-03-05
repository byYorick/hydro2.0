"""Helpers for core device-task execution branch."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Sequence

from common.pump_safety import can_run_pump
from config.scheduler_task_mapping import SchedulerTaskMapping
from domain.models.decision_models import DecisionOutcome
from services.resilience_contract import INFRA_IRRIGATION_PUMP_BLOCKED, INFRA_TASK_NO_ONLINE_NODES

GetZoneNodesFn = Callable[[int, Sequence[str]], Awaitable[Sequence[Dict[str, Any]]]]
ResolveCommandNameFn = Callable[[Dict[str, Any], SchedulerTaskMapping], str | None]
ResolveCommandParamsFn = Callable[[Dict[str, Any], SchedulerTaskMapping], Dict[str, Any]]
PublishBatchFn = Callable[..., Awaitable[Dict[str, Any]]]
SendInfraAlertFn = Callable[..., Awaitable[Any]]
SendInfraResolvedAlertFn = Callable[..., Awaitable[Any]]

logger = logging.getLogger(__name__)


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


def _accepted_terminal_statuses_for_mapping(mapping: SchedulerTaskMapping) -> tuple[str, ...] | None:
    # Команды с state_key (set_relay/light_on/light_off) идемпотентны для текущего состояния,
    # поэтому NO_EFFECT считаем подтверждённым эффектом.
    if mapping.state_key:
        return ("DONE", "NO_EFFECT")
    return None


async def _enforce_pump_safety_gate(
    *,
    zone_id: int,
    task_type: str,
    cmd: str | None,
    nodes: Sequence[Dict[str, Any]],
    send_infra_alert_fn: SendInfraAlertFn,
    send_infra_resolved_alert_fn: SendInfraResolvedAlertFn | None = None,
) -> str | None:
    command = str(cmd or "").strip().lower()
    if command != "run_pump":
        return None

    blocked: list[Dict[str, Any]] = []
    for node in nodes:
        channel = str(node.get("channel") or "").strip().lower()
        if not channel:
            continue
        raw_node_id = node.get("id")
        node_id: int | None = None
        if isinstance(raw_node_id, int):
            node_id = raw_node_id
        else:
            try:
                node_id = int(raw_node_id)
            except Exception:
                node_id = None
        can_run, error_msg = await can_run_pump(zone_id, channel, node_id=node_id)
        if can_run:
            continue
        blocked.append(
            {
                "node_id": node_id,
                "node_uid": node.get("uid"),
                "channel": channel,
                "reason": str(error_msg or "pump_safety_blocked"),
            }
        )

    if not blocked:
        if callable(send_infra_resolved_alert_fn):
            primary_channel = next(
                (str(node.get("channel") or "").strip().lower() for node in nodes if str(node.get("channel") or "").strip()),
                None,
            )
            try:
                await send_infra_resolved_alert_fn(
                    code=INFRA_IRRIGATION_PUMP_BLOCKED,
                    alert_type="Irrigation Pump Blocked",
                    message=f"Задача {task_type}: safety-политика насоса восстановлена",
                    zone_id=zone_id,
                    service="automation-engine",
                    component="scheduler_task_executor",
                    channel=primary_channel,
                    cmd="run_pump",
                    details={
                        "task_type": task_type,
                        "reason_code": "pump_safety_gate_passed",
                    },
                )
            except Exception:
                logger.warning(
                    "Zone %s: failed to resolve pump safety alert after successful gate check",
                    zone_id,
                    exc_info=True,
                )
        return None

    primary = blocked[0]
    await send_infra_alert_fn(
        code=INFRA_IRRIGATION_PUMP_BLOCKED,
        alert_type="Irrigation Pump Blocked",
        message=f"Задача {task_type} заблокирована safety-политикой насоса",
        severity="error",
        zone_id=zone_id,
        service="automation-engine",
        component="scheduler_task_executor",
        channel=primary.get("channel"),
        cmd="run_pump",
        error_type="PumpSafetyBlocked",
        details={
            "task_type": task_type,
            "error_code": "two_tank_pump_safety_blocked",
            "blocked_pumps": blocked,
        },
    )
    return str(primary.get("reason") or "pump_safety_blocked")


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
    send_infra_resolved_alert_fn: SendInfraResolvedAlertFn | None = None,
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
    safety_error = await _enforce_pump_safety_gate(
        zone_id=zone_id,
        task_type=mapping.task_type,
        cmd=cmd,
        nodes=nodes,
        send_infra_alert_fn=send_infra_alert_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
    )
    if safety_error is not None:
        return {
            "success": False,
            "task_type": mapping.task_type,
            "error": safety_error,
            "error_code": "two_tank_pump_safety_blocked",
            "commands_total": 0,
            "commands_failed": 0,
            "command_statuses": [],
        }

    accepted_terminal_statuses = _accepted_terminal_statuses_for_mapping(mapping)
    return await publish_batch_fn(
        zone_id=zone_id,
        task_type=mapping.task_type,
        nodes=nodes,
        cmd=cmd,
        params=params,
        context=context,
        decision=decision,
        accepted_terminal_statuses=accepted_terminal_statuses,
    )


__all__ = ["execute_device_task_core"]
