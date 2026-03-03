"""CommandBus controller-oriented flows."""

import logging
from typing import Any, Dict, Optional

from common.commands import new_command_id
from common.simulation_events import record_simulation_event
from decision_context import ContextLike, normalize_context

from .command_bus_shared import _DEFAULT_CLOSED_LOOP_TIMEOUT_SEC, _TERMINAL_COMMAND_STATUSES, COMMAND_VALIDATION_FAILED

logger = logging.getLogger(__name__)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


async def publish_controller_command(
    command_bus: Any,
    zone_id: int,
    command: Dict[str, Any],
    context: ContextLike = None,
) -> bool:
    node_uid = command.get("node_uid")
    channel = command.get("channel", "default")
    cmd = command.get("cmd")
    params = command.get("params")
    incoming_cmd_id_raw = command.get("cmd_id")
    incoming_cmd_id = str(incoming_cmd_id_raw).strip() if isinstance(incoming_cmd_id_raw, str) else None
    if incoming_cmd_id == "":
        incoming_cmd_id = None
    dedupe_bypass = _is_truthy(command.get("dedupe_bypass"))
    cmd_id = None
    normalized_context = normalize_context(context)

    if not node_uid or not cmd:
        logger.warning("Zone %s: Invalid command structure - missing node_uid or cmd", zone_id)
        return False

    is_valid, error = command_bus.validator.validate_command(command)
    if not is_valid:
        COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason=error or "unknown").inc()
        logger.error(
            "Zone %s: Command validation failed: %s",
            zone_id,
            error,
            extra={
                "zone_id": zone_id,
                "command": command,
                "validation_error": error,
            },
        )
        await command_bus._safe_create_zone_event(
            zone_id,
            "COMMAND_VALIDATION_FAILED",
            {
                "command": command,
                "error": error,
            },
        )
        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_validate",
            status="validation_failed",
            level="warning",
            message="Команда не прошла валидацию",
            payload={
                "command": command,
                "error": error,
            },
        )
        return False

    dedupe_ttl_sec = command_bus._resolve_dedupe_ttl_sec(params)
    generated_cmd_id = incoming_cmd_id
    if generated_cmd_id is None and command_bus.tracker is not None:
        generated_cmd_id = new_command_id()

    if dedupe_bypass:
        dedupe_state = {
            "decision": "bypass",
            "reference_key": "",
            "scope_key": "",
            "dedupe_ttl_sec": dedupe_ttl_sec,
            "reservation_token": None,
            "effective_cmd_id": generated_cmd_id,
        }
        await command_bus._safe_create_zone_event(
            zone_id,
            "COMMAND_DEDUPE_BYPASSED",
            {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": generated_cmd_id,
                "reason": "explicit_bypass_flag",
            },
        )
    else:
        dedupe_state = await command_bus._reserve_command_dedupe(
            zone_id=zone_id,
            node_uid=str(node_uid),
            channel=str(channel),
            cmd=str(cmd),
            params=params if isinstance(params, dict) else {},
            cmd_id=generated_cmd_id,
            dedupe_ttl_sec=dedupe_ttl_sec,
            idempotency_key=str(command.get("idempotency_key") or "").strip() or None,
        )
    dedupe_decision = str(dedupe_state.get("decision") or "new").strip().lower()
    dedupe_reference_key = str(dedupe_state.get("reference_key") or "").strip()
    dedupe_ttl_value = int(dedupe_state.get("dedupe_ttl_sec") or dedupe_ttl_sec)
    effective_cmd_id = str(dedupe_state.get("effective_cmd_id") or generated_cmd_id or "").strip() or None

    command["dedupe_decision"] = dedupe_decision
    command["dedupe_reference_key"] = dedupe_reference_key
    command["dedupe_ttl_sec"] = dedupe_ttl_value
    command["dedupe_bypass"] = dedupe_bypass

    if dedupe_decision in {"duplicate_blocked", "duplicate_no_effect"}:
        if effective_cmd_id:
            command["cmd_id"] = effective_cmd_id
        cmd_id = effective_cmd_id
        await command_bus._safe_create_zone_event(
            zone_id,
            "COMMAND_DEDUPE_SKIPPED",
            {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": effective_cmd_id,
                "dedupe_decision": dedupe_decision,
                "dedupe_reference_key": dedupe_reference_key,
                "dedupe_ttl_sec": dedupe_ttl_value,
            },
        )
        success = True
    else:
        cmd_id = None
        if command_bus.tracker:
            try:
                cmd_id = await command_bus.tracker.track_command(
                    zone_id,
                    command,
                    normalized_context,
                    cmd_id=generated_cmd_id,
                )
                command["cmd_id"] = cmd_id
                await command_bus._bind_dedupe_cmd_id(dedupe_state, cmd_id)
            except Exception as exc:
                logger.warning("Zone %s: Failed to track command: %s", zone_id, exc, exc_info=True)
                await command_bus._complete_command_dedupe(dedupe_state, success=False)
                params = command.get("params")
                cmd_id = None
                command.pop("cmd_id", None)
                return False
        else:
            cmd_id = incoming_cmd_id
            if cmd_id:
                command["cmd_id"] = cmd_id
                await command_bus._bind_dedupe_cmd_id(dedupe_state, cmd_id)

        success = await command_bus.publish_command(
            zone_id,
            node_uid,
            channel,
            cmd,
            params,
            cmd_id=cmd_id,
            dedupe_state=dedupe_state,
        )

    cmd_id = str(command.get("cmd_id") or cmd_id or "").strip() or None

    try:
        await command_bus.audit.audit_command(zone_id, command, normalized_context)
    except Exception as exc:
        logger.warning("Zone %s: Failed to audit command: %s", zone_id, exc, exc_info=True)

    if not success and cmd_id and command_bus.tracker:
        await command_bus.tracker.confirm_command_status(cmd_id, "SEND_FAILED", error="publish_failed")

    return success


