"""IrrigationCheckHandler timing: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import _utc_naive_dt
from ae3lite.application.services.irrigation_check_shared import _IRRIGATION_DURATION_MAX_SEC
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.irrigation_actuation import (
    irrigation_start_uses_set_relay_pump,
    irrigation_start_uses_timed_run_pump,
)


@dataclass(frozen=True)
class IrrigationCheckTimingPorts:
    runtime_monitor: Callable[[], Any]
    global_logger: Callable[..., Any]


class IrrigationCheckTiming:
    def __init__(self, ports: IrrigationCheckTimingPorts) -> None:
        self._ports = ports

    def resolve_irrigation_duration_sec(self, *, task: Any, runtime: Any) -> int:
        raw = getattr(task, "irrigation_requested_duration_sec", None)
        if raw is None:
            execution = getattr(runtime, "irrigation_execution", None)
            raw = getattr(execution, "duration_sec", None) if execution is not None else None
        if raw is not None:
            try:
                return max(1, min(_IRRIGATION_DURATION_MAX_SEC, int(raw)))
            except (TypeError, ValueError) as exc:
                raise TaskExecutionError(
                    "irrigation_duration_unconfigured",
                    "Не задана длительность полива "
                    "(irrigation_requested_duration_sec или irrigation_execution.duration_sec).",
                ) from exc

        workflow = getattr(task, "workflow", None)
        deadline = getattr(workflow, "stage_deadline_at", None) if workflow is not None else None
        entered = getattr(workflow, "stage_entered_at", None) if workflow is not None else None
        if isinstance(deadline, datetime) and isinstance(entered, datetime):
            derived_sec = int((_utc_naive_dt(deadline) - _utc_naive_dt(entered)).total_seconds())
            if derived_sec >= 1:
                return min(_IRRIGATION_DURATION_MAX_SEC, derived_sec)

        raise TaskExecutionError(
            "irrigation_duration_unconfigured",
            "Не задана длительность полива (irrigation_requested_duration_sec или irrigation_execution.duration_sec).",
        )

    def resolve_irrigation_pump_stop_at(
        self,
        *,
        task: Any,
        runtime: Any,
        plan: Any,
        requested_sec: int,
    ) -> datetime | None:
        if irrigation_start_uses_timed_run_pump(plan):
            return None

        deadline = getattr(task.workflow, "stage_deadline_at", None)
        if not isinstance(deadline, datetime):
            return None

        if irrigation_start_uses_set_relay_pump(plan):
            deadline_naive = _utc_naive_dt(deadline)
            entered = getattr(task.workflow, "stage_entered_at", None)
            if isinstance(entered, datetime):
                entered_stop = _utc_naive_dt(entered) + timedelta(seconds=requested_sec)
                return min(deadline_naive, entered_stop)
            return deadline_naive

        entered = getattr(task.workflow, "stage_entered_at", None)
        if not isinstance(entered, datetime):
            return None
        return _utc_naive_dt(entered) + timedelta(seconds=requested_sec)

    async def maybe_stop_continuous_pump_after_duration(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
        observe_duration: Any,
    ) -> StageOutcome | None:
        if not irrigation_start_uses_set_relay_pump(plan):
            return None

        requested_sec = self.resolve_irrigation_duration_sec(task=task, runtime=runtime)
        pump_stop_at = self.resolve_irrigation_pump_stop_at(
            task=task,
            runtime=runtime,
            plan=plan,
            requested_sec=requested_sec,
        )
        if pump_stop_at is None:
            return None

        if _utc_naive_dt(now) < pump_stop_at:
            return None

        state = await self._ports.runtime_monitor().read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=int(runtime.irr_state_max_age_sec),
            expected_cmd_id=None,
        )
        snapshot = state.get("snapshot") if isinstance(state, Mapping) else None
        if not isinstance(snapshot, Mapping) or not bool(snapshot.get("pump_main")):
            return None

        elapsed_sec = max(0.0, (_utc_naive_dt(now) - pump_stop_at).total_seconds())
        self._ports.global_logger().info(
            "irrigation_check: requested duration elapsed, stopping continuous pump zone_id=%s task_id=%s elapsed_sec=%.1f requested_sec=%s",
            task.zone_id,
            getattr(task, "id", None),
            elapsed_sec,
            requested_sec,
        )
        observe_duration("duration_cap")
        return StageOutcome(kind="transition", next_stage="irrigation_pump_stop")
