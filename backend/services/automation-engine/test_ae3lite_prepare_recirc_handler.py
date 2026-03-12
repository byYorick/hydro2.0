"""Unit tests for PrepareRecircCheckHandler.

Outcomes:
 1. Deadline exceeded (check first) → prepare_recirculation_window_exhausted
 2. Targets reached → prepare_recirculation_stop_to_ready
 3. Targets not reached → enter_correction
 4. IRR state probe mismatch → TaskExecutionError
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import StageDef


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)

RUNTIME = {
    "telemetry_max_age_sec": 300,
    "level_poll_interval_sec": 10,
    "irr_state_max_age_sec": 60,
    "irr_state_wait_timeout_sec": 0.02,
    "irr_state_wait_poll_interval_sec": 0.005,
    "target_ph": 6.0,
    "target_ec": 2.0,
    "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
    "correction": {
        "max_ec_correction_attempts": 5,
        "max_ph_correction_attempts": 5,
        "prepare_recirculation_max_attempts": 3,
        "prepare_recirculation_max_correction_attempts": 32767,
        "stabilization_sec": 60,
    },
}

STAGE_DEF = StageDef(
    "prepare_recirculation_check", "prepare_recirc",
    workflow_phase="tank_recirc",
    timeout_key="prepare_recirculation_timeout_sec",
    has_correction=True,
    on_corr_success="prepare_recirculation_stop_to_ready",
    on_corr_fail="prepare_recirculation_window_exhausted",
)


def _make_task(*, deadline: datetime | None = None) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 5, "zone_id": 50, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k5", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "prepare_recirculation_check", "workflow_phase": "tank_recirc",
        "stage_deadline_at": deadline, "stage_retry_count": 0,
        "stage_entered_at": NOW - timedelta(minutes=10), "clean_fill_cycle": 1,
        "corr_step": None,
    })


class _MockPlan:
    def __init__(self, *, runtime_override: dict | None = None):
        self.runtime = deepcopy(RUNTIME)
        if runtime_override:
            self.runtime.update(runtime_override)
        self.named_plans = {"irr_state_probe": [object()]}
        self.targets = {}


class _MockRuntimeMonitor:
    def __init__(
        self, *,
        ph: float = 6.0,
        ec: float = 2.0,
        irr_match: bool = True,
        irr_states: list[dict] | None = None,
    ):
        self._ph = ph
        self._ec = ec
        self._irr_match = irr_match
        self._irr_states = list(irr_states or [])
        self.irr_reads = 0

    async def read_latest_irr_state(self, *, zone_id, max_age_sec):
        self.irr_reads += 1
        if self._irr_states:
            state = self._irr_states.pop(0)
            return dict(state)
        snapshot = {
            "valve_solution_supply": True,
            "valve_solution_fill": True,
            "pump_main": True,
        }
        if not self._irr_match:
            snapshot["pump_main"] = False  # mismatch
        return {"has_snapshot": True, "is_stale": False, "snapshot": snapshot}

    async def read_metric(self, *, zone_id, sensor_type, telemetry_max_age_sec):
        value = self._ph if sensor_type == "PH" else self._ec
        return {"has_value": True, "is_stale": False, "value": value}


class _MockGateway:
    async def run_batch(self, *, task, commands, now):
        return {"success": True, "error_code": None, "error_message": None}


def _make_handler(*, monitor=None, gateway=None) -> PrepareRecircCheckHandler:
    return PrepareRecircCheckHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway or _MockGateway(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_prepare_recirc_deadline_timeout_stop():
    """Deadline exceeded → prepare_recirculation_window_exhausted (checked before targets)."""
    deadline = NOW - timedelta(seconds=1)
    task = _make_task(deadline=deadline)
    handler = _make_handler()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 1


async def test_prepare_recirc_targets_reached():
    """PH/EC within tolerance → prepare_recirculation_stop_to_ready."""
    monitor = _MockRuntimeMonitor(ph=6.0, ec=2.0)
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


async def test_prepare_recirc_targets_not_reached_enter_correction():
    """Targets not met → enter correction with sensors_already_active=True."""
    monitor = _MockRuntimeMonitor(ph=4.0, ec=0.5)  # way off target
    handler = _make_handler(monitor=monitor)
    task = _make_task()
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.correction.activated_here is False  # sensors already active
    assert outcome.correction.return_stage_success == "prepare_recirculation_stop_to_ready"
    assert outcome.correction.return_stage_fail == "prepare_recirculation_window_exhausted"
    assert outcome.correction.ec_max_attempts == 5
    assert outcome.correction.ph_max_attempts == 5


async def test_prepare_recirc_probe_irr_mismatch_raises():
    """IRR state does not match expected → TaskExecutionError."""
    monitor = _MockRuntimeMonitor(irr_match=False)
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)
    assert exc_info.value.code == "irr_state_mismatch"


async def test_prepare_recirc_probe_waits_for_fresh_snapshot_after_stale_read():
    monitor = _MockRuntimeMonitor(
        ph=6.0,
        ec=2.0,
        irr_states=[
            {
                "has_snapshot": True,
                "is_stale": True,
                "snapshot": {
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            },
            {
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": {
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            },
        ],
    )
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"
    assert monitor.irr_reads >= 2


async def test_prepare_recirc_probe_stale_after_wait_still_fails_closed():
    monitor = _MockRuntimeMonitor(
        irr_states=[
            {
                "has_snapshot": True,
                "is_stale": True,
                "snapshot": {
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            },
            {
                "has_snapshot": True,
                "is_stale": True,
                "snapshot": {
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            },
        ],
    )
    handler = _make_handler(monitor=monitor)
    task = _make_task()

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_MockPlan(), stage_def=STAGE_DEF, now=NOW)
    assert exc_info.value.code == "irr_state_stale"
    assert monitor.irr_reads >= 2
