"""Stage component: deadlines. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


def _utc_naive_dt(dt: datetime) -> datetime:
    """Нормализует datetime к UTC-naive перед сравнениями."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageTimingPorts:
    irr_state_probe_retry_count: Callable[[], Any]
    irr_state_probe_retry_delay_sec: Callable[[], Any]
    runtime_config: Callable[[], Any]


class StageTiming:
    def __init__(self, ports: StageTimingPorts) -> None:
        self._ports = ports

    def deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        if deadline is None:
            return False
        return _utc_naive_dt(now) >= _utc_naive_dt(deadline)

    def stage_entered_at(self, *, task: Any) -> datetime | None:
        entered = getattr(getattr(task, "workflow", None), "stage_entered_at", None)
        return _utc_naive_dt(entered) if isinstance(entered, datetime) else None

    def stage_elapsed_ms(self, *, task: Any, now: datetime) -> int:
        entered = self.stage_entered_at(task=task)
        if entered is None:
            return 0
        return max(0, int((_utc_naive_dt(now) - entered).total_seconds() * 1000.0))

    def remaining_stage_time_sec(self, *, now: datetime, deadline: datetime | None) -> float | None:
        if deadline is None:
            return None
        remaining = (_utc_naive_dt(deadline) - _utc_naive_dt(now)).total_seconds()
        return max(0.0, remaining)

    def require_runtime_plan(self, *, plan: Any) -> RuntimePlan:
        runtime = getattr(plan, "runtime", None)
        if isinstance(runtime, RuntimePlan):
            return runtime
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            "Отсутствует typed RuntimePlan в command plan",
        )

    def irr_probe_deadline_budget_sec(self, *, runtime: RuntimePlan) -> float:
        # На реальном test-node roundtrip команды и состояния может занимать несколько секунд.
        # Если запускать новый IRR probe слишком близко к дедлайну stage, команда
        # может упасть уже на polling после дедлайна, а не пойти по ожидаемому stage path.
        wait_timeout = self._ports.runtime_config().coerce_float(runtime.irr_state_wait_timeout_sec)
        attempts = 1 + self._ports.irr_state_probe_retry_count()
        # Бюджет должен покрывать и roundtrip команды storage_state, и последующее
        # ожидание snapshot. На реальном железе этот путь легко превышает 5 с,
        # и для transient-потери MQTT probe допускается один republish.
        single_attempt_budget = (
            wait_timeout if wait_timeout is not None else 0.0
        ) + 2.0  # config-literal: fixed command roundtrip budget
        base_budget = (single_attempt_budget * attempts) + (
            self._ports.irr_state_probe_retry_delay_sec() * self._ports.irr_state_probe_retry_count()
        )
        return max(8.0, base_budget)  # config-literal: minimum safe IRR probe budget

    def deadline_too_close_for_irr_probe(
        self,
        *,
        now: datetime,
        deadline: datetime | None,
        runtime: RuntimePlan,
    ) -> bool:
        remaining = self.remaining_stage_time_sec(now=now, deadline=deadline)
        if remaining is None:
            return False
        return remaining <= self.irr_probe_deadline_budget_sec(runtime=runtime)