async def publish_controller_command_closed_loop(
    command_bus: Any,
    zone_id: int,
    command: Dict[str, Any],
    context: ContextLike = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    effective_timeout = float(timeout_sec) if timeout_sec is not None else _DEFAULT_CLOSED_LOOP_TIMEOUT_SEC
    effective_timeout = max(1.0, effective_timeout)
    tracker = command_bus.tracker
    result: Dict[str, Any] = {
        "command_submitted": False,
        "command_effect_confirmed": False,
        "terminal_status": None,
        "cmd_id": None,
        "error_code": None,
        "error": None,
    }
    node_uid = str(command.get("node_uid") or "").strip() or "unknown"
    channel = str(command.get("channel") or "").strip() or "default"
    cmd = str(command.get("cmd") or "").strip() or "unknown"

    submitted = await command_bus.publish_controller_command(zone_id, command, context)
    cmd_id = str(command.get("cmd_id") or "").strip() or None
    dedupe_decision = str(command.get("dedupe_decision") or "").strip().lower()
    result["command_submitted"] = bool(submitted)
    result["cmd_id"] = cmd_id

    if not submitted:
        await _finish_not_confirmed(
            command_bus,
            result,
            zone_id=zone_id,
            cmd_id=cmd_id,
            cmd=cmd,
            node_uid=node_uid,
            channel=channel,
            terminal_status="SEND_FAILED",
            reason="publish_failed",
            error="publish_failed",
        )
        return result

    if dedupe_decision == "duplicate_no_effect":
        if tracker is None or cmd_id is None:
            result["command_effect_confirmed"] = True
            result["terminal_status"] = "NO_EFFECT"
            return result
        terminal_status_raw = await tracker._get_command_status_from_db(cmd_id)  # noqa: SLF001
        normalized_status = str(terminal_status_raw or "").strip().upper()
        if normalized_status == "DONE":
            result["command_effect_confirmed"] = True
            result["terminal_status"] = "DONE"
            return result
        if normalized_status in _TERMINAL_COMMAND_STATUSES:
            await _finish_not_confirmed(
                command_bus,
                result,
                zone_id=zone_id,
                cmd_id=cmd_id,
                cmd=cmd,
                node_uid=node_uid,
                channel=channel,
                terminal_status=normalized_status,
                reason="terminal_status_not_done",
                error=f"command_terminal_status_{normalized_status.lower()}",
            )
            return result
        if cmd_id not in tracker.pending_commands:
            result["command_effect_confirmed"] = True
            result["terminal_status"] = "NO_EFFECT"
            return result

    if tracker is None or cmd_id is None:
        await _finish_not_confirmed(
            command_bus,
            result,
            zone_id=zone_id,
            cmd_id=cmd_id,
            cmd=cmd,
            node_uid=node_uid,
            channel=channel,
            terminal_status="TRACKER_UNAVAILABLE",
            reason="tracker_or_cmd_id_missing",
            error="command_tracker_required_for_closed_loop",
        )
        return result

    wait_result = await tracker.wait_for_command_done(
        cmd_id=cmd_id,
        timeout_sec=effective_timeout,
        poll_interval_sec=min(1.0, max(0.25, effective_timeout / 20.0)),
    )
    if wait_result is True:
        result["command_effect_confirmed"] = True
        result["terminal_status"] = "DONE"
        return result

    terminal_status = await tracker._get_command_status_from_db(cmd_id)  # noqa: SLF001
    normalized_status = str(terminal_status or "").strip().upper()

    if wait_result is None:
        if normalized_status == "DONE":
            result["command_effect_confirmed"] = True
            result["terminal_status"] = "DONE"
            return result
        if normalized_status not in _TERMINAL_COMMAND_STATUSES:
            normalized_status = "TIMEOUT"
        try:
            if normalized_status == "TIMEOUT":
                await tracker.confirm_command_status(cmd_id, "TIMEOUT", error="closed_loop_timeout")
        except Exception:
            logger.warning("Zone %s: failed to mark TIMEOUT for cmd_id=%s", zone_id, cmd_id, exc_info=True)

    if normalized_status not in _TERMINAL_COMMAND_STATUSES:
        normalized_status = "ERROR"

    await _finish_not_confirmed(
        command_bus,
        result,
        zone_id=zone_id,
        cmd_id=cmd_id,
        cmd=cmd,
        node_uid=node_uid,
        channel=channel,
        terminal_status=normalized_status,
        reason="terminal_status_not_done",
        error=f"command_terminal_status_{normalized_status.lower()}",
    )
    return result


async def _finish_not_confirmed(
    command_bus: Any,
    result: Dict[str, Any],
    *,
    zone_id: int,
    cmd_id: Optional[str],
    cmd: str,
    node_uid: str,
    channel: str,
    terminal_status: str,
    reason: str,
    error: str,
) -> None:
    result["terminal_status"] = terminal_status
    result["error_code"] = terminal_status
    result["error"] = error
    await command_bus._safe_create_zone_event(
        zone_id,
        "COMMAND_EFFECT_NOT_CONFIRMED",
        {
            "cmd_id": cmd_id,
            "cmd": cmd,
            "node_uid": node_uid,
            "channel": channel,
            "terminal_status": terminal_status,
            "reason": reason,
        },
    )
    await command_bus._emit_closed_loop_failure_alert(
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        cmd_id=cmd_id,
        terminal_status=terminal_status,
        error=error,
    )
