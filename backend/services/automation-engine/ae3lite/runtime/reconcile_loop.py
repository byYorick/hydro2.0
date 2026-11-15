"""Ordered reconcile ticks with wakeable polling and bounded failure backoff."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Sequence

from ae3lite.infrastructure.metrics import RECONCILE_CONSECUTIVE_ERRORS


class ReconcileLoop:
    """Owns loop/error state; individual reconciliation policies stay with the worker."""

    def __init__(
        self,
        *,
        steps: Sequence[Callable[[], Awaitable[None]]],
        is_stopping: Callable[[], bool],
        wake: asyncio.Event,
        poll_interval_sec: float,
        owner: str,
        logger: Any,
        log_debug: Callable[..., None],
    ) -> None:
        self._steps = tuple(steps)
        self._is_stopping = is_stopping
        self._wake = wake
        self._poll_interval_sec = poll_interval_sec
        self._owner = owner
        self._logger = logger
        self._log_debug = log_debug
        self.consecutive_errors = 0

    async def run(self) -> None:
        while not self._is_stopping():
            try:
                for step in self._steps:
                    await step()
                self.consecutive_errors = 0
                RECONCILE_CONSECUTIVE_ERRORS.set(0)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.consecutive_errors += 1
                RECONCILE_CONSECUTIVE_ERRORS.set(self.consecutive_errors)
                self._logger.warning(
                    "AE3 waiting_command reconcile loop failed: owner=%s consecutive_errors=%s",
                    self._owner,
                    self.consecutive_errors,
                    exc_info=True,
                )
            if self._is_stopping():
                break
            if self.consecutive_errors >= 3:
                exponent = self.consecutive_errors - 2
                sleep_sec = min(2**exponent, 30.0)
                self._log_debug(
                    "AE3 reconcile backoff sleep: owner=%s consecutive_errors=%s sleep_sec=%.1f",
                    self._owner,
                    self.consecutive_errors,
                    sleep_sec,
                )
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=sleep_sec)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                continue
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=self._poll_interval_sec,
                )
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
