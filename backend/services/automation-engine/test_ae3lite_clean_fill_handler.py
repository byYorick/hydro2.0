"""Unit tests for CleanFillCheckHandler (4 outcomes + sensor consistency).

Outcomes:
 1. Tank full (max=1, min=1) → clean_fill_stop_to_solution
 2. Deadline exceeded + retry available → clean_fill_retry_stop (cycle+1)
 3. Deadline exceeded + max cycles reached → clean_fill_timeout_stop
 4. Not full, no deadline → poll
 5. Tank full but min=0 → TaskExecutionError (sensor_state_inconsistent)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.handlers.clean_fill import CleanFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "clean_max_sensor_labels": ["clean_max"],
    "clean_min_sensor_labels": ["clean_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "level_poll_interval_sec": 10,
    "clean_fill_retry_cycles": 1,  # max cycle=2 (1 initial + 1 retry)
}


def _make_task(
    *,
    clean_fill_cycle: int = 1,
    deadline: datetime | None = None,
) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 3, "zone_id": 30, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k3", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "clean_fill_check", "workflow_phase": "tank_filling",
        "stage_deadline_at": deadline, "stage_retry_count": 0,
        "stage_entered_at": NOW - timedelta(minutes=5), "clean_fill_cycle": clean_fill_cycle,
        "corr_step": None,
    })


class _MockPlan:
    def __init__(self, runtime: dict | None = None):
        self.runtime = runtime or RUNTIME
        self.named_plans = {}
        self.targets = {}


class _MockRuntimeMonitor:
    def __init__(self, *, clean_max_triggered: bool = False, clean_min_triggered: bool = True):
        self._levels = {"clean_max": clean_max_triggered, "clean_min": clean_min_triggered}

    async def read_level_switch(self, *, zone_id, sensor_labels, threshold, telemetry_max_age_sec):
        label = sensor_labels[0] if sensor_labels else ""
        triggered = self._levels.get(label, False)
        return {"has_level": True, "is_stale": False, "is_triggered": triggered}


def _make_handler(*, monitor=None) -> CleanFillCheckHandler:
    return CleanFillCheckHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=object(),  # not used by CleanFillCheckHandler
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_clean_fill_tank_full_routes_to_stop_solution():
    """Max and min both triggered → transition to clean_fill_stop_to_solution."""
    monitor = _MockRuntimeMonitor(clean_max_triggered=True, clean_min_triggered=True)
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_stop_to_solution"


async def test_clean_fill_deadline_retry_increments_cycle():
    """Deadline exceeded + cycle < retry limit → clean_fill_retry_stop with cycle+1."""
    deadline = NOW - timedelta(seconds=1)  # past deadline
    task = _make_task(clean_fill_cycle=1, deadline=deadline)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_retry_stop"
    assert outcome.clean_fill_cycle == 2  # incremented


async def test_clean_fill_deadline_max_cycles_terminal():
    """Deadline exceeded + cycle at retry limit → clean_fill_timeout_stop."""
    deadline = NOW - timedelta(seconds=1)
    # retry_cycles=1 → max cycle is 1+1=2; cycle=2 means exhausted
    task = _make_task(clean_fill_cycle=2, deadline=deadline)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_timeout_stop"


async def test_clean_fill_poll_when_not_full_no_deadline():
    """Not full, no deadline → poll with poll_interval."""
    task = _make_task()
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10  # level_poll_interval_sec


async def test_clean_fill_sensor_inconsistency_raises():
    """Tank max=1 but min=0 → TaskExecutionError (sensor_state_inconsistent)."""
    monitor = _MockRuntimeMonitor(clean_max_triggered=True, clean_min_triggered=False)
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"
