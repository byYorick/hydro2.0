"""IrrigationCheckHandler expected state: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.application.handlers.base import _utc_naive_dt
from ae3lite.domain.services.irrigation_actuation import (
    irrigation_start_uses_set_relay_pump,
    irrigation_start_uses_timed_run_pump,
)


@dataclass(frozen=True)
class IrrigationCheckExpectedStatePorts:
    resolve_irrigation_duration_sec: Callable[..., Any]
    resolve_irrigation_pump_stop_at: Callable[..., Any]


class IrrigationCheckExpectedState:
    def __init__(self, ports: IrrigationCheckExpectedStatePorts) -> None:
        self._ports = ports

    def resolve_expected_irrigation_state(
        self,
        *,
        task: Any,
        plan: Any,
        runtime: Any,
        now: datetime,
    ) -> dict[str, bool]:
        base = {
            "valve_solution_supply": True,
            "valve_irrigation": True,
        }
        if irrigation_start_uses_timed_run_pump(plan):
            return {**base, "pump_main": False}

        requested_sec = self._ports.resolve_irrigation_duration_sec(task=task, runtime=runtime)
        if irrigation_start_uses_set_relay_pump(plan):
            pump_stop_at = self._ports.resolve_irrigation_pump_stop_at(
                task=task,
                runtime=runtime,
                plan=plan,
                requested_sec=requested_sec,
            )
            if pump_stop_at is None:
                return {**base, "pump_main": True}

            now_naive = _utc_naive_dt(now)
            return {**base, "pump_main": now_naive < pump_stop_at}

        entered = getattr(task.workflow, "stage_entered_at", None)
        if not isinstance(entered, datetime):
            return {**base, "pump_main": True}

        elapsed = (_utc_naive_dt(now) - _utc_naive_dt(entered)).total_seconds()
        return {**base, "pump_main": elapsed < requested_sec}
