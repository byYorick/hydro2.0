"""Stage component: flow safety. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.stage_runtime_config import _MISSING_CONFIG
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.infrastructure.metrics import (
    EMERGENCY_STOP_RECONCILE,
    FAIL_SAFE_TRANSITION,
)
from common.service_logs import send_service_log

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageFlowSafetyPorts:
    require_runtime_plan: Callable[..., Any]
    run_command_batch_checked: Callable[..., Awaitable[Any]]
    probe_irr_state: Callable[..., Awaitable[Any]]
    read_level: Callable[..., Awaitable[Any]]
    runtime_config: Callable[[], Any]
    runtime_monitor: Callable[[], Any]
    stage_entered_at: Callable[..., Any]
    create_zone_event: Callable[..., Awaitable[Any]]


class StageFlowSafety:
    def __init__(self, ports: StageFlowSafetyPorts) -> None:
        self._ports = ports

    def _require_runtime_plan(self, **kwargs):
        return self._ports.require_runtime_plan(**kwargs)

    async def _run_command_batch_checked(self, **kwargs):
        return await self._ports.run_command_batch_checked(**kwargs)

    async def _probe_irr_state(self, **kwargs):
        return await self._ports.probe_irr_state(**kwargs)

    async def handle_control_mode_flow_path_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        control_mode: str,
        reason: str = "control_mode_manual",
    ) -> StageOutcome | None:
        from ae3lite.application.handlers.flow_path_guard import (
            handle_control_mode_flow_path_interrupt,
        )

        return await handle_control_mode_flow_path_interrupt(
            self,
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
            reason=reason,
        )

    async def ensure_flow_path_stopped(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        stage: str,
        reason: str,
    ) -> Any:
        from ae3lite.application.handlers.flow_path_guard import ensure_flow_stopped

        return await ensure_flow_stopped(
            self,
            task=task,
            plan=plan,
            now=now,
            stage=stage,
            reason=reason,
        )

    async def read_recent_storage_event(
        self,
        *,
        task: Any,
        event_types: Sequence[str],
        max_age_sec: int = 3600,  # config-literal: default recent-event lookup window
    ) -> Mapping[str, Any] | None:
        read_latest_zone_event = getattr(self._ports.runtime_monitor(), "read_latest_zone_event", None)
        if not callable(read_latest_zone_event):
            return None
        return await read_latest_zone_event(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            event_types=event_types,
            max_age_sec=max_age_sec,
            since_ts=self._ports.stage_entered_at(task=task),
            channel="storage_state",
        )

    def storage_event_payload(self, event: Mapping[str, Any] | None) -> Mapping[str, Any]:
        payload = event.get("payload") if isinstance(event, Mapping) else None
        return payload if isinstance(payload, Mapping) else {}

    def task_topology(self, *, task: Any) -> str:
        return str(getattr(task, "topology", "") or "").strip()

    def task_stage(self, *, task: Any) -> str:
        workflow = getattr(task, "workflow", None)
        return str(getattr(workflow, "current_stage", None) or getattr(task, "current_stage", None) or "").strip()

    def observe_fail_safe_transition(
        self,
        *,
        task: Any,
        reason: str,
        source: str,
        next_stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        topology = self.task_topology(task=task)
        stage = self.task_stage(task=task)
        FAIL_SAFE_TRANSITION.labels(
            topology=topology,
            stage=stage or "unknown",
            reason=str(reason or "unknown"),
            source=str(source or "unknown"),
        ).inc()
        context = {
            "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
            "task_id": int(getattr(task, "id", 0) or 0) or None,
            "topology": topology or None,
            "stage": stage or None,
            "reason": str(reason or "unknown"),
            "source": str(source or "unknown"),
            "next_stage": str(next_stage or "unknown"),
        }
        if isinstance(details, Mapping):
            context.update({str(k): v for k, v in details.items()})
        send_service_log(
            service="automation-engine",
            level="warning",
            message="AE3 fail-safe transition selected",
            context=context,
        )

    async def reconcile_recent_emergency_stop(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        event = await self.read_recent_storage_event(
            task=task,
            event_types=("EMERGENCY_STOP_ACTIVATED",),
            max_age_sec=86400,  # config-literal: one-day ESTOP replay window
        )
        if not isinstance(event, Mapping):
            return

        probe_error: str | None = None
        try:
            await self._ports.probe_irr_state(task=task, plan=plan, now=now, expected=expected)
        except TaskExecutionError as exc:
            probe_error = str(exc)

        EMERGENCY_STOP_RECONCILE.labels(
            topology=self.task_topology(task=task),
            stage=self.task_stage(task=task) or "unknown",
            outcome="failed",
        ).inc()
        send_service_log(
            service="automation-engine",
            level="error",
            message="AE3 emergency-stop fail-closed",
            context={
                "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                "task_id": int(getattr(task, "id", 0) or 0) or None,
                "topology": self.task_topology(task=task) or None,
                "stage": self.task_stage(task=task) or None,
                "error_code": "emergency_stop_activated",
                "error_message": probe_error,
            },
        )
        detail = (
            f"Физический E-Stop активирован: {probe_error}"
            if probe_error
            else "Физический E-Stop активирован; автоматика не продолжает stage после аварийного стопа"
        )
        raise TaskExecutionError("emergency_stop_activated", detail)

    async def check_solution_change_abort(
        self,
        *,
        task: Any,
        pending_manual_step: str,
    ) -> StageOutcome | None:
        """Обрабатывает operator abort для task_type=solution_change."""
        if str(getattr(task, "task_type", "") or "").strip().lower() != "solution_change":
            return None
        from ae3lite.application.use_cases.manual_control_contract import SOLUTION_CHANGE_ABORT_STEP

        if str(pending_manual_step or "").strip() != SOLUTION_CHANGE_ABORT_STEP:
            return None
        _logger.info(
            "solution_change: operator abort zone_id=%s task_id=%s stage=%s",
            task.zone_id,
            getattr(task, "id", None),
            getattr(task.workflow, "current_stage", None),
        )
        try:
            await self._ports.create_zone_event(
                int(task.zone_id),
                "SOLUTION_CHANGE_ABORTED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "zone_id": int(getattr(task, "zone_id", 0) or 0),
                    "stage": str(getattr(task.workflow, "current_stage", "") or ""),
                },
            )
        except Exception:
            _logger.warning(
                "solution_change_abort: не удалось записать SOLUTION_CHANGE_ABORTED zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
        return StageOutcome(kind="transition", next_stage="solution_change_abort_stop")

    async def check_sensor_consistency(
        self,
        *,
        task: Any,
        runtime: Any,
        min_labels_key: str,
        min_unavailable_error: str,
        min_stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
    ) -> None:
        """Read min-level sensor and assert it's triggered (consistency with max)."""
        min_labels = self._ports.runtime_config().mapping_value(runtime, min_labels_key)
        if min_labels is _MISSING_CONFIG:
            raise TaskExecutionError(
                ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
                f"Отсутствует runtime.{min_labels_key}",
            )
        level = await self._ports.read_level(
            task=task,
            zone_id=task.zone_id,
            labels=min_labels,
            threshold=float(runtime.level_switch_on_threshold),
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error=min_unavailable_error,
            stale_error=min_stale_error,
            stale_recheck_delay_sec=stale_recheck_delay_sec,
            prefer_probe_snapshot=prefer_probe_snapshot,
        )
        if not level["is_triggered"]:
            raise TaskExecutionError(
                "sensor_state_inconsistent",
                f"Датчики бака противоречат друг другу: max=1 min=0 ({min_labels_key})",
            )
