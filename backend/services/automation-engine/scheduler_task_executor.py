"""Public scheduler task executor API with explicit runtime wiring."""

from __future__ import annotations

from typing import Any, Dict, Optional

from application import scheduler_executor_impl as _impl
from application.scheduler_executor_wiring import (
    SchedulerExecutorRuntimeBindings,
    apply_scheduler_executor_runtime_bindings,
    build_scheduler_executor_runtime_bindings,
)

DecisionOutcome = _impl.DecisionOutcome

# Compatibility patch points used by tests and callers.
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


async def _fetch_runtime_binding(*args, **kwargs):
    return await fetch(*args, **kwargs)


async def _create_zone_event_runtime_binding(*args, **kwargs):
    return await create_zone_event(*args, **kwargs)


async def _send_infra_alert_runtime_binding(*args, **kwargs):
    return await send_infra_alert(*args, **kwargs)


async def _enqueue_internal_scheduler_task_runtime_binding(*args, **kwargs):
    return await enqueue_internal_scheduler_task(*args, **kwargs)


class SchedulerTaskExecutor(_impl.SchedulerTaskExecutor):
    """Compatibility wrapper with explicit runtime dependency wiring."""

    def __init__(
        self,
        command_bus: Any,
        zone_service: Optional[Any] = None,
        workflow_state_store: Optional[Any] = None,
        runtime_bindings: Optional[SchedulerExecutorRuntimeBindings] = None,
    ):
        super().__init__(
            command_bus=command_bus,
            zone_service=zone_service,
            workflow_state_store=workflow_state_store,
        )
        bindings = runtime_bindings or build_scheduler_executor_runtime_bindings(
            fetch_fn=_fetch_runtime_binding,
            create_zone_event_fn=_create_zone_event_runtime_binding,
            send_infra_alert_fn=_send_infra_alert_runtime_binding,
            enqueue_internal_scheduler_task_fn=_enqueue_internal_scheduler_task_runtime_binding,
        )
        apply_scheduler_executor_runtime_bindings(self, bindings)

    async def execute(
        self,
        *,
        zone_id: int,
        task_type: str,
        payload: Dict[str, Any],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await _impl.policy_run_scheduler_executor_execute(
            executor=self,
            zone_id=zone_id,
            task_type=task_type,
            payload=payload,
            task_context=task_context,
            get_task_mapping_fn=_impl.get_task_mapping,
            send_infra_alert_fn=self.send_infra_alert_fn,
            log_structured_fn=_impl.log_structured,
            logger_obj=_impl.logger,
            auto_logic_climate_guards_v1=_impl.AUTO_LOGIC_CLIMATE_GUARDS_V1,
            auto_logic_extended_outcome_v1=_impl.AUTO_LOGIC_EXTENDED_OUTCOME_V1,
            workflow_phase_irrigating=_impl.WORKFLOW_PHASE_IRRIGATING,
        )


def create_scheduler_task_executor(
    *,
    command_bus: Any,
    zone_service: Optional[Any] = None,
    workflow_state_store: Optional[Any] = None,
    runtime_bindings: Optional[SchedulerExecutorRuntimeBindings] = None,
) -> SchedulerTaskExecutor:
    return SchedulerTaskExecutor(
        command_bus=command_bus,
        zone_service=zone_service,
        workflow_state_store=workflow_state_store,
        runtime_bindings=runtime_bindings,
    )


__all__ = [
    "DecisionOutcome",
    "SchedulerTaskExecutor",
    "SchedulerExecutorRuntimeBindings",
    "build_scheduler_executor_runtime_bindings",
    "create_scheduler_task_executor",
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
