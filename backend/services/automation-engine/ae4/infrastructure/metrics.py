"""Узкий набор метрик AE4 для алертов тишины, возраста задачи и lease."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

TICK_DURATION = Histogram(
    "ae4_tick_duration_seconds",
    "Длительность одного цикла воркера AE4",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

PENDING_TASKS = Gauge(
    "ae4_pending_tasks",
    "Число задач AE4 в статусе pending",
)

OLDEST_ACTIVE_TASK_AGE_SECONDS = Gauge(
    "ae4_oldest_active_task_age_seconds",
    "Возраст самой старой активной задачи AE4 (секунды)",
)

ZONE_LEASE_LOST = Counter(
    "ae4_zone_lease_lost_total",
    "Потери lease зоны AE4",
    ["zone_id"],
)

__all__ = [
    "TICK_DURATION",
    "PENDING_TASKS",
    "OLDEST_ACTIVE_TASK_AGE_SECONDS",
    "ZONE_LEASE_LOST",
]
