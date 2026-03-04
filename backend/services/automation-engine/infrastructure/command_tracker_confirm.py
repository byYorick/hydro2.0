"""Confirmation and timeout helpers for CommandTracker."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from common.command_status_queue import send_status_to_laravel
from common.commands import mark_command_send_failed, mark_command_timeout
from common.db import create_zone_event


def _timeout_alert_state_maps(tracker: Any) -> tuple[Dict[int, bool], Dict[int, bool]]:
    active_map = getattr(tracker, "_timeout_alert_active_by_zone", None)
    if not isinstance(active_map, dict):
        active_map = {}
        setattr(tracker, "_timeout_alert_active_by_zone", active_map)

    probe_map = getattr(tracker, "_timeout_alert_probe_done_by_zone", None)
    if not isinstance(probe_map, dict):
        probe_map = {}
        setattr(tracker, "_timeout_alert_probe_done_by_zone", probe_map)

    return active_map, probe_map


async def emit_failure_alert_impl(
    tracker: Any,
    *,
    zone_id: int,
    cmd_id: str,
    status: str,
    command_info: Dict[str, Any],
    error: Optional[str],
) -> None:
    command = command_info.get("command") or {}
    node_uid = command.get("node_uid")
    channel = command.get("channel")
    cmd = command.get("cmd") or command_info.get("command_type")

    status_upper = str(status).upper()
    code_map = {
        "SEND_FAILED": ("infra_command_send_failed", "critical"),
        "TIMEOUT": ("infra_command_timeout", "critical"),
        "ERROR": ("infra_command_failed", "error"),
        "INVALID": ("infra_command_invalid", "error"),
        "BUSY": ("infra_command_busy", "warning"),
        "NO_EFFECT": ("infra_command_no_effect", "warning"),
    }
    code, severity = code_map.get(status_upper, ("infra_command_unknown_status", "error"))

    from common.infra_alerts import send_infra_alert

    await send_infra_alert(
        code=code,
        alert_type="Command Execution Failed",
        message=f"Команда {cmd or 'unknown'} завершилась со статусом {status_upper}: {error or status_upper}",
        severity=severity,
        zone_id=zone_id,
        service="automation-engine",
        component="command_tracker",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=status_upper,
        details={
            "cmd_id": cmd_id,
            "status": status_upper,
            "error_message": error,
        },
    )
    if status_upper == "TIMEOUT":
        active_map, probe_map = _timeout_alert_state_maps(tracker)
        active_map[int(zone_id)] = True
        probe_map[int(zone_id)] = True


async def persist_terminal_status_impl(
    tracker: Any,
    *,
    cmd_id: str,
    status: str,
    error: Optional[str],
) -> None:
    try:
        transitioned = False
        if status == "TIMEOUT":
            transitioned = await mark_command_timeout(cmd_id)
        elif status == "SEND_FAILED":
            transitioned = await mark_command_send_failed(cmd_id, error_message=error)

        if not transitioned:
            return

        command_info = tracker.pending_commands.get(cmd_id, {})
        command_payload = command_info.get("command")
        if not isinstance(command_payload, dict):
            command_payload = {}
        details = {
            "zone_id": command_info.get("zone_id"),
            "node_uid": command_payload.get("node_uid"),
            "channel": command_payload.get("channel"),
            "command": command_payload.get("cmd"),
            "source": "automation-engine",
            "status_origin": "command_tracker",
            "error_code": status,
            "error_message": error,
        }
        details = {k: v for k, v in details.items() if v is not None}
        await send_status_to_laravel(cmd_id, status, details)
    except Exception:
        tracker._logger.warning(
            "Failed to persist terminal status for cmd_id=%s status=%s",
            cmd_id,
            status,
            exc_info=True,
        )


async def confirm_command_internal_impl(
    tracker: Any,
    cmd_id: str,
    status: str,
    response: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    command_info = tracker.pending_commands.pop(cmd_id, None)
    if not command_info:
        tracker._logger.debug("Command %s not found in pending commands (may be already processed)", cmd_id)
        return

    zone_id = command_info["zone_id"]
    command_type = command_info["command_type"]

    timeout_task = tracker._timeout_tasks.pop(cmd_id, None)
    current_task = asyncio.current_task()
    if timeout_task is not None and timeout_task is not current_task and not timeout_task.done():
        timeout_task.cancel()

    success = status == "DONE"
    suppress_no_effect_alert = tracker._should_suppress_no_effect_alert(status, command_info)

    command_info["status"] = status
    command_info["completed_at"] = tracker._normalize_utc_datetime(tracker._utcnow())
    command_info["sent_at"] = tracker._normalize_utc_datetime(command_info.get("sent_at"))
    if response:
        command_info["response"] = response
    if error:
        command_info["error"] = error

    latency = (command_info["completed_at"] - command_info["sent_at"]).total_seconds()
    tracker._metrics["COMMAND_LATENCY"].labels(zone_id=str(zone_id), command_type=command_type).observe(latency)
    tracker._metrics["PENDING_COMMANDS"].labels(zone_id=str(zone_id)).dec()

    if success:
        tracker._metrics["COMMAND_SUCCESS"].labels(zone_id=str(zone_id), command_type=command_type).inc()
    else:
        reason = error or status
        tracker._metrics["COMMAND_FAILURE"].labels(
            zone_id=str(zone_id),
            command_type=command_type,
            reason=reason,
        ).inc()

    if success:
        active_map, probe_map = _timeout_alert_state_maps(tracker)
        zone_key = int(zone_id)
        timeout_alert_active = bool(active_map.get(zone_key))
        timeout_probe_done = bool(probe_map.get(zone_key))
        if timeout_alert_active or not timeout_probe_done:
            from common.infra_alerts import send_infra_resolved_alert

            command_payload = command_info.get("command")
            if not isinstance(command_payload, dict):
                command_payload = {}
            resolved = await send_infra_resolved_alert(
                code="infra_command_timeout",
                alert_type="Command Execution Timeout",
                message=f"Команда {command_type} восстановлена после timeout",
                zone_id=zone_id,
                service="automation-engine",
                component="command_tracker",
                node_uid=command_payload.get("node_uid"),
                channel=command_payload.get("channel"),
                cmd=command_payload.get("cmd") or command_type,
                details={
                    "recovered_cmd_id": cmd_id,
                    "recovered_status": status,
                    "recovery_probe": "cold_start" if not timeout_probe_done else "tracked",
                },
            )
            probe_map[zone_key] = True
            if resolved:
                active_map[zone_key] = False

        tracker._logger.info(
            "Zone %s: Command %s completed successfully (status: %s)",
            zone_id,
            cmd_id,
            status,
            extra={
                "zone_id": zone_id,
                "cmd_id": cmd_id,
                "command_type": command_type,
                "status": status,
                "latency": latency,
            },
        )
        return

    if suppress_no_effect_alert:
        tracker._logger.info(
            "Zone %s: Command %s completed with expected NO_EFFECT (command=%s)",
            zone_id,
            cmd_id,
            command_type,
            extra={
                "zone_id": zone_id,
                "cmd_id": cmd_id,
                "command_type": command_type,
                "status": status,
                "error": error,
                "latency": latency,
            },
        )
        return

    tracker._logger.warning(
        "Zone %s: Command %s failed (status: %s): %s",
        zone_id,
        cmd_id,
        status,
        error,
        extra={
            "zone_id": zone_id,
            "cmd_id": cmd_id,
            "command_type": command_type,
            "status": status,
            "error": error,
            "latency": latency,
        },
    )
    await tracker._emit_failure_alert(
        zone_id=zone_id,
        cmd_id=cmd_id,
        status=status,
        command_info=command_info,
        error=error,
    )


async def check_timeout_impl(tracker: Any, cmd_id: str) -> None:
    try:
        await asyncio.sleep(tracker.command_timeout)

        if cmd_id not in tracker.pending_commands:
            return

        command_info = tracker.pending_commands[cmd_id]
        db_status = await tracker._get_command_status_from_db(cmd_id)
        if db_status and db_status in ("DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"):
            normalized_status = str(db_status).upper()
            tracker._logger.debug(
                "Command %s already processed in DB (status: %s), confirming via tracker",
                cmd_id,
                normalized_status,
            )

            timeout_task = tracker._timeout_tasks.pop(cmd_id, None)
            current_task = asyncio.current_task()
            if timeout_task is not None and timeout_task is not current_task and not timeout_task.done():
                timeout_task.cancel()

            error = None
            if normalized_status in ("ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"):
                error = f"Command {normalized_status}"
            await tracker._confirm_command_internal(cmd_id, normalized_status, error=error)
            return

        if command_info["status"] not in ("QUEUED", "SENT", "ACK"):
            return

        zone_id = command_info["zone_id"]
        command_type = command_info["command_type"]
        tracker._logger.warning(
            "Zone %s: Command %s timed out after %ss (status: %s)",
            zone_id,
            cmd_id,
            tracker.command_timeout,
            command_info["status"],
            extra={
                "zone_id": zone_id,
                "cmd_id": cmd_id,
                "command_type": command_type,
                "timeout": tracker.command_timeout,
                "status": command_info["status"],
            },
        )

        tracker._metrics["COMMAND_TIMEOUT"].labels(zone_id=str(zone_id), command_type=command_type).inc()
        await tracker.confirm_command_status(cmd_id, "TIMEOUT", error="timeout")

        await create_zone_event(
            zone_id,
            "COMMAND_TIMEOUT",
            {
                "cmd_id": cmd_id,
                "command": command_info["command"],
                "timeout_seconds": tracker.command_timeout,
            },
        )
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        tracker._logger.error("Error in timeout check for command %s: %s", cmd_id, exc, exc_info=True)


async def wait_for_command_done_impl(
    tracker: Any,
    *,
    cmd_id: str,
    timeout_sec: Optional[float],
    poll_interval_sec: float,
) -> Optional[bool]:
    if timeout_sec is None:
        timeout_sec = tracker.command_timeout

    start_time = time.monotonic()
    while (time.monotonic() - start_time) < timeout_sec:
        db_status = await tracker._get_command_status_from_db(cmd_id)

        if db_status == "DONE":
            if cmd_id in tracker.pending_commands:
                await tracker._confirm_command_internal(cmd_id, db_status)
            return True

        if db_status in ("NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"):
            if cmd_id in tracker.pending_commands:
                await tracker._confirm_command_internal(cmd_id, db_status, error=f"Command {db_status}")
            return False

        await asyncio.sleep(poll_interval_sec)

    tracker._logger.warning("Timeout waiting for command %s to complete (waited %ss)", cmd_id, timeout_sec)
    return None


__all__ = [
    "check_timeout_impl",
    "confirm_command_internal_impl",
    "emit_failure_alert_impl",
    "persist_terminal_status_impl",
    "wait_for_command_done_impl",
]
