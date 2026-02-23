"""Zone runner registry for AE2-Lite."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional


class ZoneRegistry:
    def __init__(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}

    def get(self, zone_id: int) -> Optional[asyncio.Task]:
        return self._tasks.get(int(zone_id))

    def set(self, zone_id: int, task: asyncio.Task) -> None:
        self._tasks[int(zone_id)] = task

    def pop(self, zone_id: int) -> Optional[asyncio.Task]:
        return self._tasks.pop(int(zone_id), None)

    def active_zone_ids(self) -> list[int]:
        return sorted(self._tasks.keys())


__all__ = ["ZoneRegistry"]
