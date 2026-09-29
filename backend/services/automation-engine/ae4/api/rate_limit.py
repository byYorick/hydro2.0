"""Rate limit для HTTP ingress AE 1.0.0."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable, Deque

_logger = logging.getLogger(__name__)


@dataclass
class SlidingWindowRateLimiter:
    max_requests: int
    window_sec: float
    max_keys: int = 10_000
    now_fn: Callable[[], float] = time.monotonic
    _events: OrderedDict[int, Deque[float]] = field(default_factory=OrderedDict)
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
        q = self._events.get(key)
        if q is None:
            if self.max_keys > 0 and len(self._events) >= self.max_keys:
                self._events.popitem(last=False)
            q = deque()
            self._events[key] = q
        else:
            self._events.move_to_end(key)
        threshold = now - float(self.window_sec)
        while q and q[0] <= threshold:
            q.popleft()
        if not q:
            self._events.pop(key, None)
            if self.max_keys > 0 and len(self._events) >= self.max_keys:
                self._events.popitem(last=False)
            q = deque()
            self._events[key] = q
        if len(q) >= int(self.max_requests):
            _logger.warning(
                "AE rate-limit: id=%s отклонено=%s/%s window=%s",
                zone_id,
                len(q),
                self.max_requests,
                self.window_sec,
            )
            return False
        q.append(now)
        self._events.move_to_end(key)
        return True

    def _sweep_stale(self, now: float) -> None:
        threshold = now - float(self.window_sec)
        stale = [k for k, queue in self._events.items() if not (queue and queue[-1] > threshold)]
        for key, queue in list(self._events.items()):
            while queue and queue[0] <= threshold:
                queue.popleft()
            if not queue:
                stale.append(key)
        for key in set(stale):
            self._events.pop(key, None)


__all__ = ["SlidingWindowRateLimiter"]
