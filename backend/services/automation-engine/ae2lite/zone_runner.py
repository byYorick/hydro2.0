"""Zone runner primitives for AE2-Lite."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


RunnerFn = Callable[[int], Awaitable[None]]


@dataclass
class ZoneRunner:
    zone_id: int
    runner_fn: RunnerFn
    task: Optional[asyncio.Task] = None

    def start(self) -> asyncio.Task:
        self.task = asyncio.create_task(self.runner_fn(self.zone_id))
        return self.task

    async def stop(self) -> None:
        if self.task is None:
            return
        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


__all__ = ["ZoneRunner"]
