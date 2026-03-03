"""Helpers for batch command publishing with optional closed-loop tracking."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from domain.models.decision_models import DecisionOutcome

EmitTaskEventFn = Callable[..., Awaitable[None]]
TerminalStatusToErrorCodeFn = Callable[[str], str]


async def publish_batch(
    *,
    zone_id: int,
    task_type: str,
    nodes: Sequence[Dict[str, Any]],
    cmd: str,
    params: Optional[Dict[str, Any]],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    accepted_terminal_statuses: Optional[Sequence[str]],
    dedupe_bypass: bool,
    task_execute_closed_loop_enforce: bool,
    task_execute_closed_loop_timeout_sec: int,
    err_command_send_failed: str,
    err_command_tracker_unavailable: str,
    err_command_effect_not_confirmed: str,
    terminal_status_to_error_code_fn: TerminalStatusToErrorCodeFn,
    emit_task_event_fn: EmitTaskEventFn,
    command_gateway: Any = None,
    command_bus: Any = None,
) -> Dict[str, Any]:
    publisher = command_gateway or command_bus
    if publisher is None:
        return {
            "success": False,
            "task_type": task_type,
            "commands_total": 0,
            "commands_submitted": 0,
            "commands_effect_confirmed": 0,
            "commands_failed": 0,
            "command_submitted": False,
            "command_effect_confirmed": False,
            "command_statuses": [],
            "cmd": cmd,
            "params": params or {},
            "error": err_command_tracker_unavailable,
            "error_code": err_command_tracker_unavailable,
        }

    accepted_statuses = {
        str(status).strip().upper()
        for status in (accepted_terminal_statuses or ("DONE",))
        if str(status).strip()
    }
    if not accepted_statuses:
        accepted_statuses = {"DONE"}
    accepted_statuses.add("DONE")

    commands_total = 0
    commands_submitted = 0
    commands_effect_confirmed = 0
    commands_failed = 0
    first_failure_error_code: Optional[str] = None
    command_statuses: List[Dict[str, Any]] = []

    for node in nodes:
        node_uid = node["node_uid"]
        channel = node.get("channel") or "default"
        await emit_task_event_fn(
            zone_id=zone_id,
            task_type=task_type,
            context=context,
            event_type="COMMAND_DISPATCHED",
            payload={
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "params": params or {},
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": decision.reason_code,
                "dedupe_bypass": bool(dedupe_bypass),
            },
        )

        commands_total += 1
        controller_command = {
            "node_uid": node_uid,
            "channel": channel,
            "cmd": cmd,
            "params": params or {},
        }
        if dedupe_bypass:
            controller_command["dedupe_bypass"] = True

        submitted = False
        effect_confirmed = False
        terminal_status = "SEND_FAILED"
        failure_error_code = err_command_send_failed
        cmd_id: Optional[str] = None

        if task_execute_closed_loop_enforce and hasattr(publisher, "publish_controller_command_closed_loop"):
            closed_loop_result = await publisher.publish_controller_command_closed_loop(
                zone_id=zone_id,
                command=controller_command,
                context={
                    "task_id": context.get("task_id"),
                    "correlation_id": context.get("correlation_id"),
                    "task_type": task_type,
                    "reason_code": decision.reason_code,
                },
                timeout_sec=task_execute_closed_loop_timeout_sec,
            )
            submitted = bool(closed_loop_result.get("command_submitted"))
            effect_confirmed = bool(closed_loop_result.get("command_effect_confirmed"))
            terminal_status = str(closed_loop_result.get("terminal_status") or "ERROR").upper()
            cmd_id_raw = closed_loop_result.get("cmd_id")
            cmd_id = str(cmd_id_raw).strip() if isinstance(cmd_id_raw, str) and cmd_id_raw.strip() else None
            failure_error_code = terminal_status_to_error_code_fn(terminal_status)
            if submitted and terminal_status in accepted_statuses:
                effect_confirmed = True
                failure_error_code = ""
        elif task_execute_closed_loop_enforce:
            submitted = False
            effect_confirmed = False
            terminal_status = "TRACKER_UNAVAILABLE"
            failure_error_code = err_command_tracker_unavailable
        else:
            submitted = await publisher.publish_command(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                params=params or {},
            )
            effect_confirmed = bool(submitted)
            terminal_status = "DONE" if submitted else "SEND_FAILED"
            failure_error_code = terminal_status_to_error_code_fn(terminal_status)

        if submitted:
            commands_submitted += 1
        if effect_confirmed:
            commands_effect_confirmed += 1

        command_statuses.append(
            {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": cmd_id,
                "command_submitted": submitted,
                "command_effect_confirmed": effect_confirmed,
                "terminal_status": terminal_status,
                "terminal_status_accepted": terminal_status in accepted_statuses,
            }
        )

        if not effect_confirmed:
            commands_failed += 1
            if first_failure_error_code is None:
                first_failure_error_code = failure_error_code
            await emit_task_event_fn(
                zone_id=zone_id,
                task_type=task_type,
                context=context,
                event_type="COMMAND_FAILED",
                payload={
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "params": params or {},
                    "cmd_id": cmd_id,
                    "terminal_status": terminal_status,
                    "command_submitted": submitted,
                    "command_effect_confirmed": effect_confirmed,
                    "error_code": failure_error_code,
                    "action_required": decision.action_required,
                    "decision": decision.decision,
                    "reason_code": decision.reason_code,
                    "accepted_terminal_statuses": sorted(accepted_statuses),
                    "dedupe_bypass": bool(dedupe_bypass),
                },
            )

    success = commands_total > 0 and commands_effect_confirmed == commands_total and commands_failed == 0
    result = {
        "success": success,
        "task_type": task_type,
        "commands_total": commands_total,
        "commands_submitted": commands_submitted,
        "commands_effect_confirmed": commands_effect_confirmed,
        "commands_failed": commands_failed,
        "command_submitted": commands_total > 0 and commands_submitted == commands_total,
        "command_effect_confirmed": commands_total > 0 and commands_effect_confirmed == commands_total,
        "command_statuses": command_statuses,
        "cmd": cmd,
        "params": params or {},
    }
    if not success:
        result["error"] = first_failure_error_code or err_command_effect_not_confirmed
        result["error_code"] = first_failure_error_code or err_command_effect_not_confirmed
    return result


__all__ = ["publish_batch"]
