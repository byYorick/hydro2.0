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
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)


# ── Task factory ────────────────────────────────────────────────────

def _make_task(
    *,
    task_id: int = 1,
    zone_id: int = 10,
    task_type: str = "cycle_start",
    status: str = "waiting_command",
    stage: str = "clean_fill_start",
    topology: str = "two_tank",
    workflow_phase: str = "tank_filling",
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
        "id": task_id, "zone_id": zone_id, "task_type": task_type, "status": status,
        "idempotency_key": "k-rec", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": claimed_by, "claimed_at": NOW, "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": topology, "intent_source": None, "intent_trigger": None,
        "intent_id": intent_id, "intent_meta": {},
        "current_stage": stage, "workflow_phase": workflow_phase,
        "stage_deadline_at": None, "stage_retry_count": 0,
        "stage_entered_at": NOW, "clean_fill_cycle": 1,
        **corr_row,
    })


# ── Stubs ───────────────────────────────────────────────────────────

class _MockTaskRepo:
    def __init__(
        self,
        *,
        tasks: list[AutomationTask] | None = None,
        reconcile_rows: list[dict] | None = None,
    ):
        self._tasks = tasks or []
        self._reconcile_rows = reconcile_rows or []
        self.failed: list[dict] = []
        self.reconcile_failed: list[dict] = []
        self.requeued: list[dict] = []
        self.completed: list[int] = []
        self.transitions: list[dict] = []
        self.waiting_command_persisted: list[int] = []

    async def list_for_startup_recovery(self) -> list[AutomationTask]:
        return self._tasks

    async def fetch_pending_with_idle_zone_workflow_rows(self) -> list[dict]:
        return self._reconcile_rows

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

    async def fail_pending_or_active_for_recovery(
        self,
        *,
        task_id,
        error_code,
        error_message,
        now,
    ) -> AutomationTask:
        self.reconcile_failed.append({"task_id": task_id, "error_code": error_code})
        for row in self._reconcile_rows:
            if int(row.get("id") or 0) == int(task_id):
                row_map = {k: v for k, v in row.items() if k != "snapshot_stage"}
                return AutomationTask.from_row({
                    **row_map,
                    "status": "failed",
                    "error_code": error_code,
                    "error_message": error_message,
                })
        return await self.fail_for_recovery(
            task_id=task_id,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )

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

    async def recover_waiting_command(self, *, task_id, now, owner=None):
        self.waiting_command_persisted.append(task_id)
        task = next((t for t in self._tasks if t.id == task_id), None)
        if task is None:
            return _make_task(task_id=task_id, status="waiting_command")
        return AutomationTask.from_row({**_task_to_row(task), "status": "waiting_command"})


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
    def __init__(self, *, release: bool = True) -> None:
        self._release = release
        self.released: list[dict[str, object]] = []

    async def release_expired(self, *, now) -> int:
        return 0

    async def release_if_owner_or_expired(self, *, zone_id, owner, now) -> bool:
        self.released.append({"zone_id": zone_id, "owner": owner, "now": now})
        return self._release


class _MockWorkflowRepo:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        self.upserts.append({
            "zone_id": zone_id,
            "workflow_phase": workflow_phase,
            "payload": payload,
            "scheduler_task_id": scheduler_task_id,
            "now": now,
        })


class _MockWorkflowRepoRaises(_MockWorkflowRepo):
    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now):
        await super().upsert_phase(
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
        )
        raise RuntimeError("workflow repo unavailable")


