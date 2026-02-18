"""Helpers for two-tank command-plan execution core."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from domain.models.decision_models import DecisionOutcome

ResolveOnlineNodeForChannelFn = Callable[..., Awaitable[Optional[Dict[str, Any]]]]
PublishBatchFn = Callable[..., Awaitable[Dict[str, Any]]]


async def dispatch_two_tank_command_plan_core(
    *,
    zone_id: int,
    command_plan: Sequence[Dict[str, Any]],
    context: Dict[str, Any],
    decision: DecisionOutcome,
    resolve_online_node_for_channel_fn: ResolveOnlineNodeForChannelFn,
    publish_batch_fn: PublishBatchFn,
    err_two_tank_channel_not_found: str,
    err_two_tank_command_failed: str,
) -> Dict[str, Any]:
    if not command_plan:
        return {
            "success": True,
            "commands_total": 0,
            "commands_failed": 0,
            "commands_submitted": 0,
            "commands_effect_confirmed": 0,
            "command_statuses": [],
        }

    combined_statuses: List[Dict[str, Any]] = []
    commands_total = 0
    commands_failed = 0
    commands_submitted = 0
    commands_effect_confirmed = 0
    first_error_code: Optional[str] = None
    first_error: Optional[str] = None

    for entry in command_plan:
        channel = str(entry.get("channel") or "").strip().lower()
        cmd = str(entry.get("cmd") or "set_relay").strip() or "set_relay"
        params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
        allow_no_effect = bool(entry.get("allow_no_effect"))
        node_types = entry.get("node_types") if isinstance(entry.get("node_types"), Sequence) else ()
        node = await resolve_online_node_for_channel_fn(
            zone_id=zone_id,
            channel=channel,
            node_types=[str(item) for item in node_types],
        )
        if not node:
            commands_total += 1
            commands_failed += 1
            if first_error_code is None:
                first_error_code = err_two_tank_channel_not_found
                first_error = f"channel_not_found:{channel}"
            combined_statuses.append(
                {
                    "node_uid": None,
                    "channel": channel,
                    "cmd": cmd,
                    "command_submitted": False,
                    "command_effect_confirmed": False,
                    "terminal_status": "CHANNEL_NOT_FOUND",
                    "error_code": err_two_tank_channel_not_found,
                }
            )
            continue

        step_result = await publish_batch_fn(
            zone_id=zone_id,
            task_type="diagnostics",
            nodes=[node],
            cmd=cmd,
            params=params,
            context=context,
            decision=decision,
            accepted_terminal_statuses=("DONE", "NO_EFFECT") if allow_no_effect else ("DONE",),
        )
        commands_total += int(step_result.get("commands_total") or 0)
        commands_failed += int(step_result.get("commands_failed") or 0)
        commands_submitted += int(step_result.get("commands_submitted") or 0)
        commands_effect_confirmed += int(step_result.get("commands_effect_confirmed") or 0)
        combined_statuses.extend(step_result.get("command_statuses") or [])
        if not step_result.get("success") and first_error_code is None:
            first_error_code = str(step_result.get("error_code") or err_two_tank_command_failed)
            first_error = str(step_result.get("error") or err_two_tank_command_failed)

    result = {
        "success": commands_total > 0 and commands_failed == 0 and commands_effect_confirmed == commands_total,
        "commands_total": commands_total,
        "commands_failed": commands_failed,
        "commands_submitted": commands_submitted,
        "commands_effect_confirmed": commands_effect_confirmed,
        "command_statuses": combined_statuses,
    }
    if not result["success"]:
        result["error_code"] = first_error_code or err_two_tank_command_failed
        result["error"] = first_error or err_two_tank_command_failed
    return result


__all__ = ["dispatch_two_tank_command_plan_core"]
