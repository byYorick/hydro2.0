"""PostgreSQL-доказательство fencing claim_generation (S2 / F2).

Два соединения и asyncio.Event. Две connection в тесте не означают
несколько production-реплик: в проде остаётся одна активная реплика AE3.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest

from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseContext,
    escalate_foreign_lease_stale_task,
)
from ae3lite.application.use_cases.operator_unblock_zone import OperatorUnblockZoneUseCase
from ae3lite.application.use_cases.stale_task_reconcile import StaleTaskReconcileUseCase
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import StartupRecoveryError
from ae3lite.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae3lite.infrastructure.repositories.automation_task_repository import PgAutomationTaskRepository
from ae3lite.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from common.db import execute, fetch
from common.env import get_settings

pytestmark = pytest.mark.integration


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


async def _connect() -> asyncpg.Connection:
    settings = get_settings()
    return await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_db,
        user=settings.pg_user,
        password=settings.pg_pass,
        timeout=10,
    )


async def _insert_zone(prefix: str) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        prefix,
        f"{prefix}-uid",
    )
    return int(rows[0]["id"])


async def _insert_task(*, zone_id: int, idempotency_key: str, now: datetime) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key,
            scheduled_for, due_at, created_at, updated_at,
            topology, current_stage, workflow_phase
        )
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $3, $3, $3, 'two_tank', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        idempotency_key,
        now,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute(
        """
        DELETE FROM ae_commands
        WHERE task_id IN (
            SELECT id FROM ae_tasks
            WHERE zone_id IN (SELECT id FROM zones WHERE name LIKE $1)
        )
        """,
        f"{prefix}%",
    )
    await execute(
        """
        DELETE FROM ae_zone_leases
        WHERE zone_id IN (SELECT id FROM zones WHERE name LIKE $1)
        """,
        f"{prefix}%",
    )
    await execute(
        """
        DELETE FROM ae_tasks
        WHERE zone_id IN (SELECT id FROM zones WHERE name LIKE $1)
        """,
        f"{prefix}%",
    )
    await execute("DELETE FROM zones WHERE name LIKE $1", f"{prefix}%")


async def _task_row(task_id: int) -> dict:
    rows = await fetch(
        """
        SELECT status, claimed_by, claim_generation, process_run_id, current_stage, corr_step
        FROM ae_tasks
        WHERE id = $1
        """,
        task_id,
    )
    return dict(rows[0])


async def _lease_row(zone_id: int) -> dict | None:
    rows = await fetch(
        """
        SELECT owner, claim_generation, process_run_id, leased_until
        FROM ae_zone_leases
        WHERE zone_id = $1
        """,
        zone_id,
    )
    if not rows:
        return None
    return dict(rows[0])


def _workflow(now: datetime, stage: str) -> WorkflowState:
    return WorkflowState(
        current_stage=stage,
        workflow_phase="tank_filling",
        stage_deadline_at=now + timedelta(seconds=30),
        stage_retry_count=0,
        stage_entered_at=now,
        clean_fill_cycle=1,
    )


@pytest.mark.asyncio
async def test_stale_writer_and_old_generation_do_not_mutate_committed_rows() -> None:
    prefix = f"ae3-gen-stale-{uuid4().hex}"
    now = _now()
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(zone_id=zone_id, idempotency_key=f"{prefix}-task", now=now)
        first = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-a",
            process_run_id="run-a",
            now=now,
            lease_ttl_sec=120,
        )
        assert first is not None
        first_task, _first_lease = first
        assert int(first_task.claim_generation) >= 1

        requeued = await task_repo.update_stage(
            task_id=task_id,
            owner="proc-a",
            claim_generation=int(first_task.claim_generation),
            workflow=_workflow(now, "startup"),
            correction=None,
            due_at=now,
            now=now,
        )
        assert requeued is not None
        assert requeued.status == "pending"
        assert int(requeued.claim_generation) == int(first_task.claim_generation)

        second = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-a",
            process_run_id="run-a",
            now=now,
            lease_ttl_sec=120,
        )
        assert second is not None
        winner, winner_lease = second
        assert winner.claimed_by == "proc-a"
        assert int(winner.claim_generation) > int(first_task.claim_generation)
        await execute(
            "UPDATE ae_tasks SET corr_step = 'corr_check' WHERE id = $1",
            task_id,
        )
        before = await _task_row(task_id)
        leased_before = await _lease_row(zone_id)
        assert leased_before is not None
        assert int(leased_before["claim_generation"]) == int(winner.claim_generation)

        stale = await task_repo.update_stage(
            task_id=task_id,
            owner="proc-a",
            claim_generation=int(first_task.claim_generation),
            workflow=_workflow(now, "solution_fill_check"),
            correction=None,
            due_at=now + timedelta(seconds=5),
            now=now,
        )
        completed = await task_repo.mark_completed(
            task_id=task_id,
            owner="proc-a",
            now=now,
            claim_generation=int(first_task.claim_generation),
        )
        failed = await task_repo.fail_for_recovery(
            task_id=task_id,
            error_code="ae3_stale_claim_rejected",
            error_message="old generation",
            now=now,
            owner="proc-a",
            claim_generation=int(first_task.claim_generation),
        )
        extended = await lease_repo.extend(
            zone_id=zone_id,
            owner="proc-a",
            now=now + timedelta(hours=1),
            lease_ttl_sec=900,
            claim_generation=int(first_task.claim_generation),
        )
        released = await lease_repo.release(
            zone_id=zone_id,
            owner="proc-a",
            claim_generation=int(first_task.claim_generation),
        )

        after = await _task_row(task_id)
        leased_after = await _lease_row(zone_id)
        assert stale is None
        assert completed is None
        assert failed is None
        assert extended is False
        assert released is False
        assert after == before
        assert leased_after is not None
        assert leased_after["owner"] == winner_lease.owner
        assert int(leased_after["claim_generation"]) == int(winner.claim_generation)
        assert leased_after["leased_until"] == leased_before["leased_until"]
        assert leased_after["process_run_id"] == "run-a"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_foreign_owner_outcome_does_not_replace_winner() -> None:
    prefix = f"ae3-gen-foreign-{uuid4().hex}"
    now = _now()
    task_repo = PgAutomationTaskRepository()
    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(zone_id=zone_id, idempotency_key=f"{prefix}-task", now=now)
        winner = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-b",
            process_run_id="run-b",
            now=now,
            lease_ttl_sec=120,
        )
        assert winner is not None
        winner_task, _lease = winner
        await execute("UPDATE ae_tasks SET corr_step = 'corr_check' WHERE id = $1", task_id)
        before = await _task_row(task_id)

        stale = await task_repo.update_stage(
            task_id=task_id,
            owner="proc-a",
            claim_generation=int(winner_task.claim_generation),
            workflow=_workflow(now, "solution_fill_check"),
            correction=None,
            due_at=now,
            now=now,
        )
        after = await _task_row(task_id)
        assert stale is None
        assert after["status"] == "claimed"
        assert after["claimed_by"] == "proc-b"
        assert int(after["claim_generation"]) == int(winner_task.claim_generation)
        assert after["current_stage"] == "startup"
        assert after["corr_step"] == "corr_check"
        assert after == before
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_concurrent_claims_leave_one_owner_and_no_claimed_without_lease() -> None:
    prefix = f"ae3-gen-race-{uuid4().hex}"
    now = _now()
    task_repo = PgAutomationTaskRepository()
    conn_a = await _connect()
    conn_b = await _connect()
    started = asyncio.Event()
    try:
        pid_a = int(await conn_a.fetchval("SELECT pg_backend_pid()"))
        pid_b = int(await conn_b.fetchval("SELECT pg_backend_pid()"))
        assert pid_a != pid_b

        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(zone_id=zone_id, idempotency_key=f"{prefix}-task", now=now)

        async def _claim(conn: asyncpg.Connection, owner: str, run_id: str):
            await started.wait()
            return await task_repo.claim_pending_task_with_zone_lease(
                task_id=task_id,
                owner=owner,
                process_run_id=run_id,
                now=now,
                lease_ttl_sec=120,
                conn=conn,
            )

        first = asyncio.create_task(_claim(conn_a, "proc-a", "run-a"))
        second = asyncio.create_task(_claim(conn_b, "proc-b", "run-b"))
        started.set()
        results = await asyncio.gather(first, second)
        winners = [item for item in results if item is not None]
        assert len(winners) == 1
        winner_task, winner_lease = winners[0]
        row = await _task_row(task_id)
        lease = await _lease_row(zone_id)
        assert row["status"] == "claimed"
        assert row["claimed_by"] == winner_task.claimed_by
        assert int(row["claim_generation"]) == int(winner_task.claim_generation)
        assert lease is not None
        assert lease["owner"] == winner_lease.owner
        assert int(lease["claim_generation"]) == int(winner_task.claim_generation)
        claimed_without_lease = await fetch(
            """
            SELECT tasks.id
            FROM ae_tasks tasks
            LEFT JOIN ae_zone_leases leases ON leases.zone_id = tasks.zone_id
            WHERE tasks.id = $1
              AND tasks.status = 'claimed'
              AND leases.zone_id IS NULL
            """,
            task_id,
        )
        assert claimed_without_lease == []
    finally:
        await conn_a.close()
        await conn_b.close()
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_lease_conflict_rolls_back_claim_inside_one_transaction() -> None:
    prefix = f"ae3-gen-rollback-{uuid4().hex}"
    now = _now()
    task_repo = PgAutomationTaskRepository()
    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(zone_id=zone_id, idempotency_key=f"{prefix}-task", now=now)
        await execute(
            """
            INSERT INTO ae_zone_leases (
                zone_id, owner, leased_until, updated_at, claim_generation, process_run_id
            )
            VALUES ($1, 'other-proc', $2, $3, 7, 'other-run')
            """,
            zone_id,
            now + timedelta(minutes=5),
            now,
        )
        claimed = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-a",
            process_run_id="run-a",
            now=now,
            lease_ttl_sec=120,
        )
        assert claimed is None
        row = await _task_row(task_id)
        lease = await _lease_row(zone_id)
        assert row["status"] == "pending"
        assert row["claimed_by"] is None
        assert lease is not None
        assert lease["owner"] == "other-proc"
        assert int(lease["claim_generation"]) == 7
        assert lease["process_run_id"] == "other-run"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_recovery_operator_and_old_token_do_not_touch_new_generation() -> None:
    prefix = f"ae3-gen-recovery-{uuid4().hex}"
    now = _now()
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    command_repo = PgAeCommandRepository()
    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(zone_id=zone_id, idempotency_key=f"{prefix}-task", now=now)
        first = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-a",
            process_run_id="run-a",
            now=now,
            lease_ttl_sec=300,
        )
        assert first is not None
        old_task, _old_lease = first
        requeued = await task_repo.update_stage(
            task_id=task_id,
            owner="proc-a",
            claim_generation=int(old_task.claim_generation),
            workflow=_workflow(now, "startup"),
            correction=None,
            due_at=now,
            now=now,
        )
        assert requeued is not None
        winner = await task_repo.claim_pending_task_with_zone_lease(
            task_id=task_id,
            owner="proc-a",
            process_run_id="run-a",
            now=now,
            lease_ttl_sec=300,
        )
        assert winner is not None
        await execute("UPDATE ae_tasks SET corr_step = 'corr_check' WHERE id = $1", task_id)
        fresh = await task_repo.get_by_id(task_id=task_id)
        assert fresh is not None
        stale_view = replace(fresh, claim_generation=int(old_task.claim_generation))
        before = await _task_row(task_id)
        lease_before = await _lease_row(zone_id)

        recovery = StartupRecoveryUseCase(
            task_repository=task_repo,
            lease_repository=lease_repo,
            command_gateway=object(),
            workflow_repository=None,
            use_startup_recovery_lock=False,
        )
        updated = await recovery._task_repo_update_stage(
            task=stale_view,
            workflow=_workflow(now, "solution_fill_check"),
            now=now,
        )
        completed = await task_repo.mark_completed(
            task_id=task_id,
            owner=str(stale_view.claimed_by or ""),
            now=now,
            claim_generation=int(stale_view.claim_generation),
        )
        with pytest.raises(StartupRecoveryError):
            await recovery._fail_task(
                task=stale_view,
                error_code="startup_recovery_unknown_stage",
                error_message="old token",
                now=now,
            )
        await recovery._release_lease_after_recovery_fail(task=stale_view, now=now)

        janitor = StaleTaskReconcileUseCase(
            task_repository=task_repo,
            lease_repository=lease_repo,
        )
        janitor_failed = await task_repo.fail_for_recovery(
            task_id=task_id,
            error_code="ae3_stale_task_reclaimed",
            error_message="old token",
            now=now,
            owner=str(stale_view.claimed_by or ""),
            claim_generation=int(stale_view.claim_generation),
        )
        await janitor._release_lease_after_action(task=stale_view, now=now)

        operator = OperatorUnblockZoneUseCase(
            task_repository=task_repo,
            workflow_repository=object(),
            lease_repository=lease_repo,
        )
        await operator._fail_active_task(task=stale_view, now=now, reason="old token")
        await operator._release_lease(task=stale_view, now=now)

        escalated = await escalate_foreign_lease_stale_task(
            task_repository=task_repo,
            alert_repository=None,
            task=stale_view,
            now=now,
            recovery_source="test",
            lease_context=ForeignLeaseContext(lease_owner="proc-a", leased_until=now + timedelta(minutes=5)),
        )
        allocated = await command_repo.allocate_and_create_pending(
            task_id=task_id,
            zone_id=zone_id,
            node_uid="node-a",
            channel="pump",
            payload={"cmd": "run_pump"},
            now=now,
            stage_name="startup",
            planner_step="old-token",
            owner=str(stale_view.claimed_by or ""),
            claim_generation=int(stale_view.claim_generation),
        )
        command_rows = await fetch(
            "SELECT id FROM ae_commands WHERE task_id = $1",
            task_id,
        )

        after = await _task_row(task_id)
        lease_after = await _lease_row(zone_id)
        assert updated is None
        assert completed is None
        assert janitor_failed is None
        assert escalated is None
        assert allocated is None
        assert command_rows == []
        assert after == before
        assert lease_after == lease_before
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_previous_task_cannot_release_or_extend_next_task_lease():
    prefix = f"ae3-cross-task-{uuid4().hex[:12]}"
    repo = PgAutomationTaskRepository()
    leases = PgZoneLeaseRepository()
    now = _now()
    try:
        zone = await _insert_zone(prefix)
        first_id = await _insert_task(zone_id=zone, idempotency_key=prefix + '-a', now=now)
        first, _ = await repo.claim_pending_task_with_zone_lease(
            task_id=first_id, owner="same-worker", process_run_id="same-process", now=now, lease_ttl_sec=300,
        )
        await repo.mark_completed(task_id=first.id, owner=first.claimed_by, claim_generation=first.claim_generation, now=now)
        second_id = await _insert_task(zone_id=zone, idempotency_key=prefix + '-b', now=now)
        second, _ = await repo.claim_pending_task_with_zone_lease(
            task_id=second_id, owner="same-worker", process_run_id="same-process", now=now, lease_ttl_sec=300,
        )
        assert second.claim_generation > first.claim_generation
        assert not await leases.release(zone_id=zone, owner=first.claimed_by, claim_generation=first.claim_generation)
        assert not await leases.extend(zone_id=zone, owner=first.claimed_by, claim_generation=first.claim_generation, now=now, lease_ttl_sec=300)
        lease = await leases.get(zone_id=zone)
        assert lease.claim_generation == second.claim_generation
        # An expired lease cannot be revived by an old heartbeat either.
        assert not await leases.extend(zone_id=zone, owner=second.claimed_by, claim_generation=second.claim_generation, now=now + timedelta(seconds=301), lease_ttl_sec=300)
    finally:
        await _cleanup(prefix)
