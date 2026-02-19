"""Single publish gateway for command side-effects in automation-engine."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from decision_context import ContextLike


class CommandGateway:
    """Serialized per-zone gateway over CommandBus publish methods."""

    # Общий per-loop lock registry для всех инстансов gateway внутри процесса.
    _registry_guard = threading.Lock()
    _zone_locks_by_loop: Dict[int, Dict[int, asyncio.Lock]] = {}

    def __init__(self, command_bus: Any, *, enable_zone_lock: bool = True) -> None:
        self._command_bus = command_bus
        self._enable_zone_lock = bool(enable_zone_lock)

    @property
    def tracker(self) -> Any:
        return getattr(self._command_bus, "tracker", None)

    @classmethod
    def _get_zone_lock(cls, zone_id: int) -> asyncio.Lock:
        loop_id = id(asyncio.get_running_loop())
        with cls._registry_guard:
            loop_locks = cls._zone_locks_by_loop.get(loop_id)
            if loop_locks is None:
                loop_locks = {}
                cls._zone_locks_by_loop[loop_id] = loop_locks

            lock = loop_locks.get(zone_id)
            if lock is None:
                lock = asyncio.Lock()
                loop_locks[zone_id] = lock
            return lock

    async def _run_serialized(self, zone_id: int, publish_coro: Any) -> Any:
        if not self._enable_zone_lock:
            return await publish_coro
        async with self._get_zone_lock(zone_id):
            return await publish_coro

    async def publish_command(
        self,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        cmd_id: Optional[str] = None,
    ) -> bool:
        return await self._run_serialized(
            zone_id,
            self._command_bus.publish_command(
                zone_id,
                node_uid,
                channel,
                cmd,
                params,
                cmd_id=cmd_id,
            ),
        )

    async def publish_controller_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None,
    ) -> bool:
        return await self._run_serialized(
            zone_id,
            self._command_bus.publish_controller_command(zone_id, command, context),
        )

    async def publish_controller_command_closed_loop(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        return await self._run_serialized(
            zone_id,
            self._command_bus.publish_controller_command_closed_loop(
                zone_id=zone_id,
                command=command,
                context=context,
                timeout_sec=timeout_sec,
            ),
        )


__all__ = ["CommandGateway"]
