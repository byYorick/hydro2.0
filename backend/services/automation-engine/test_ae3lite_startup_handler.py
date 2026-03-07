"""Unit tests for StartupHandler.

Covers:
 - probe_irr_state (pump_main must be OFF)
 - clean tank full → transition to solution_fill_start
 - clean tank not full → transition to clean_fill_start (cycle=1)
 - sensor inconsistency (max=1, min=0) → TaskExecutionError
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.application.handlers.startup import StartupHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import TaskExecutionError


# ── Helpers ──────────────────────────────────────────────────────────────────

NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "clean_max_sensor_labels": ["clean_max"],
    "clean_min_sensor_labels": ["clean_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "irr_state_max_age_sec": 60,
}


def _make_task(zone_id: int = 10) -> AutomationTask:
    wf = WorkflowState(
        current_stage="startup",
        workflow_phase="idle",
        stage_deadline_at=None,
        stage_retry_count=0,
        stage_entered_at=None,
        clean_fill_cycle=0,
    )
    return AutomationTask.from_row({
        "id": 1, "zone_id": zone_id, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k1", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": None, "clean_fill_cycle": 0,
        "corr_step": None,
    })


class _MockPlan:
    def __init__(self, *, irr_snapshot: dict[str, bool] | None = None):
        self.runtime = RUNTIME
        self.named_plans = {"irr_state_probe": [object()]}
        self._irr_snapshot = irr_snapshot or {"pump_main": False}

    @property
    def targets(self):
        return {}


class _MockCommandGateway:
    def __init__(self, *, success: bool = True):
        self._success = success

    async def run_batch(self, *, task, commands, now):
        return {"success": self._success, "error_code": "fail", "error_message": "err"}


class _MockRuntimeMonitor:
    def __init__(
        self,
        *,
        irr_state: dict | None = None,
        clean_max_triggered: bool = False,
        clean_min_triggered: bool = True,
    ):
        self._irr_state = irr_state or {"pump_main": False}
        self._levels: dict[str, bool] = {
            "clean_max": clean_max_triggered,
            "clean_min": clean_min_triggered,
        }

    async def read_latest_irr_state(self, *, zone_id, max_age_sec):
        return {
            "has_snapshot": True,
            "is_stale": False,
            "snapshot": self._irr_state,
        }

    async def read_level_switch(self, *, zone_id, sensor_labels, threshold, telemetry_max_age_sec):
        label = sensor_labels[0] if sensor_labels else ""
        triggered = self._levels.get(label, False)
        return {"has_level": True, "is_stale": False, "is_triggered": triggered}


def _make_handler(*, gateway=None, monitor=None) -> StartupHandler:
    return StartupHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway or _MockCommandGateway(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_startup_clean_tank_not_full_routes_to_clean_fill():
    """Clean tank max sensor not triggered → transition to clean_fill_start, cycle=1."""
    handler = _make_handler(monitor=_MockRuntimeMonitor(clean_max_triggered=False))
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "clean_fill_start"
    assert outcome.clean_fill_cycle == 1


async def test_startup_clean_tank_full_routes_to_solution_fill():
    """Clean tank max AND min triggered → skip clean fill, go to solution_fill_start."""
    monitor = _MockRuntimeMonitor(clean_max_triggered=True, clean_min_triggered=True)
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_start"


async def test_startup_sensor_inconsistency_raises():
    """Clean max=1 but min=0 → TaskExecutionError (sensor_state_inconsistent)."""
    monitor = _MockRuntimeMonitor(clean_max_triggered=True, clean_min_triggered=False)
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "sensor_state_inconsistent"


async def test_startup_probe_failure_raises():
    """Probe command fails → TaskExecutionError from run_batch failure."""
    gateway = _MockCommandGateway(success=False)
    handler = _make_handler(gateway=gateway)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "fail"
