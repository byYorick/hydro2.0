"""Политика rate limit для ingress AE3-Lite."""

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
            max_keys = int(self.max_keys)
            if max_keys > 0 and len(self._events) >= max_keys:
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
            max_keys = int(self.max_keys)
            if max_keys > 0 and len(self._events) >= max_keys:
                self._events.popitem(last=False)
            q = deque()
            self._events[key] = q
        if len(q) >= int(self.max_requests):
            _logger.warning(
                "AE3 rate-limit: zone_id=%s запросы отклонены=%s/%s window_sec=%s",
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
        stale_keys = []
        for key, queue in self._events.items():
            while queue and queue[0] <= threshold:
                queue.popleft()
            if not queue:
                stale_keys.append(key)
        for key in stale_keys:
            self._events.pop(key, None)


__all__ = ["SlidingWindowRateLimiter"]
