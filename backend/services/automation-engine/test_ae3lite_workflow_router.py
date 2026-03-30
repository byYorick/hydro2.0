"""Unit tests for WorkflowRouter (pure orchestrator).

Tests dispatch, outcome application, workflow phase updates, and
deadline computation — without real DB (all dependencies mocked).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import TopologyRegistry


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)
RUNTIME = {"solution_fill_timeout_sec": 3600, "clean_fill_timeout_sec": 1800}


# ── Task factory ────────────────────────────────────────────────────

def _make_task(
    *,
    stage: str = "startup",
    phase: str = "idle",
    task_type: str = "cycle_start",
    correction: CorrectionState | None = None,
    clean_fill_cycle: int = 0,
    stage_deadline_at: datetime | None = None,
    stage_entered_at: datetime | None = None,
    stage_retry_count: int = 0,
    control_mode: str = "auto",
    pending_manual_step: str | None = None,
    irrigation_requested_duration_sec: int | None = None,
) -> AutomationTask:
    corr_row: dict = {}
    if correction:
        corr_row = {
            "corr_step": correction.corr_step,
            "corr_attempt": correction.attempt,
            "corr_max_attempts": correction.max_attempts,
            "corr_ec_attempt": correction.ec_attempt,
            "corr_ec_max_attempts": correction.ec_max_attempts,
            "corr_ph_attempt": correction.ph_attempt,
            "corr_ph_max_attempts": correction.ph_max_attempts,
            "corr_activated_here": correction.activated_here,
            "corr_stabilization_sec": correction.stabilization_sec,
            "corr_return_stage_success": correction.return_stage_success,
            "corr_return_stage_fail": correction.return_stage_fail,
            "corr_outcome_success": correction.outcome_success,
            "corr_needs_ec": correction.needs_ec,
            "corr_ec_node_uid": correction.ec_node_uid,
            "corr_ec_channel": correction.ec_channel,
            "corr_ec_duration_ms": correction.ec_duration_ms,
            "corr_needs_ph_up": correction.needs_ph_up,
            "corr_needs_ph_down": correction.needs_ph_down,
            "corr_ph_node_uid": correction.ph_node_uid,
            "corr_ph_channel": correction.ph_channel,
            "corr_ph_duration_ms": correction.ph_duration_ms,
            "corr_wait_until": correction.wait_until,
        }
    else:
        corr_row = {"corr_step": None}

    return AutomationTask.from_row({
        "id": 99, "zone_id": 99, "task_type": task_type, "status": "running",
        "idempotency_key": "k99", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": stage, "workflow_phase": phase,
        "stage_deadline_at": stage_deadline_at, "stage_retry_count": stage_retry_count,
        "stage_entered_at": stage_entered_at or NOW, "clean_fill_cycle": clean_fill_cycle,
        "control_mode_snapshot": control_mode, "pending_manual_step": pending_manual_step,
        "irrigation_requested_duration_sec": irrigation_requested_duration_sec,
        **corr_row,
    })


class _MockPlan:
    def __init__(self, *, runtime: dict | None = None):
        self.runtime = runtime or RUNTIME
        self.named_plans: dict = {}
        self.targets: dict = {}


# ── Stubs ───────────────────────────────────────────────────────────

class _StubHandler:
    """Returns a fixed outcome when run() is called."""
    def __init__(self, outcome: StageOutcome):
        self._outcome = outcome

    async def run(self, *, task, plan, stage_def, now) -> StageOutcome:
        return self._outcome


class _MockTaskRepo:
    def __init__(self, *, return_task: AutomationTask | None = None, current_task: AutomationTask | None = None):
        self.update_stage_calls: list[dict] = []
        self.mark_completed_calls: list = []
        self.record_transition_calls: list[dict] = []
        self._return_task = return_task
        self._current_task = current_task

    async def update_stage(self, *, task_id, owner, workflow, correction, due_at, now):
        self.update_stage_calls.append({
            "task_id": task_id, "workflow": workflow, "correction": correction,
        })
        return self._return_task

    async def mark_completed(self, *, task_id, owner, now):
        self.mark_completed_calls.append(task_id)
        return self._return_task

    async def get_by_id(self, *, task_id):
        return self._current_task

    async def record_transition(self, *, task_id, from_stage, to_stage, workflow_phase, now, **kwargs):
        self.record_transition_calls.append({
            "from_stage": from_stage, "to_stage": to_stage, "phase": workflow_phase,
        })


class _MockWorkflowRepo:
    def __init__(self):
        self.upsert_calls: list[dict] = []

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        self.upsert_calls.append({"zone_id": zone_id, "phase": workflow_phase, "payload": payload})


class _MockRuntimeMonitor:
    pass


class _MockCommandGateway:
    pass


class _MetricRecorder:
    def __init__(self):
        self.calls: list[dict[str, str]] = []

    def labels(self, **labels):
        recorder = self

        class _Inc:
            def inc(self_inner):
                recorder.calls.append({key: str(value) for key, value in labels.items()})

        return _Inc()


def _make_router(
    *,
    task_repo: _MockTaskRepo | None = None,
    workflow_repo: _MockWorkflowRepo | None = None,
    startup_outcome: StageOutcome | None = None,
    clean_fill_outcome: StageOutcome | None = None,
    correction_outcome: StageOutcome | None = None,
    return_task: AutomationTask | None = None,
) -> tuple[WorkflowRouter, _MockTaskRepo, _MockWorkflowRepo]:
    tr = task_repo or _MockTaskRepo(return_task=return_task)
    wr = workflow_repo or _MockWorkflowRepo()
    registry = TopologyRegistry()
    router = WorkflowRouter(
        task_repository=tr,
        workflow_repository=wr,
        topology_registry=registry,
        runtime_monitor=_MockRuntimeMonitor(),
        command_gateway=_MockCommandGateway(),
    )
    # Inject stub handlers
    if startup_outcome:
        router._handlers["startup"] = _StubHandler(startup_outcome)
    if clean_fill_outcome:
        router._handlers["clean_fill"] = _StubHandler(clean_fill_outcome)
    if correction_outcome:
        router._handlers["correction"] = _StubHandler(correction_outcome)
    return router, tr, wr


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_router_dispatches_startup_handler():
    """startup stage → StartupHandler dispatched → outcome applied."""
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_start", clean_fill_cycle=1)
    task = _make_task(stage="startup")
    router, tr, _ = _make_router(startup_outcome=outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert len(tr.update_stage_calls) == 1
    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "clean_fill_start"
    assert wf.clean_fill_cycle == 1


async def test_router_applies_poll_outcome():
    """poll outcome → update_stage called with same workflow, correction unchanged."""
    poll_outcome = StageOutcome(kind="poll", due_delay_sec=10)
    task = _make_task(stage="clean_fill_check")
    router, tr, wr = _make_router(clean_fill_outcome=poll_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert len(tr.update_stage_calls) == 1
    call = tr.update_stage_calls[0]
    # Stage unchanged
    assert call["workflow"].current_stage == "clean_fill_check"
    # upsert_phase called
    assert len(wr.upsert_calls) == 1


async def test_router_applies_transition_outcome():
    """transition outcome → new stage, deadline computed, audit trail recorded."""
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_check")
    task = _make_task(stage="clean_fill_start")
    router, tr, wr = _make_router(startup_outcome=outcome, return_task=task)
    # Override command handler to return the transition
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    assert len(tr.update_stage_calls) == 1
    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "clean_fill_check"
    # clean_fill_check has timeout_key → deadline computed
    assert wf.stage_deadline_at is not None
    # Audit trail
    assert len(tr.record_transition_calls) == 1
    assert tr.record_transition_calls[0]["to_stage"] == "clean_fill_check"


async def test_router_returns_cancelled_task_when_transition_persist_races_with_abort():
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_check")
    task = _make_task(stage="clean_fill_start")
    cancelled_task = AutomationTask.from_row({
        "id": 99, "zone_id": 99, "task_type": "cycle_start", "status": "cancelled",
        "idempotency_key": "k99", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW, "error_code": "grow_cycle_aborted", "error_message": "aborted",
        "created_at": NOW, "updated_at": NOW, "completed_at": NOW,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "clean_fill_start", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 0,
        "control_mode_snapshot": "auto", "pending_manual_step": None,
        "corr_step": None,
    })
    tr = _MockTaskRepo(return_task=None, current_task=cancelled_task)
    wr = _MockWorkflowRepo()
    router = WorkflowRouter(
        task_repository=tr,
        workflow_repository=wr,
        topology_registry=TopologyRegistry(),
        runtime_monitor=_MockRuntimeMonitor(),
        command_gateway=_MockCommandGateway(),
    )
    router._handlers["command"] = _StubHandler(outcome)

    result = await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    assert result.status == "cancelled"


async def test_router_transition_preserves_control_mode_and_clears_pending_manual_step():
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_check")
    task = _make_task(
        stage="clean_fill_start",
        control_mode="manual",
        pending_manual_step="clean_fill_start",
    )
    router, tr, _wr = _make_router(startup_outcome=outcome, return_task=task)
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.control_mode == "manual"
    assert wf.pending_manual_step is None


async def test_router_applies_enter_correction():
    """enter_correction outcome → update_stage with CorrectionState set."""
    corr = CorrectionState(
        corr_step="corr_check", attempt=1, max_attempts=5,
        ec_attempt=0, ec_max_attempts=5, ph_attempt=0, ph_max_attempts=5,
        activated_here=False, stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=None, needs_ec=False, ec_node_uid=None, ec_channel=None,
        ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    outcome = StageOutcome(kind="enter_correction", correction=corr)
    task = _make_task(stage="solution_fill_check")
    router, tr, _ = _make_router(return_task=task)
    router._handlers["solution_fill"] = _StubHandler(outcome)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    call = tr.update_stage_calls[0]
    assert call["correction"] is not None
    assert call["correction"].corr_step == "corr_check"
    # Stage unchanged (correction is within same stage)
    assert call["workflow"].current_stage == "solution_fill_check"


async def test_router_applies_exit_correction():
    """exit_correction → transition to return stage, correction cleared."""
    exit_outcome = StageOutcome(kind="exit_correction", next_stage="solution_fill_stop_to_ready")
    corr = CorrectionState(
        corr_step="corr_deactivate", attempt=2, max_attempts=5,
        ec_attempt=1, ec_max_attempts=5, ph_attempt=1, ph_max_attempts=5,
        activated_here=False, stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=True, needs_ec=False, ec_node_uid=None, ec_channel=None,
        ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    task = _make_task(stage="solution_fill_check", correction=corr)
    router, tr, _ = _make_router(correction_outcome=exit_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    call = tr.update_stage_calls[0]
    assert call["workflow"].current_stage == "solution_fill_stop_to_ready"
    assert call["correction"] is None  # cleared


async def test_router_same_stage_transition_preserves_deadline_and_stage_entered_at():
    exit_outcome = StageOutcome(kind="exit_correction", next_stage="solution_fill_check")
    corr = CorrectionState(
        corr_step="corr_done", attempt=2, max_attempts=5,
        ec_attempt=1, ec_max_attempts=5, ph_attempt=1, ph_max_attempts=5,
        activated_here=False, stabilization_sec=60,
        return_stage_success="solution_fill_check",
        return_stage_fail="solution_fill_check",
        outcome_success=True, needs_ec=False, ec_node_uid=None, ec_channel=None,
        ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    task = _make_task(
        stage="solution_fill_check",
        correction=corr,
        stage_deadline_at=NOW + timedelta(seconds=1800),
        stage_entered_at=NOW - timedelta(seconds=120),
    )
    router, tr, _ = _make_router(correction_outcome=exit_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "solution_fill_check"
    assert wf.stage_deadline_at == (NOW + timedelta(seconds=1800)).replace(tzinfo=None)
    assert wf.stage_entered_at == (NOW - timedelta(seconds=120)).replace(tzinfo=None)


async def test_router_new_stage_transition_resets_stage_retry_count_by_default():
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_check")
    task = _make_task(stage="clean_fill_start", stage_retry_count=3)
    router, tr, _ = _make_router(startup_outcome=outcome, return_task=task)
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "clean_fill_check"
    assert wf.stage_retry_count == 0


async def test_router_dispatches_corr_done_to_correction_handler():
    exit_outcome = StageOutcome(kind="exit_correction", next_stage="solution_fill_stop_to_ready")
    corr = CorrectionState(
        corr_step="corr_done", attempt=2, max_attempts=5,
        ec_attempt=1, ec_max_attempts=5, ph_attempt=1, ph_max_attempts=5,
        activated_here=True, stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=True, needs_ec=False, ec_node_uid=None, ec_channel=None,
        ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    task = _make_task(stage="solution_fill_check", correction=corr)
    router, tr, _ = _make_router(correction_outcome=exit_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert len(tr.update_stage_calls) == 1
    assert tr.update_stage_calls[0]["workflow"].current_stage == "solution_fill_stop_to_ready"
    assert tr.update_stage_calls[0]["correction"] is None


async def test_router_exit_correction_metrics_use_outcome_correction(monkeypatch):
    metric = _MetricRecorder()
    monkeypatch.setattr(
        "ae3lite.application.use_cases.workflow_router.CORRECTION_COMPLETED",
        metric,
    )
    exit_outcome = StageOutcome(
        kind="exit_correction",
        next_stage="solution_fill_stop_to_ready",
        correction=CorrectionState(
            corr_step="corr_done", attempt=2, max_attempts=5,
            ec_attempt=1, ec_max_attempts=5, ph_attempt=1, ph_max_attempts=5,
            activated_here=False, stabilization_sec=60,
            return_stage_success="solution_fill_stop_to_ready",
            return_stage_fail="solution_fill_stop_to_prepare",
            outcome_success=True, needs_ec=False, ec_node_uid=None, ec_channel=None,
            ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
            ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
        ),
    )
    task = _make_task(
        stage="solution_fill_check",
        correction=CorrectionState(
            corr_step="corr_check", attempt=2, max_attempts=5,
            ec_attempt=1, ec_max_attempts=5, ph_attempt=1, ph_max_attempts=5,
            activated_here=False, stabilization_sec=60,
            return_stage_success="solution_fill_stop_to_ready",
            return_stage_fail="solution_fill_stop_to_prepare",
            outcome_success=None, needs_ec=False, ec_node_uid=None, ec_channel=None,
            ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
            ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
        ),
    )
    router, _, _ = _make_router(correction_outcome=exit_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert metric.calls == [{"topology": "two_tank", "outcome": "success"}]


async def test_router_complete_ready_completes_task():
    """complete_ready stage → mark_completed called, no handler dispatched."""
    task = _make_task(stage="complete_ready", phase="ready")
    router, tr, wr = _make_router(return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert len(tr.mark_completed_calls) == 1
    assert len(tr.update_stage_calls) == 0
    assert len(wr.upsert_calls) == 1
    assert wr.upsert_calls[0]["phase"] == "ready"


async def test_router_fail_outcome_raises():
    """fail outcome → raises TaskExecutionError with the given error_code."""
    fail_outcome = StageOutcome(kind="fail", error_code="sensor_unavailable",
                                error_message="Sensor not found")
    task = _make_task(stage="startup")
    router, _, _ = _make_router(startup_outcome=fail_outcome, return_task=task)

    with pytest.raises(TaskExecutionError) as exc_info:
        await router.run(task=task, plan=_MockPlan(), now=NOW)
    assert exc_info.value.code == "sensor_unavailable"


async def test_router_correction_takes_priority_over_stage():
    """When correction is active, CorrectionHandler is dispatched regardless of current stage."""
    corr = CorrectionState(
        corr_step="corr_check", attempt=1, max_attempts=5,
        ec_attempt=0, ec_max_attempts=5, ph_attempt=0, ph_max_attempts=5,
        activated_here=False, stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=None, needs_ec=False, ec_node_uid=None, ec_channel=None,
        ec_duration_ms=None, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    corr_poll = StageOutcome(kind="enter_correction", correction=corr)
    task = _make_task(stage="solution_fill_check", correction=corr)
    router, tr, _ = _make_router(correction_outcome=corr_poll, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    # CorrectionHandler was used (enter_correction result → update_stage with correction)
    assert len(tr.update_stage_calls) == 1
    assert tr.update_stage_calls[0]["correction"] is not None


async def test_router_upsert_workflow_phase_called_on_poll():
    """poll outcome → workflow_repo.upsert_phase is called with current phase."""
    poll_outcome = StageOutcome(kind="poll", due_delay_sec=5)
    task = _make_task(stage="clean_fill_check", phase="tank_filling")
    router, _, wr = _make_router(clean_fill_outcome=poll_outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(), now=NOW)

    assert wr.upsert_calls[0]["phase"] == "tank_filling"


async def test_router_computes_deadline_on_transition_to_check_stage():
    """Transition to a stage with timeout_key → stage_deadline_at computed from runtime."""
    outcome = StageOutcome(kind="transition", next_stage="solution_fill_check")
    task = _make_task(stage="solution_fill_start")
    router, tr, _ = _make_router(return_task=task)
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(
        task=task,
        plan=_MockPlan(runtime={"solution_fill_timeout_sec": 7200}),
        now=NOW,
    )

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.stage_deadline_at == NOW + timedelta(seconds=7200)


async def test_router_transition_no_deadline_for_command_stage():
    """Transition to a command stage (no timeout_key) → stage_deadline_at is None."""
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_start")
    task = _make_task(stage="startup")
    router, tr, _ = _make_router(startup_outcome=outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.stage_deadline_at is None  # clean_fill_start has no timeout_key


async def test_router_transition_to_irrigation_check_uses_requested_duration_for_deadline():
    outcome = StageOutcome(kind="transition", next_stage="irrigation_check")
    task = _make_task(
        stage="irrigation_start",
        phase="irrigating",
        task_type="irrigation_start",
        irrigation_requested_duration_sec=180,
    )
    router, tr, _ = _make_router(return_task=task)
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(
        task=task,
        plan=_MockPlan(runtime={"irrigation_execution": {"duration_sec": 120}}),
        now=NOW,
    )

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "irrigation_check"
    assert wf.stage_deadline_at == NOW + timedelta(seconds=180)


async def test_router_transition_to_irrigation_check_uses_runtime_duration_fallback():
    outcome = StageOutcome(kind="transition", next_stage="irrigation_check")
    task = _make_task(
        stage="irrigation_start",
        phase="irrigating",
        task_type="irrigation_start",
    )
    router, tr, _ = _make_router(return_task=task)
    router._handlers["command"] = _StubHandler(outcome)

    await router.run(
        task=task,
        plan=_MockPlan(runtime={"irrigation_execution": {"duration_sec": 120}}),
        now=NOW,
    )

    wf = tr.update_stage_calls[0]["workflow"]
    assert wf.current_stage == "irrigation_check"
    assert wf.stage_deadline_at == NOW + timedelta(seconds=120)


async def test_router_transition_upsert_payload_uses_next_stage_not_old():
    """Regression: upsert_phase payload must contain the NEW stage, not the old one.

    Bug: _upsert_workflow_phase used task.current_stage (old stage before transition)
    in the ae3_cycle_start_stage payload key. zone_workflow_state was always one
    transition behind, confusing external observers.
    """
    outcome = StageOutcome(kind="transition", next_stage="clean_fill_start")
    task = _make_task(stage="startup")
    router, _, wr = _make_router(startup_outcome=outcome, return_task=task)

    await router.run(task=task, plan=_MockPlan(runtime=RUNTIME), now=NOW)

    assert len(wr.upsert_calls) == 1
    payload = wr.upsert_calls[0]["payload"]
    # Must reflect the NEW stage (clean_fill_start), not the old one (startup)
    assert payload["ae3_cycle_start_stage"] == "clean_fill_start", (
        f"Expected 'clean_fill_start' but got {payload['ae3_cycle_start_stage']!r}. "
        "The payload must use next_stage, not task.current_stage (old stage)."
    )
