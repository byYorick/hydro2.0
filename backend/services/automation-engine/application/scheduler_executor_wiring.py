"""Manual wiring helpers for SchedulerTaskExecutor runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

AsyncCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class SchedulerExecutorRuntimeBindings:
    fetch_fn: AsyncCallable
    create_zone_event_fn: AsyncCallable
    send_infra_alert_fn: AsyncCallable
    enqueue_internal_scheduler_task_fn: AsyncCallable


def build_scheduler_executor_runtime_bindings(
    *,
    fetch_fn: AsyncCallable,
    create_zone_event_fn: AsyncCallable,
    send_infra_alert_fn: AsyncCallable,
    enqueue_internal_scheduler_task_fn: AsyncCallable,
) -> SchedulerExecutorRuntimeBindings:
    return SchedulerExecutorRuntimeBindings(
        fetch_fn=fetch_fn,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task_fn,
    )


def apply_scheduler_executor_runtime_bindings(
    executor: Any,
    bindings: SchedulerExecutorRuntimeBindings,
) -> None:
    executor.fetch_fn = bindings.fetch_fn
    executor.create_zone_event_fn = bindings.create_zone_event_fn
    executor.send_infra_alert_fn = bindings.send_infra_alert_fn
    executor.enqueue_internal_scheduler_task_fn = bindings.enqueue_internal_scheduler_task_fn


__all__ = [
    "SchedulerExecutorRuntimeBindings",
    "apply_scheduler_executor_runtime_bindings",
    "build_scheduler_executor_runtime_bindings",
]
