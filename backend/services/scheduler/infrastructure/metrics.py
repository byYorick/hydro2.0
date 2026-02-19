from __future__ import annotations

from typing import Any


def set_active_tasks(m: Any, count: int) -> None:
    m.SCHEDULER_ACTIVE_TASKS.set(count)


def inc_dispatch_skip(m: Any, reason: str) -> None:
    m.SCHEDULER_DISPATCH_SKIPS.labels(reason=reason).inc()
