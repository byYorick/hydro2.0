"""Rate-limit policy for API endpoints."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Tuple


@dataclass
class SlidingWindowRateLimiter:
    max_requests: int
    window_sec: float
    now_fn: Callable[[], float] = time.monotonic
    _events: Dict[Tuple[int, str], Deque[float]] = field(default_factory=dict)

    def check(self, *, zone_id: int, source: str) -> bool:
        if self.max_requests <= 0 or self.window_sec <= 0:
            return True
        key = (int(zone_id), str(source or "").strip().lower())
        now = float(self.now_fn())
        q = self._events.setdefault(key, deque())
        threshold = now - float(self.window_sec)
        while q and q[0] <= threshold:
            q.popleft()
        if len(q) >= int(self.max_requests):
            return False
        q.append(now)
        return True


__all__ = ["SlidingWindowRateLimiter"]
