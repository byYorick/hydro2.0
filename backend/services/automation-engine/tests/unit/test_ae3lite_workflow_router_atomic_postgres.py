from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.infrastructure.repositories import PgAutomationTaskRepository, PgZoneWorkflowRepository
from common.db import execute, fetch


pytestmark = pytest.mark.integration


class _StubHandler:
    def __init__(self, outcome: StageOutcome):
        self.outcome = outcome

    async def run(self, *, task, plan, stage_def, now):
        return self.outcome


class _RuntimeMonitor:
    pass


class _CommandGateway:
    pass


class _FailingWorkflowRepository(PgZoneWorkflowRepository):
    def __init__(self) -> None:
        self.received_conn = False

    async def upsert_phase(self, *, zone_id, workflow_phase, payload, scheduler_task_id, now, conn=None):
        self.received_conn = conn is not None
        await super().upsert_phase(
            zone_id=zone_id,
            workflow_phase=workflow_phase,
            payload=payload,
            scheduler_task_id=scheduler_task_id,
            now=now,
            conn=conn,
        )
        raise RuntimeError("injected workflow sync failure after write")


async def _insert_greenhouse(prefix: str) -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:20]}",
        f"{prefix}-gh",
        f"pt-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_zone(prefix: str, *, greenhouse_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"{prefix}-zone",
        f"zn-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_running_task(
    zone_id: int,
    *,
    prefix: str,
    now: datetime,
    stage: str = "startup",
    phase: str = "idle",
    pending_manual_step: str | None = None,
) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id,
            task_type,
            status,
            idempotency_key,
            scheduled_for,
            due_at,
            claimed_by,
            claimed_at,
            created_at,
            updated_at,
            topology,
            current_stage,
            workflow_phase,
            stage_entered_at,
            control_mode_snapshot,
            pending_manual_step
        )
        VALUES (
            $1,
            'cycle_start',
            'running',
            $2,
            $3,
            $3,
            'worker-a',
            $3,
            $3,
            $3,
            'two_tank',
            $4,
            $5,
            $3,
            'auto',
            $6
        )
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
        now,
        stage,
        phase,
        pending_manual_step,
    )
    return int(rows[0]["id"])


async def _insert_workflow_state(zone_id: int, *, now: datetime) -> None:
    await execute(
        """
        INSERT INTO zone_workflow_state (
            zone_id,
            workflow_phase,
            version,
            started_at,
            updated_at,
            payload,
            scheduler_task_id
        )
        VALUES ($1, 'idle', 1, $2, $2, '{"ae3_cycle_start_stage":"startup"}'::jsonb, NULL)
        """,
        zone_id,
        now,
    )


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


def _plan():
    return type("Plan", (), {"runtime": make_runtime_plan(), "named_plans": {}, "targets": {}})()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_json_string", [False, True])
async def test_recirc_resume_rolls_back_with_stage_then_commits_and_reenters(legacy_json_string):
    import json
    from dataclasses import replace
    from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
    from ae3lite.application.services.task_workflow_transition import TaskWorkflowTransition
    from ae3lite.domain.entities.workflow_state import CorrectionState
    from ae3lite.infrastructure.repositories.prepare_baseline_repository import PgPrepareBaselineRepository
    from ae3lite.domain.services.nutrient_pipeline import compute_component_targets

    prefix = f"ae3-resume-atomic-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    tasks = PgAutomationTaskRepository()
    baselines = PgPrepareBaselineRepository()
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        task_id = await _insert_running_task(zone, prefix=prefix, now=now,
                                             stage="prepare_recirculation_check", phase="tank_recirc")
        await _insert_workflow_state(zone, now=now)
        task = await tasks.get_by_id(task_id=task_id)
        corr = CorrectionState.build_default(
            corr_step="corr_check", max_attempts=5, ec_max_attempts=5, ph_max_attempts=5,
            activated_here=False, stabilization_sec=60,
            return_stage_success="prepare_recirculation_stop_to_ready",
            return_stage_fail="prepare_recirculation_window_exhausted",
        )
        corr = replace(corr, pipeline_phase="recirc_npk", active_component="npk", dilute_attempts=2)
        task = replace(task, correction=corr)
        ratios = {"calcium": 0.2, "magnesium": 0.1, "npk": 0.6, "micro": 0.1}
        targets = compute_component_targets(water_ec=0.4, water_ph=6.0, target_ec=1.8, ratios=ratios)
        baseline_id = await baselines.insert_baseline(
            zone_id=zone, ae_task_id=task_id, water_ec=0.4, water_ph=6.0, target_ec=1.8,
            nutrient_budget=1.4, ratios=ratios, component_targets=json.loads(targets.to_json()), captured_at=now,
        )
        assert baseline_id is not None
        if legacy_json_string:
            await execute(
                "UPDATE zone_prepare_baselines SET component_targets_json=to_jsonb(component_targets_json::text) WHERE id=$1",
                baseline_id,
            )
        workflow = replace(task.workflow, current_stage="prepare_recirculation_window_exhausted")
        args = dict(task=task, owner=task.claimed_by, claim_generation=task.claim_generation,
                    workflow=workflow, correction=None, due_at=now, now=now,
                    workflow_phase="tank_recirc", stage=workflow.current_stage)
        transitions = TaskWorkflowTransition(task_repository=tasks, workflow_repository=_FailingWorkflowRepository())
        with pytest.raises(TaskExecutionError):
            await transitions.requeue(**args)
        baseline = (await fetch("SELECT component_targets_json FROM zone_prepare_baselines WHERE id=$1", baseline_id))[0]
        assert "pipeline_resume" not in baseline["component_targets_json"]
        assert (await tasks.get_by_id(task_id=task_id)).current_stage == "prepare_recirculation_check"

        transitions = TaskWorkflowTransition(task_repository=tasks, workflow_repository=PgZoneWorkflowRepository())
        stale = await transitions.requeue(**{**args, "claim_generation": task.claim_generation + 1})
        assert stale is None
        still_original = (await fetch("SELECT component_targets_json FROM zone_prepare_baselines WHERE id=$1", baseline_id))[0]
        assert "pipeline_resume" not in still_original["component_targets_json"]
        updated = await transitions.requeue(**args)
        assert updated is not None and updated.correction is None
        stored = (await fetch("SELECT component_targets_json FROM zone_prepare_baselines WHERE id=$1", baseline_id))[0]
        assert isinstance(stored["component_targets_json"], dict)
        assert stored["component_targets_json"]["pipeline_resume"]["pipeline_phase"] == "recirc_npk"
        handler = PrepareRecircCheckHandler(runtime_monitor=_RuntimeMonitor(), command_gateway=_CommandGateway(), task_repository=tasks)
        resumed = await handler._enter_recirc_pipeline_correction(
            task=updated, runtime=_plan().runtime,
            return_stage_success=corr.return_stage_success, return_stage_fail=corr.return_stage_fail,
        )
        assert resumed.pipeline_phase == "recirc_npk"
        assert resumed.active_component == "npk"
        assert resumed.dilute_attempts == 2
    finally:
        await _cleanup(prefix)


