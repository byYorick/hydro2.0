"""Unit tests for CleanFillCheckHandler.

Outcomes under test:
1. Tank full → clean_fill_stop_to_solution  (+ sensor consistency check)
2. Deadline exceeded + retries available → clean_fill_retry_stop (cycle+1)
3. Deadline exceeded + no retries → clean_fill_timeout_stop
4. Still filling → poll with level_poll_interval_sec
5. Level unavailable → TaskExecutionError
6. Level stale → TaskExecutionError
7. Sensor inconsistency (max=1, min=0) → TaskExecutionError
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 3, 12, 10, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=1)

_RUNTIME = {
    "clean_max_sensor_labels": ["clean_max"],
    "clean_min_sensor_labels": ["clean_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "level_poll_interval_sec": 15,
    "clean_fill_retry_cycles": 1,  # retry_limit = 1+1 = 2 → cycle < 2 means retry
}


def _make_task(*, deadline=FUTURE, cycle: int = 1) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 1, "zone_id": 10, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "clean_fill_check", "workflow_phase": "clean_fill",
        "stage_deadline_at": deadline, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": cycle, "corr_step": None,
    })


class _Monitor:
    def __init__(
        self,
        *,
        max_triggered: bool = False,
        min_triggered: bool = True,
        has_level: bool = True,
        is_stale: bool = False,
    ) -> None:
        self._max = {"has_level": has_level, "is_stale": is_stale, "is_triggered": max_triggered}
        self._min = {"has_level": has_level, "is_stale": is_stale, "is_triggered": min_triggered}
        self._call_count = 0

    async def read_level_switch(self, *, zone_id: int, sensor_labels: Any, **kw: Any) -> dict:
        self._call_count += 1
        # first call = clean_max, second = clean_min (consistency check)
        return self._max if self._call_count <= 1 else self._min

    async def read_latest_irr_state(self, **_kw: Any) -> dict:
        return {"has_snapshot": True, "is_stale": False, "snapshot": {}}

    async def read_metric(self, **_kw: Any) -> dict:
        return {"has_value": True, "is_stale": False, "value": 6.0}


class _Gateway:
    async def run_batch(self, **_kw: Any) -> dict:
        return {"success": True, "error_code": None, "error_message": None}


class _Plan:
    def __init__(self, runtime: dict | None = None) -> None:
        self.runtime = runtime or _RUNTIME
        self.named_plans: dict = {}


def _handler(monitor: _Monitor | None = None, gateway: _Gateway | None = None) -> CleanFillCheckHandler:
    return CleanFillCheckHandler(
        runtime_monitor=monitor or _Monitor(),
        command_gateway=gateway or _Gateway(),
    )


# ── 1. Tank full → stop_to_solution ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_tank_full_transitions_to_stop_to_solution() -> None:
    m = _Monitor(max_triggered=True, min_triggered=True)
    outcome = await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_stop_to_solution"


@pytest.mark.asyncio
async def test_tank_full_checks_sensor_consistency() -> None:
    m = _Monitor(max_triggered=True, min_triggered=False)  # inconsistent
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"


# ── 2. Deadline exceeded + retries available → retry_stop ────────────────────

@pytest.mark.asyncio
async def test_deadline_exceeded_with_retry_available() -> None:
    # cycle=1, retry_limit=2 → cycle < 2 → retry
    outcome = await _handler().run(task=_make_task(deadline=PAST, cycle=1), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_retry_stop"
    assert outcome.clean_fill_cycle == 2


@pytest.mark.asyncio
async def test_retry_increments_cycle() -> None:
    for initial_cycle in (1,):
        outcome = await _handler().run(
            task=_make_task(deadline=PAST, cycle=initial_cycle),
            plan=_Plan(), stage_def=None, now=NOW,
        )
        assert outcome.clean_fill_cycle == initial_cycle + 1


# ── 3. Deadline exceeded + no retries → timeout_stop ─────────────────────────

@pytest.mark.asyncio
async def test_deadline_exceeded_no_retries_timeout_stop() -> None:
    # cycle=2, retry_limit=2 → cycle >= 2 → timeout
    outcome = await _handler().run(task=_make_task(deadline=PAST, cycle=2), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_timeout_stop"


@pytest.mark.asyncio
async def test_zero_retry_cycles_always_times_out() -> None:
    runtime = {**_RUNTIME, "clean_fill_retry_cycles": 0}  # retry_limit=1 → cycle=1 >= 1 → timeout
    outcome = await _handler().run(
        task=_make_task(deadline=PAST, cycle=1), plan=_Plan(runtime), stage_def=None, now=NOW,
    )
    assert outcome.next_stage == "clean_fill_timeout_stop"


# ── 4. Still filling → poll ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_still_filling_returns_poll() -> None:
    outcome = await _handler().run(task=_make_task(deadline=FUTURE), plan=_Plan(), stage_def=None, now=NOW)
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 15  # level_poll_interval_sec


@pytest.mark.asyncio
async def test_poll_uses_default_interval_when_missing() -> None:
    runtime = {k: v for k, v in _RUNTIME.items() if k != "level_poll_interval_sec"}
    outcome = await _handler().run(task=_make_task(), plan=_Plan(runtime), stage_def=None, now=NOW)
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10  # default


# ── 5. Level unavailable ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_level_unavailable_raises() -> None:
    m = _Monitor(has_level=False)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "two_tank_clean_level_unavailable"


# ── 6. Level stale ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_level_stale_raises() -> None:
    m = _Monitor(is_stale=True)
    with pytest.raises(TaskExecutionError) as exc_info:
        await _handler(m).run(task=_make_task(), plan=_Plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "two_tank_clean_level_stale"


# ── deadline boundary (exactly at now) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_exactly_at_now_triggers_timeout() -> None:
    outcome = await _handler().run(
        task=_make_task(deadline=NOW, cycle=2), plan=_Plan(), stage_def=None, now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_timeout_stop"