class _MockCommandGateway:
    def __init__(
        self,
        *,
        recover_state: str = "done",
        failed_error_code: str | None = None,
        failed_error_message: str | None = None,
        simulate_missing_ae_command: bool = False,
    ):
        self._state = recover_state
        self._failed_error_code = failed_error_code
        self._failed_error_message = failed_error_message
        self._simulate_missing_ae_command = simulate_missing_ae_command

    async def recover_waiting_command(self, *, task, now) -> dict:
        if self._simulate_missing_ae_command:
            from ae3lite.domain.errors import TaskExecutionError

            raise TaskExecutionError(
                "ae3_missing_ae_command",
                f"Task {task.id} has no ae_command for recovery",
            )
        if self._state == "done":
            # Return task in "running" state after reconcile
            updated = AutomationTask.from_row({
                **_task_to_row(task),
                "status": "running",
            })
            return {"state": "done", "task": updated}
        if self._state == "waiting_command":
            return {"state": "waiting_command", "task": task}
        if self._state == "failed":
            failed = AutomationTask.from_row({
                **_task_to_row(task),
                "status": "failed",
                "error_code": "command_error",
                "error_message": "legacy command ERROR",
            })
            result: dict = {"state": "failed", "task": failed}
            if self._failed_error_code is not None:
                result["error_code"] = self._failed_error_code
            if self._failed_error_message is not None:
                result["error_message"] = self._failed_error_message
            return result
        return {"state": "failed", "task": task}


class _AlertRepositoryRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def raise_active(self, **kwargs):
        self.calls.append(kwargs)
        return 101


def _make_use_case(
    *,
    tasks: list[AutomationTask],
    gateway_state: str = "done",
    gateway_failed_error_code: str | None = None,
    gateway_simulate_missing_ae_command: bool = False,
    alert_repository: _AlertRepositoryRecorder | None = None,
    lease_repository: _MockLeaseRepo | None = None,
    workflow_repository: _MockWorkflowRepo | None = None,
    reconcile_rows: list[dict] | None = None,
) -> tuple[StartupRecoveryUseCase, _MockTaskRepo, _MockLeaseRepo]:
    repo = _MockTaskRepo(tasks=tasks, reconcile_rows=reconcile_rows)
    leases = lease_repository or _MockLeaseRepo()
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=leases,
        command_gateway=_MockCommandGateway(
            recover_state=gateway_state,
            failed_error_code=gateway_failed_error_code,
            simulate_missing_ae_command=gateway_simulate_missing_ae_command,
        ),
        workflow_repository=workflow_repository,
        topology_registry=TopologyRegistry(),
        alert_repository=alert_repository,
        use_startup_recovery_lock=False,
    )
    return uc, repo, leases


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_recovery_command_done_routes_to_next_stage():
    """Command DONE + clean_fill_start has next_stage=clean_fill_check → requeue to next stage."""
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.scanned_tasks == 1
    assert result.failed_tasks == 0
    assert len(repo.requeued) == 1
    assert repo.requeued[0]["workflow"].current_stage == "clean_fill_check"


async def test_recovery_terminal_stage_done_fails_task(monkeypatch: pytest.MonkeyPatch):
    """Command DONE + terminal_error stage (clean_fill_timeout_stop) → task failed."""
    zone_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, details: dict | None = None) -> bool:
        zone_events.append((zone_id, event_type, dict(details or {})))
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.send_service_log",
        lambda **_kwargs: None,
    )

    task = _make_task(status="waiting_command", stage="clean_fill_timeout_stop", intent_id=42)
    alerts = _AlertRepositoryRecorder()
    workflow_repo = _MockWorkflowRepo()
    uc, repo, leases = _make_use_case(
        tasks=[task],
        gateway_state="done",
        alert_repository=alerts,
        workflow_repository=workflow_repo,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "clean_tank_not_filled_timeout"
    assert len(repo.requeued) == 0
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["details"]["error_code"] == "clean_tank_not_filled_timeout"
    assert len(leases.released) == 1
    assert workflow_repo.upserts
    assert workflow_repo.upserts[0]["workflow_phase"] == "idle"
    assert zone_events
    assert zone_events[0][2]["outcome"] == "failed"
    assert zone_events[0][2]["stage"] == "clean_fill_timeout_stop"


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
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1


async def test_recovery_workflow_repo_failure_does_not_abort_otherwise_valid_transition():
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    repo = _MockTaskRepo(tasks=[task])
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_MockLeaseRepo(),
        command_gateway=_MockCommandGateway(recover_state="done"),
        workflow_repository=_MockWorkflowRepoRaises(),
        topology_registry=TopologyRegistry(),
        use_startup_recovery_lock=False,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert len(repo.requeued) == 1


async def test_recovery_command_still_pending_stays_waiting():
    """Command gateway returns waiting_command → stays as waiting_command."""
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="waiting_command")

    result = await uc.run(now=NOW)

    assert result.waiting_command_tasks == 1
    assert result.failed_tasks == 0
    assert len(repo.requeued) == 0


