"""Periodic reconcile poller for AE2-Lite."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional


PollFn = Callable[[], Awaitable[None]]


class ReconcilePoller:
    def __init__(self, *, interval_sec: float, poll_fn: PollFn):
        self._interval_sec = max(0.05, float(interval_sec))
        self._poll_fn = poll_fn
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(self._interval_sec)
            await self._poll_fn()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        if not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None


__all__ = ["ReconcilePoller"]
