"""Helpers for irrigation pump actuation mode in AE3 workflow plans."""

from __future__ import annotations

from typing import Any, Mapping


def _irrigation_start_commands(plan: Any) -> tuple[Any, ...]:
    named = getattr(plan, "named_plans", None) or {}
    if not isinstance(named, Mapping):
        return ()
    commands = named.get("irrigation_start", ())
    return tuple(commands or ())


def irrigation_start_pump_main_command(plan: Any) -> Any | None:
    for command in _irrigation_start_commands(plan):
        channel = str(getattr(command, "channel", "") or "").strip().lower()
        if channel == "pump_main":
            return command
    return None


def irrigation_start_uses_timed_run_pump(plan: Any) -> bool:
    command = irrigation_start_pump_main_command(plan)
    if command is None:
        return False
    payload = getattr(command, "payload", None)
    if not isinstance(payload, Mapping):
        return False
    return str(payload.get("cmd") or "").strip().lower() == "run_pump"


def irrigation_start_uses_set_relay_pump(plan: Any) -> bool:
    command = irrigation_start_pump_main_command(plan)
    if command is None:
        return False
    payload = getattr(command, "payload", None)
    if not isinstance(payload, Mapping):
        return False
    return str(payload.get("cmd") or "").strip().lower() == "set_relay"