async def test_recovery_claimed_task_fails():
    """Task stuck in claimed status (no confirmed command) → fail immediately."""
    task = _make_task(status="claimed", stage="clean_fill_start")
    alerts = _AlertRepositoryRecorder()
    uc, repo, leases = _make_use_case(
        tasks=[task],
        alert_repository=alerts,
        gateway_simulate_missing_ae_command=True,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "startup_recovery_unconfirmed_command"
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    details = alerts.calls[0]["details"]
    assert isinstance(details, dict)
    assert details["error_code"] == "startup_recovery_unconfirmed_command"
    assert details["recovery_source"] == "startup_recovery"
    assert details["stage"] == "clean_fill_start"
    assert details["dedupe_key"] == f"biz_ae3_task_failed:{task.zone_id}:{task.id}:startup_recovery"
    assert len(leases.released) == 1
    assert leases.released[0]["zone_id"] == task.zone_id
    assert leases.released[0]["owner"] == "worker-a"


async def test_recovery_running_with_done_advances_to_next_stage():
    """running + legacy DONE → topology transition без fail (фаза 2)."""
    task = _make_task(status="running", stage="prepare_recirculation_start")
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert result.recovered_waiting_command_tasks == 1
    assert len(repo.requeued) == 1
    assert repo.requeued[0]["workflow"].current_stage == "prepare_recirculation_check"


async def test_recovery_poll_stage_done_requeues_same_stage_not_completed():
    """DONE на poll-stage (solution_fill_check) не должен terminal-complete task."""
    task = _make_task(status="waiting_command", stage="solution_fill_check")
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert result.recovered_waiting_command_tasks == 1
    assert len(repo.completed) == 0
    assert len(repo.requeued) == 1
    assert repo.requeued[0]["workflow"].current_stage == "solution_fill_check"
    assert repo.requeued[0]["workflow"].workflow_phase == "tank_filling"


async def test_recovery_terminal_ready_stage_done_marks_completed():
    """complete_ready (handler=ready) → mark_completed."""
    task = _make_task(
        status="waiting_command",
        stage="complete_ready",
        workflow_phase="ready",
    )
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert result.completed_tasks == 1
    assert repo.completed == [task.id]
    assert len(repo.requeued) == 0


async def test_recovery_generic_cycle_start_startup_done_marks_completed():
    """generic_cycle_start startup (command, no next_stage) → mark_completed after DONE."""
    task = _make_task(
        status="waiting_command",
        stage="startup",
        topology="generic_cycle_start",
        workflow_phase="idle",
    )
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert result.completed_tasks == 1
    assert repo.completed == [task.id]
    assert len(repo.requeued) == 0


async def test_recovery_running_with_pending_legacy_stays_waiting_command():
    """running + legacy in-flight → waiting_command, не fail."""
    task = _make_task(status="running", stage="clean_fill_start")
    uc, repo, _leases = _make_use_case(tasks=[task], gateway_state="waiting_command")

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 0
    assert result.waiting_command_tasks == 1
    assert repo.waiting_command_persisted == [task.id]


async def test_recovery_running_without_ae_command_fails():
    """running без ae_command → startup_recovery_unconfirmed_command."""
    from ae3lite.domain.errors import TaskExecutionError

    class _GatewayRaisesOnRecover:
        async def recover_waiting_command(self, *, task, now) -> dict:
            raise TaskExecutionError(
                "ae3_missing_ae_command",
                f"Task {task.id} has no ae_command for recovery",
            )

    task = _make_task(status="running", stage="prepare_recirculation_start")
    repo = _MockTaskRepo(tasks=[task])
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_MockLeaseRepo(),
        command_gateway=_GatewayRaisesOnRecover(),
        workflow_repository=None,
        topology_registry=TopologyRegistry(),
        use_startup_recovery_lock=False,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "startup_recovery_unconfirmed_command"


async def test_recovery_gateway_command_failed_emits_alert_and_releases_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, details: dict | None = None) -> bool:
        zone_events.append((zone_id, event_type, dict(details or {})))
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.send_service_log",
        lambda **_kwargs: None,
    )

    task = _make_task(status="waiting_command", stage="clean_fill_start")
    alerts = _AlertRepositoryRecorder()
    uc, repo, leases = _make_use_case(
        tasks=[task],
        gateway_state="failed",
        alert_repository=alerts,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert len(alerts.calls) == 1
    assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    assert alerts.calls[0]["details"]["error_code"] == "command_error"
    assert len(leases.released) == 1
    assert zone_events
    assert zone_events[0][1] == "AE_STARTUP_RECOVERY_OUTCOME"
    assert zone_events[0][2]["outcome"] == "failed"


async def test_recovery_missing_ae_command_fails_gracefully():
    """waiting_command task with no ae_command row → TaskExecutionError caught, task fails gracefully."""
    from ae3lite.domain.errors import TaskExecutionError

    class _GatewayRaisesOnRecover:
        async def recover_waiting_command(self, *, task, now) -> dict:
            raise TaskExecutionError("ae3_missing_ae_command", f"Task {task.id} has no ae_command for recovery")

    task = _make_task(status="waiting_command", stage="clean_fill_start")
    repo = _MockTaskRepo(tasks=[task])
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_MockLeaseRepo(),
        command_gateway=_GatewayRaisesOnRecover(),
        workflow_repository=None,
        topology_registry=TopologyRegistry(),
        use_startup_recovery_lock=False,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert result.scanned_tasks == 1
    assert repo.failed[0]["error_code"] == "ae3_missing_ae_command"


async def test_recovery_unknown_stage_syncs_workflow_idle_before_fail() -> None:
    task = _make_task(status="waiting_command", stage="broken_stage")
    repo = _MockTaskRepo(tasks=[task])
    workflow_repo = _MockWorkflowRepo()
    uc = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_MockLeaseRepo(),
        command_gateway=_MockCommandGateway(recover_state="done"),
        workflow_repository=workflow_repo,
        topology_registry=TopologyRegistry(),
        use_startup_recovery_lock=False,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert repo.failed[0]["error_code"] == "startup_recovery_unknown_stage"
    assert workflow_repo.upserts == [{
        "zone_id": task.zone_id,
        "workflow_phase": "idle",
        "payload": {
            "ae3_cycle_start_stage": "broken_stage",
            "ae3_failure_rollback": True,
            "ae3_failed_task_id": task.id,
        },
        "scheduler_task_id": str(task.id),
        "now": NOW,
    }]


async def test_recovery_success_event_reports_next_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    zone_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, details: dict | None = None) -> bool:
        zone_events.append((zone_id, event_type, dict(details or {})))
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.send_service_log",
        lambda **_kwargs: None,
    )

    task = _make_task(status="waiting_command", stage="clean_fill_start")
    uc, _repo, _leases = _make_use_case(tasks=[task], gateway_state="done")

    result = await uc.run(now=NOW)

    assert result.recovered_waiting_command_tasks == 1
    assert zone_events
    assert zone_events[0][1] == "AE_STARTUP_RECOVERY_OUTCOME"
    assert zone_events[0][2]["outcome"] == "recovered_waiting_command"
    assert zone_events[0][2]["stage"] == "clean_fill_check"


