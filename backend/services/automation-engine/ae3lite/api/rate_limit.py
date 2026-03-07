"""Rate-limit policy for AE3-Lite ingress."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict


@dataclass
class SlidingWindowRateLimiter:
    max_requests: int
    window_sec: float
    now_fn: Callable[[], float] = time.monotonic
    _events: Dict[int, Deque[float]] = field(default_factory=dict)
    _last_sweep_ts: float = 0.0

    def check(self, *, zone_id: int, source: str = "") -> bool:
        del source
        if self.max_requests <= 0 or self.window_sec <= 0:
            return True
        key = int(zone_id)
        now = float(self.now_fn())
        if now - self._last_sweep_ts >= float(self.window_sec):
            self._sweep_stale(now)
            self._last_sweep_ts = now
        q = self._events.setdefault(key, deque())
        threshold = now - float(self.window_sec)
        while q and q[0] <= threshold:
            q.popleft()
        if not q:
            self._events.pop(key, None)
            q = self._events.setdefault(key, deque())
        if len(q) >= int(self.max_requests):
            return False
        q.append(now)
        return True

    def _sweep_stale(self, now: float) -> None:
        threshold = now - float(self.window_sec)
        stale_keys = []
        for key, queue in self._events.items():
            while queue and queue[0] <= threshold:
                queue.popleft()
            if not queue:
                stale_keys.append(key)
        for key in stale_keys:
            self._events.pop(key, None)


__all__ = ["SlidingWindowRateLimiter"]
