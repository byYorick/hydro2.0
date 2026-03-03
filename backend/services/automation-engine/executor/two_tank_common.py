"""Shared utilities for two-tank phase starters."""

from __future__ import annotations

from typing import Any


def resolve_primary_pump_channel(command_plan: Any) -> str:
    """Extract the first pump channel from a command plan list."""
    if isinstance(command_plan, list):
        for item in command_plan:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel") or "").strip().lower()
            if channel.startswith("pump"):
                return channel
    return "pump_main"


__all__ = ["resolve_primary_pump_channel"]