async def test_recovery_gateway_fail_syncs_workflow_rollback() -> None:
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    workflow_repo = _MockWorkflowRepo()
    uc, _repo, leases = _make_use_case(
        tasks=[task],
        gateway_state="failed",
        workflow_repository=workflow_repo,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert workflow_repo.upserts
    assert workflow_repo.upserts[0]["workflow_phase"] == "idle"
    assert workflow_repo.upserts[0]["payload"]["ae3_failure_rollback"] is True
    assert len(leases.released) == 1


async def test_recovery_gateway_fail_prefers_result_error_code() -> None:
    task = _make_task(status="waiting_command", stage="clean_fill_start")
    alerts = _AlertRepositoryRecorder()
    uc, _repo, _leases = _make_use_case(
        tasks=[task],
        gateway_state="failed",
        gateway_failed_error_code="legacy_command_error",
        alert_repository=alerts,
    )

    await uc.run(now=NOW)

    assert len(alerts.calls) == 1
    assert alerts.calls[0]["details"]["error_code"] == "legacy_command_error"


async def test_recovery_lease_not_released_for_foreign_owner() -> None:
    task = _make_task(status="claimed", stage="clean_fill_start")
    leases = _MockLeaseRepo(release=False)
    uc, _repo, _leases = _make_use_case(
        tasks=[task],
        lease_repository=leases,
        gateway_simulate_missing_ae_command=True,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert len(leases.released) == 1


async def test_recovery_reconcile_pending_fail_emits_alert_and_releases_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zone_events: list[tuple[int, str, dict]] = []

    async def _record_zone_event(zone_id: int, event_type: str, details: dict | None = None) -> bool:
        zone_events.append((zone_id, event_type, dict(details or {})))
        return True

    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.create_zone_event",
        _record_zone_event,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.send_service_log",
        lambda **_kwargs: None,
    )

    pending_task = _make_task(
        task_id=5,
        status="pending",
        stage="await_ready",
        task_type="irrigation_start",
        intent_id=99,
    )
    reconcile_row = {
        **_task_to_row(pending_task),
        "snapshot_stage": "clean_fill_source_empty_stop",
    }
    alerts = _AlertRepositoryRecorder()
    uc, repo, leases = _make_use_case(
        tasks=[],
        reconcile_rows=[reconcile_row],
        alert_repository=alerts,
    )

    result = await uc.run(now=NOW)

    assert result.failed_tasks == 1
    assert len(repo.reconcile_failed) == 1
    assert repo.reconcile_failed[0]["error_code"] == "startup_recovery_pending_vs_terminal_workflow"
    assert len(alerts.calls) == 1
    assert len(leases.released) == 1
    assert zone_events
    assert zone_events[0][2]["outcome"] == "failed"
    assert zone_events[0][2]["error_code"] == "startup_recovery_pending_vs_terminal_workflow"


async def test_recovery_service_log_on_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    service_logs: list[dict] = []

    def _capture_service_log(**kwargs):
        service_logs.append(kwargs)

    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.send_service_log",
        _capture_service_log,
    )
    monkeypatch.setattr(
        "ae3lite.application.use_cases.startup_recovery.create_zone_event",
        lambda *_args, **_kwargs: True,
    )

    task = _make_task(status="claimed", stage="clean_fill_start")
    uc, _repo, _leases = _make_use_case(
        tasks=[task],
        gateway_simulate_missing_ae_command=True,
    )

    await uc.run(now=NOW)

    assert service_logs
    assert service_logs[0]["message"] == "AE3 startup recovery outcome"
    assert service_logs[0]["context"]["outcome"] == "failed"
    assert service_logs[0]["level"] == "warning"
