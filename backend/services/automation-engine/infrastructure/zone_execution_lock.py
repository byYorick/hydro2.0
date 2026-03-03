"""Per-zone asyncio execution lock for workflow serialization."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

_logger = logging.getLogger(__name__)
_zone_locks: Dict[int, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


async def _get_zone_lock(zone_id: int) -> asyncio.Lock:
    async with _registry_lock:
        if zone_id not in _zone_locks:
            _zone_locks[zone_id] = asyncio.Lock()
        return _zone_locks[zone_id]


@asynccontextmanager
async def zone_execution_context(
    zone_id: int,
    *,
    task_type: str = "unknown",
    workflow: str = "",
) -> AsyncIterator[None]:
    """Serialize workflow execution for a single zone_id within one process.

    NOTE: This is an in-process guard only. Multi-instance runtime requires
    distributed lock (see zone_execution_lock_pg.py).
    """
    lock = await _get_zone_lock(zone_id)
    if lock.locked():
        _logger.warning(
            "Zone %s: execution lock contention detected (task_type=%s workflow=%s) - waiting",
            zone_id,
            task_type,
            workflow or "<none>",
        )
    async with lock:
        yield


__all__ = ["zone_execution_context"]