def _router(*, task_repo, workflow_repo) -> WorkflowRouter:
    return WorkflowRouter(
        task_repository=task_repo,
        workflow_repository=workflow_repo,
        topology_registry=TopologyRegistry(),
        runtime_monitor=_RuntimeMonitor(),
        command_gateway=_CommandGateway(),
    )


@pytest.mark.asyncio
async def test_router_rolls_back_task_and_workflow_when_workflow_sync_fails_after_write() -> None:
    prefix = f"ae3-router-atomic-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    workflow_repo = _FailingWorkflowRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_running_task(zone_id, prefix=prefix, now=now)
        await _insert_workflow_state(zone_id, now=now)

        task = await task_repo.get_by_id(task_id=task_id)
        assert task is not None
        router = _router(task_repo=task_repo, workflow_repo=workflow_repo)
        router._handlers["startup"] = _StubHandler(
            StageOutcome(kind="transition", next_stage="clean_fill_start")
        )

        with pytest.raises(TaskExecutionError) as exc_info:
            await router.run(task=task, plan=_plan(), now=now)

        assert exc_info.value.code == ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED
        assert workflow_repo.received_conn is True

        task_rows = await fetch(
            """
            SELECT status, current_stage, workflow_phase, claimed_by
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert dict(task_rows[0]) == {
            "status": "running",
            "current_stage": "startup",
            "workflow_phase": "idle",
            "claimed_by": "worker-a",
        }

        workflow_rows = await fetch(
            """
            SELECT workflow_phase, version, payload
            FROM zone_workflow_state
            WHERE zone_id = $1
            """,
            zone_id,
        )
        workflow_row = workflow_rows[0]
        assert workflow_row["workflow_phase"] == "idle"
        assert int(workflow_row["version"]) == 1
        assert workflow_row["payload"]["ae3_cycle_start_stage"] == "startup"

        transition_rows = await fetch(
            "SELECT id FROM ae_stage_transitions WHERE task_id = $1",
            task_id,
        )
        assert transition_rows == []
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_router_commits_task_workflow_and_audit_on_successful_transition() -> None:
    prefix = f"ae3-router-atomic-success-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    workflow_repo = PgZoneWorkflowRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_running_task(zone_id, prefix=prefix, now=now)
        await _insert_workflow_state(zone_id, now=now)
        task = await task_repo.get_by_id(task_id=task_id)
        assert task is not None

        router = _router(task_repo=task_repo, workflow_repo=workflow_repo)
        router._handlers["startup"] = _StubHandler(
            StageOutcome(kind="transition", next_stage="clean_fill_start")
        )

        result = await router.run(task=task, plan=_plan(), now=now)

        assert result.status == "pending"
        task_rows = await fetch(
            """
            SELECT status, current_stage, workflow_phase, claimed_by
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert dict(task_rows[0]) == {
            "status": "pending",
            "current_stage": "clean_fill_start",
            "workflow_phase": "tank_filling",
            "claimed_by": None,
        }
        workflow_rows = await fetch(
            """
            SELECT workflow_phase, payload
            FROM zone_workflow_state
            WHERE zone_id = $1
            """,
            zone_id,
        )
        assert workflow_rows[0]["workflow_phase"] == "tank_filling"
        assert workflow_rows[0]["payload"]["ae3_cycle_start_stage"] == "clean_fill_start"
        transition_rows = await fetch(
            """
            SELECT from_stage, to_stage, workflow_phase
            FROM ae_stage_transitions
            WHERE task_id = $1
            """,
            task_id,
        )
        assert [dict(row) for row in transition_rows] == [
            {
                "from_stage": "startup",
                "to_stage": "clean_fill_start",
                "workflow_phase": "tank_filling",
            }
        ]
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_router_cas_miss_does_not_touch_task_workflow_or_audit() -> None:
    prefix = f"ae3-router-atomic-cas-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    workflow_repo = PgZoneWorkflowRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_running_task(zone_id, prefix=prefix, now=now)
        await _insert_workflow_state(zone_id, now=now)
        stale_task = await task_repo.get_by_id(task_id=task_id)
        assert stale_task is not None
        await execute(
            """
            UPDATE ae_tasks
            SET claim_generation = claim_generation + 1
            WHERE id = $1
            """,
            task_id,
        )

        router = _router(task_repo=task_repo, workflow_repo=workflow_repo)
        router._handlers["startup"] = _StubHandler(
            StageOutcome(kind="transition", next_stage="clean_fill_start")
        )

        with pytest.raises(TaskExecutionError) as exc_info:
            await router.run(task=stale_task, plan=_plan(), now=now)

        assert exc_info.value.code == "ae3_stale_claim_rejected"
        task_rows = await fetch(
            "SELECT status, current_stage, workflow_phase FROM ae_tasks WHERE id = $1",
            task_id,
        )
        assert dict(task_rows[0]) == {
            "status": "running",
            "current_stage": "startup",
            "workflow_phase": "idle",
        }
        workflow_rows = await fetch(
            "SELECT workflow_phase, payload FROM zone_workflow_state WHERE zone_id = $1",
            zone_id,
        )
        assert workflow_rows[0]["workflow_phase"] == "idle"
        assert workflow_rows[0]["payload"]["ae3_cycle_start_stage"] == "startup"
        transition_rows = await fetch("SELECT id FROM ae_stage_transitions WHERE task_id = $1", task_id)
        assert transition_rows == []
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_router_poll_preserves_concurrent_pending_manual_step_inside_atomic_update() -> None:
    prefix = f"ae3-router-atomic-manual-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    workflow_repo = PgZoneWorkflowRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_running_task(
            zone_id,
            prefix=prefix,
            now=now,
            stage="clean_fill_check",
            phase="tank_filling",
        )
        await _insert_workflow_state(zone_id, now=now)
        stale_task = await task_repo.get_by_id(task_id=task_id)
        assert stale_task is not None
        await execute(
            """
            UPDATE ae_tasks
            SET pending_manual_step = 'operator-step'
            WHERE id = $1
            """,
            task_id,
        )

        router = _router(task_repo=task_repo, workflow_repo=workflow_repo)
        router._handlers["clean_fill"] = _StubHandler(StageOutcome(kind="poll", due_delay_sec=5))

        await router.run(task=stale_task, plan=_plan(), now=now)

        task_rows = await fetch(
            """
            SELECT status, current_stage, workflow_phase, pending_manual_step
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert dict(task_rows[0]) == {
            "status": "pending",
            "current_stage": "clean_fill_check",
            "workflow_phase": "tank_filling",
            "pending_manual_step": "operator-step",
        }
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_router_rolls_back_completed_task_when_ready_workflow_sync_fails() -> None:
    prefix = f"ae3-router-atomic-complete-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    workflow_repo = _FailingWorkflowRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_running_task(
            zone_id,
            prefix=prefix,
            now=now,
            stage="complete_ready",
            phase="ready",
        )
        await _insert_workflow_state(zone_id, now=now)
        task = await task_repo.get_by_id(task_id=task_id)
        assert task is not None

        router = _router(task_repo=task_repo, workflow_repo=workflow_repo)

        with pytest.raises(TaskExecutionError) as exc_info:
            await router.run(task=task, plan=_plan(), now=now)

        assert exc_info.value.code == ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED
        task_rows = await fetch(
            "SELECT status, current_stage, completed_at FROM ae_tasks WHERE id = $1",
            task_id,
        )
        assert task_rows[0]["status"] == "running"
        assert task_rows[0]["current_stage"] == "complete_ready"
        assert task_rows[0]["completed_at"] is None
        workflow_rows = await fetch(
            "SELECT workflow_phase, payload FROM zone_workflow_state WHERE zone_id = $1",
            zone_id,
        )
        assert workflow_rows[0]["workflow_phase"] == "idle"
        assert workflow_rows[0]["payload"]["ae3_cycle_start_stage"] == "startup"
    finally:
        await _cleanup(prefix)
