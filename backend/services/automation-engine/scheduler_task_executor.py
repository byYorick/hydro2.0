"""Public scheduler task executor API with compatibility exports."""

from __future__ import annotations

from application import scheduler_executor_impl as _impl

SchedulerTaskExecutor = _impl.SchedulerTaskExecutor
DecisionOutcome = _impl.DecisionOutcome

# Compatibility patch points used by existing tests and callers.
fetch = _impl.fetch
create_zone_event = _impl.create_zone_event
send_infra_alert = _impl.send_infra_alert
enqueue_internal_scheduler_task = _impl.enqueue_internal_scheduler_task

# Runtime flags exposed for backward-compatible monkeypatching.
AUTO_LOGIC_TANK_STATE_MACHINE_V1 = _impl.AUTO_LOGIC_TANK_STATE_MACHINE_V1
AE_LEGACY_WORKFLOW_DEFAULT_ENABLED = _impl.AE_LEGACY_WORKFLOW_DEFAULT_ENABLED
TELEMETRY_FRESHNESS_ENFORCE = _impl.TELEMETRY_FRESHNESS_ENFORCE
TELEMETRY_FRESHNESS_MAX_AGE_SEC = _impl.TELEMETRY_FRESHNESS_MAX_AGE_SEC
AE_TWOTANK_SAFETY_GUARDS_ENABLED = _impl.AE_TWOTANK_SAFETY_GUARDS_ENABLED


async def _fetch_proxy(*args, **kwargs):
    return await fetch(*args, **kwargs)


async def _create_zone_event_proxy(*args, **kwargs):
    return await create_zone_event(*args, **kwargs)


async def _send_infra_alert_proxy(*args, **kwargs):
    return await send_infra_alert(*args, **kwargs)


async def _enqueue_internal_scheduler_task_proxy(*args, **kwargs):
    return await enqueue_internal_scheduler_task(*args, **kwargs)


# Ensure executor implementation observes patched public symbols.
_impl.fetch = _fetch_proxy
_impl.create_zone_event = _create_zone_event_proxy
_impl.send_infra_alert = _send_infra_alert_proxy
_impl.enqueue_internal_scheduler_task = _enqueue_internal_scheduler_task_proxy


__all__ = [
    "DecisionOutcome",
    "SchedulerTaskExecutor",
    "fetch",
    "create_zone_event",
    "send_infra_alert",
    "enqueue_internal_scheduler_task",
    "AUTO_LOGIC_TANK_STATE_MACHINE_V1",
    "AE_LEGACY_WORKFLOW_DEFAULT_ENABLED",
    "TELEMETRY_FRESHNESS_ENFORCE",
    "TELEMETRY_FRESHNESS_MAX_AGE_SEC",
    "AE_TWOTANK_SAFETY_GUARDS_ENABLED",
]
