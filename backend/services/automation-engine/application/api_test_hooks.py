"""Test hooks helpers for API layer decomposition."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from infrastructure import CommandBus


class TestHookRequest(BaseModel):
    """Request model for test hooks."""

    zone_id: int = Field(..., ge=1, description="Zone ID")
    controller: Optional[str] = Field(None, description="Controller name (climate, ph, ec, irrigation, etc.)")
    action: str = Field(..., description="Action: inject_error, clear_error, reset_backoff, set_state, publish_command")
    error_type: Optional[str] = Field(None, description="Error type for inject_error")
    state: Optional[Dict[str, Any]] = Field(None, description="State override for set_state")
    command: Optional[Dict[str, Any]] = Field(
        None,
        description="Command payload for publish_command: {node_uid, channel, cmd, params?, cmd_id?}",
    )


def parse_optional_datetime(value: Any, field_name: str) -> Optional[datetime]:
    """Normalize datetime override from JSON (None|ISO string|datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            return datetime.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid datetime format for '{field_name}': {value}",
            ) from exc
    raise HTTPException(
        status_code=400,
        detail=f"Field '{field_name}' must be null or ISO datetime string",
    )


def normalize_state_override(state: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce zone-state override payload to a safe internal format."""
    error_streak_raw = state.get("error_streak", 0)
    try:
        error_streak = int(error_streak_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Field 'error_streak' must be integer, got: {error_streak_raw}",
        ) from exc
    if error_streak < 0:
        raise HTTPException(status_code=400, detail="Field 'error_streak' must be >= 0")

    return {
        "error_streak": error_streak,
        "next_allowed_run_at": parse_optional_datetime(state.get("next_allowed_run_at"), "next_allowed_run_at"),
        "last_backoff_reported_until": parse_optional_datetime(
            state.get("last_backoff_reported_until"), "last_backoff_reported_until"
        ),
        "degraded_alert_active": bool(state.get("degraded_alert_active", False)),
        "last_missing_targets_report_at": parse_optional_datetime(
            state.get("last_missing_targets_report_at"), "last_missing_targets_report_at"
        ),
    }


async def handle_test_hook(
    req: TestHookRequest,
    *,
    test_mode: bool,
    test_hooks: Dict[int, Dict[str, Dict[str, Any]]],
    zone_states_override: Dict[int, Dict[str, Any]],
    logger: logging.Logger,
    command_bus: Optional[CommandBus],
    gh_uid: str,
    command_bus_cls: type[CommandBus] = CommandBus,
) -> Dict[str, Any]:
    if not test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled (AE_TEST_MODE=0)")

    zone_id = req.zone_id
    controller = req.controller
    action = req.action

    if action == "inject_error":
        if not controller or not req.error_type:
            raise HTTPException(status_code=400, detail="inject_error requires controller and error_type")

        if zone_id not in test_hooks:
            test_hooks[zone_id] = {}
        test_hooks[zone_id][controller] = {"error_type": req.error_type, "active": True}

        logger.info("[TEST_HOOK] Injected error for zone %s, controller %s: %s", zone_id, controller, req.error_type)
        return {"status": "ok", "message": f"Error injected for zone {zone_id}, controller {controller}"}

    if action == "clear_error":
        if controller:
            if zone_id in test_hooks and controller in test_hooks[zone_id]:
                del test_hooks[zone_id][controller]
                if not test_hooks[zone_id]:
                    del test_hooks[zone_id]
        else:
            if zone_id in test_hooks:
                del test_hooks[zone_id]

        logger.info("[TEST_HOOK] Cleared errors for zone %s, controller %s", zone_id, controller or "all")
        return {"status": "ok", "message": f"Errors cleared for zone {zone_id}"}

    if action == "reset_backoff":
        zone_states_override[zone_id] = normalize_state_override({"error_streak": 0})
        logger.info("[TEST_HOOK] Reset backoff for zone %s", zone_id)
        return {"status": "ok", "message": f"Backoff reset for zone {zone_id}"}

    if action == "set_state":
        if not req.state:
            raise HTTPException(status_code=400, detail="set_state requires state")

        normalized_state = normalize_state_override(req.state)
        zone_states_override[zone_id] = normalized_state
        logger.info("[TEST_HOOK] Set state for zone %s: %s", zone_id, normalized_state)
        return {"status": "ok", "message": f"State set for zone {zone_id}"}

    if action == "publish_command":
        if not isinstance(req.command, dict):
            raise HTTPException(status_code=400, detail="publish_command requires command payload")

        node_uid = req.command.get("node_uid")
        channel = req.command.get("channel", "default")
        cmd = req.command.get("cmd")
        params = req.command.get("params") or {}
        cmd_id = req.command.get("cmd_id")

        if not isinstance(node_uid, str) or not node_uid.strip():
            raise HTTPException(status_code=400, detail="publish_command requires non-empty command.node_uid")
        if not isinstance(channel, str) or not channel.strip():
            raise HTTPException(status_code=400, detail="publish_command requires non-empty command.channel")
        if not isinstance(cmd, str) or not cmd.strip():
            raise HTTPException(status_code=400, detail="publish_command requires non-empty command.cmd")
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="publish_command requires object command.params")
        if cmd_id is not None and not isinstance(cmd_id, str):
            raise HTTPException(status_code=400, detail="publish_command requires string command.cmd_id")

        active_command_bus = command_bus
        temporary_command_bus: Optional[CommandBus] = None
        if active_command_bus is None:
            history_logger_url = os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
            history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
            greenhouse_uid = gh_uid or os.getenv("GREENHOUSE_UID", "gh-test-1")
            temporary_command_bus = command_bus_cls(
                mqtt=None,
                gh_uid=greenhouse_uid,
                history_logger_url=history_logger_url,
                history_logger_token=history_logger_token,
                enforce_node_zone_assignment=True,
            )
            try:
                await temporary_command_bus.start()
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"CommandBus init failed: {exc}") from exc
            active_command_bus = temporary_command_bus
            logger.info("[TEST_HOOK] Temporary CommandBus initialized for publish_command")

        try:
            published = await active_command_bus.publish_command(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                params=params,
                cmd_id=cmd_id,
            )
        finally:
            if temporary_command_bus is not None:
                try:
                    await temporary_command_bus.stop()
                except Exception:
                    logger.warning("[TEST_HOOK] Failed to stop temporary CommandBus", exc_info=True)

        logger.info(
            "[TEST_HOOK] publish_command for zone %s: cmd=%s node_uid=%s channel=%s published=%s",
            zone_id,
            cmd,
            node_uid,
            channel,
            published,
        )
        return {
            "status": "ok",
            "data": {
                "published": bool(published),
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "cmd_id": cmd_id,
            },
        }

    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


def build_test_hook_state_payload(
    zone_id: int,
    *,
    test_mode: bool,
    test_hooks: Dict[int, Dict[str, Dict[str, Any]]],
    zone_states_override: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    if not test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled")

    hooks = test_hooks.get(zone_id, {})
    state = zone_states_override.get(zone_id, {})
    return {
        "status": "ok",
        "data": {
            "zone_id": zone_id,
            "hooks": hooks,
            "state_override": state,
        },
    }


def get_test_hook_for_zone(
    zone_id: int,
    controller: str,
    *,
    test_mode: bool,
    test_hooks: Dict[int, Dict[str, Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    if not test_mode:
        return None
    return test_hooks.get(zone_id, {}).get(controller)


def get_zone_state_override(
    zone_id: int,
    *,
    test_mode: bool,
    zone_states_override: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not test_mode:
        return None
    return zone_states_override.get(zone_id)


__all__ = [
    "TestHookRequest",
    "build_test_hook_state_payload",
    "get_test_hook_for_zone",
    "get_zone_state_override",
    "handle_test_hook",
    "normalize_state_override",
    "parse_optional_datetime",
]
