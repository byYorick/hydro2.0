"""Adapter around CommandBus for scheduler executor command publishing."""

from __future__ import annotations

from typing import Any, Dict


class CommandPublisher:
    """Thin adapter to keep command bus dependency explicit for application layer."""

    def __init__(self, command_bus: Any) -> None:
        self._command_bus = command_bus

    async def publish_closed_loop(self, **kwargs: Any) -> Dict[str, Any]:
        return await self._command_bus.publish_controller_command_closed_loop(**kwargs)

    async def publish_simple(self, **kwargs: Any) -> bool:
        return await self._command_bus.publish_command(**kwargs)
