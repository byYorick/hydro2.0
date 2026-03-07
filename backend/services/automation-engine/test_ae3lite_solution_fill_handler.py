"""Unit tests for SolutionFillCheckHandler.

Outcomes:
 1. Tank full + targets reached → solution_fill_stop_to_ready
 2. Tank full + targets not reached → enter_correction
 3. Deadline exceeded → solution_fill_timeout_stop
 4. Not full, no deadline → poll
 5. Tank full but min=0 → TaskExecutionError (sensor_state_inconsistent)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import StageDef


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "solution_max_sensor_labels": ["sol_max"],
    "solution_min_sensor_labels": ["sol_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "level_poll_interval_sec": 10,
    "irr_state_max_age_sec": 60,
    "target_ph": 6.0,
    "target_ec": 2.0,
    "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
    "correction": {"max_correction_attempts": 5, "stabilization_sec": 60},
}

STAGE_DEF = StageDef(
    "solution_fill_check", "solution_fill",
    workflow_phase="tank_filling",
    timeout_key="solution_fill_timeout_sec",
    has_correction=True,
    on_corr_success="solution_fill_stop_to_ready",
    on_corr_fail="solution_fill_stop_to_prepare",
)


def _make_task(*, deadline: datetime | None = None) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 4, "zone_id": 40, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k4", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "solution_fill_check", "workflow_phase": "tank_filling",
        "stage_deadline_at": deadline, "stage_retry_count": 0,
        "stage_entered_at": NOW - timedelta(minutes=5), "clean_fill_cycle": 1,
        "corr_step": None,
    })


class _MockPlan:
    def __init__(self, *, ph: float = 6.0, ec: float = 2.0):
        self.runtime = RUNTIME
        self.named_plans = {"irr_state_probe": [object()]}
        self.targets = {}
        self._ph = ph
        self._ec = ec


class _MockRuntimeMonitor:
    def __init__(
        self, *,
        sol_max_triggered: bool = False,
        sol_min_triggered: bool = True,
        ph: float = 6.0,
        ec: float = 2.0,
    ):
        self._levels = {"sol_max": sol_max_triggered, "sol_min": sol_min_triggered}
        self._ph = ph
        self._ec = ec

    async def read_latest_irr_state(self, *, zone_id, max_age_sec):
        return {
            "has_snapshot": True,
            "is_stale": False,
            "snapshot": {
                "valve_clean_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
        }

    async def read_level_switch(self, *, zone_id, sensor_labels, threshold, telemetry_max_age_sec):
        label = sensor_labels[0] if sensor_labels else ""
        triggered = self._levels.get(label, False)
        return {"has_level": True, "is_stale": False, "is_triggered": triggered}

    async def read_metric(self, *, zone_id, sensor_type, telemetry_max_age_sec):
        value = self._ph if sensor_type == "PH" else self._ec
        return {"has_value": True, "is_stale": False, "value": value}


class _MockGateway:
    async def run_batch(self, *, task, commands, now):
        return {"success": True, "error_code": None, "error_message": None}


def _make_handler(*, monitor=None, gateway=None) -> SolutionFillCheckHandler:
    return SolutionFillCheckHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway or _MockGateway(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_solution_fill_full_targets_reached():
    """Solution tank full + PH/EC within tolerance → stop fill → ready."""
    monitor = _MockRuntimeMonitor(
        sol_max_triggered=True, sol_min_triggered=True,
        ph=6.0, ec=2.0,
    )
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_stop_to_ready"


async def test_solution_fill_full_targets_not_reached_enter_correction():
    """Solution tank full + targets far off → enter correction cycle."""
    monitor = _MockRuntimeMonitor(
        sol_max_triggered=True, sol_min_triggered=True,
        ph=4.0, ec=0.5,  # way off target
    )
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    # Sensors were already activated by solution_fill_start, so we skip activate step
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.correction.return_stage_success == "solution_fill_stop_to_ready"
    assert outcome.correction.return_stage_fail == "solution_fill_stop_to_prepare"


async def test_solution_fill_deadline_timeout_stop():
    """Deadline passed, tank not yet full → solution_fill_timeout_stop."""
    deadline = NOW - timedelta(seconds=1)
    task = _make_task(deadline=deadline)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_timeout_stop"


async def test_solution_fill_poll_when_not_full():
    """Tank not full, no deadline → poll with poll_interval."""
    task = _make_task()
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10


async def test_solution_fill_sensor_inconsistency_raises():
    """Solution max=1 but min=0 → TaskExecutionError."""
    monitor = _MockRuntimeMonitor(sol_max_triggered=True, sol_min_triggered=False)
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"
