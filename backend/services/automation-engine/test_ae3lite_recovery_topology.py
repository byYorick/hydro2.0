"""Unit tests for topology-driven startup recovery (_apply_topology_done_transition).

Spec: аудит критика #5 — explicit recovery algorithm using topology registry.

Tests:
 1. Command DONE + next_stage → task transitioned to next stage
 2. Command DONE + terminal_error → task failed with terminal error
 3. Correction in-flight (task.correction != None) → task failed (safe)
 4. Command still pending (waiting_command) → stays waiting_command
 5. Task in claimed/running (no confirmed command) → task failed
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ae3lite.application.dto.startup_recovery_result import StartupRecoveryResult
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState
from ae3lite.domain.services.topology_registry import TopologyRegistry


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)


# ── Task factory ────────────────────────────────────────────────────

def _make_task(
    *,
    task_id: int = 1,
    zone_id: int = 10,
    status: str = "waiting_command",
    stage: str = "clean_fill_start",
    topology: str = "two_tank",
    claimed_by: str | None = "worker-a",
    intent_id: int | None = None,
    correction: CorrectionState | None = None,
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
        "id": task_id, "zone_id": zone_id, "task_type": "cycle_start", "status": status,
        "idempotency_key": "k-rec", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": claimed_by, "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": topology, "intent_source": None, "intent_trigger": None,
        "intent_id": intent_id, "intent_meta": {},
        "current_stage": stage, "workflow_phase": "tank_filling",
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 1,
        **corr_row,
    })


# ── Stubs ───────────────────────────────────────────────────────────

class _MockTaskRepo:
    def __init__(self, *, tasks: list[AutomationTask] | None = None):
        self._tasks = tasks or []
        self.failed: list[dict] = []
        self.requeued: list[dict] = []
        self.completed: list[int] = []
        self.transitions: list[dict] = []

    async def list_for_startup_recovery(self) -> list[AutomationTask]:
        return self._tasks

    async def fail_for_recovery(self, *, task_id, error_code, error_message, now) -> AutomationTask:
        self.failed.append({"task_id": task_id, "error_code": error_code})
        # Return a failed version of the task
        task = next((t for t in self._tasks if t.id == task_id), None)
        if task is None:
            return _make_task(task_id=task_id, status="failed")
        return AutomationTask.from_row({
            **_task_to_row(task),
            "status": "failed",
            "error_code": error_code,
            "error_message": error_message,
        })

    async def update_stage(self, *, task_id, owner, workflow, correction, due_at, now):
        self.requeued.append({"task_id": task_id, "workflow": workflow})
        task = next((t for t in self._tasks if t.id == task_id), None)
        if task is None:
            return _make_task(task_id=task_id, status="pending", stage=workflow.current_stage)
        return AutomationTask.from_row({
            **_task_to_row(task),
            "status": "pending",
            "current_stage": workflow.current_stage,
        })

    async def mark_completed(self, *, task_id, owner, now):
        self.completed.append(task_id)
        task = next((t for t in self._tasks if t.id == task_id), None)
        if task is None:
            return _make_task(task_id=task_id, status="completed")
        return AutomationTask.from_row({**_task_to_row(task), "status": "completed"})

    async def record_transition(self, *, task_id, from_stage, to_stage, workflow_phase, now, **kwargs):
        self.transitions.append({"task_id": task_id, "to_stage": to_stage})


def _task_to_row(task: AutomationTask) -> dict:
    wf = task.workflow
    return {
        "id": task.id, "zone_id": task.zone_id, "task_type": task.task_type,
        "status": task.status, "idempotency_key": task.idempotency_key,
        "scheduled_for": task.scheduled_for, "due_at": task.due_at,
        "claimed_by": task.claimed_by, "claimed_at": task.claimed_at,
        "error_code": task.error_code, "error_message": task.error_message,
        "created_at": task.created_at, "updated_at": task.updated_at,
        "completed_at": task.completed_at,
        "topology": task.topology, "intent_source": task.intent_source,
        "intent_trigger": task.intent_trigger, "intent_id": task.intent_id,
        "intent_meta": dict(task.intent_meta),
        "current_stage": wf.current_stage, "workflow_phase": wf.workflow_phase,
        "stage_deadline_at": wf.stage_deadline_at, "stage_retry_count": wf.stage_retry_count,
        "stage_entered_at": wf.stage_entered_at, "clean_fill_cycle": wf.clean_fill_cycle,
        "corr_step": task.correction.corr_step if task.correction else None,
        "corr_attempt": task.correction.attempt if task.correction else None,
        "corr_max_attempts": task.correction.max_attempts if task.correction else None,
        "corr_ec_attempt": task.correction.ec_attempt if task.correction else None,
        "corr_ec_max_attempts": task.correction.ec_max_attempts if task.correction else None,
        "corr_ph_attempt": task.correction.ph_attempt if task.correction else None,
        "corr_ph_max_attempts": task.correction.ph_max_attempts if task.correction else None,
    }


class _MockLeaseRepo:
    async def release_expired(self, *, now) -> int:
        return 0


class _MockReconcileUseCase:
    def __init__(self, *, state: str = "waiting_command"):
        self._state = state

    async def run(self, *, task, now):
        from ae3lite.application.dto.command_reconcile_result import CommandReconcileResult
        if self._state == "waiting_command":
            return CommandReconcileResult(
                task=task, ae_command_id=0, external_id=None, legacy_cmd_id=None,
                is_terminal=False, terminal_status=None, legacy_status="waiting_command",
            )
        return CommandReconcileResult(
            task=task, ae_command_id=0, external_id=None, legacy_cmd_id=None,
            is_terminal=True, terminal_status="DONE", legacy_status=None,
        )


class _MockCommandGateway:
    def __init__(self, *, recover_state: str = "done"):
        self._state = recover_state

    async def recover_waiting_command(self, *, task, now) -> dict:
        if self._state == "done":
            # Return task in "running" state after reconcile
            updated = AutomationTask.from_row({
                **_task_to_row(task),
                "status": "running",
            })
            return {"state": "done", "task": updated}
        if self._state == "waiting_command":
            return {"state": "waiting_command", "task": task}
        return {"state": "failed", "task": task}


def _make_use_case(
    *,
    tasks: list[AutomationTask],
    gateway_state: str = "done",
    reconcile_state: str = "waiting_command",
) -> tuple[StartupRecoveryUseCase, _MockTaskRepo]:
    repo = _MockTaskRepo(tasks=tasks)
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_MockLeaseRepo(),
        reconcile_command_use_case=_MockReconcileUseCase(state=reconcile_state),
        command_gateway=_MockCommandGateway(recover_state=gateway_state),
        workflow_repository=None,
        topology_registry=TopologyRegistry(),
    )
    return uc, repo


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_recovery_command_done_routes_to_next_stage():
    """Command DONE + clean_fill_start has next_stage=clean_fill_check → requeue to next stage."""
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    uc, repo = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.scanned_tasks == 1
    assert result.failed_tasks == 0
    assert len(repo.requeued) == 1
    assert repo.requeued[0]["workflow"].current_stage == "clean_fill_check"


async def test_recovery_terminal_stage_done_fails_task():
    """Command DONE + terminal_error stage (clean_fill_timeout_stop) → task failed."""
    task = _make_task(status="waiting_command", stage="clean_fill_timeout_stop")
    uc, repo = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "clean_tank_not_filled_timeout"
    assert len(repo.requeued) == 0


async def test_recovery_correction_in_flight_fails():
    """Task in waiting_command WITH correction active → fail (cannot resume safely)."""
    corr = CorrectionState(
        corr_step="corr_dose_ec", attempt=2, max_attempts=5,
        ec_attempt=1, ec_max_attempts=5, ph_attempt=0, ph_max_attempts=5,
        activated_here=True, stabilization_sec=60,
        return_stage_success="solution_fill_stop_to_ready",
        return_stage_fail="solution_fill_stop_to_prepare",
        outcome_success=None, needs_ec=True, ec_node_uid="ec-n", ec_channel="ec_p",
        ec_duration_ms=2000, needs_ph_up=False, needs_ph_down=False,
        ph_node_uid=None, ph_channel=None, ph_duration_ms=None, wait_until=None,
    )
    task = _make_task(status="waiting_command", stage="solution_fill_check", correction=corr)
    uc, repo = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert "correction" in repo.failed[0]["error_code"].lower() or \
           repo.failed[0]["error_code"] == "startup_recovery_correction_interrupted"


async def test_recovery_command_still_pending_stays_waiting():
    """Command gateway returns waiting_command → stays as waiting_command."""
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    uc, repo = _make_use_case(tasks=[task], gateway_state="waiting_command")

    result = await uc.run(now=NOW)

    assert result.waiting_command_tasks == 1
    assert result.failed_tasks == 0
    assert len(repo.requeued) == 0


async def test_recovery_claimed_task_fails():
    """Task stuck in claimed status (no confirmed command) → fail immediately."""
    task = _make_task(status="claimed", stage="clean_fill_start")
    uc, repo = _make_use_case(tasks=[task])

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "startup_recovery_unconfirmed_command"
