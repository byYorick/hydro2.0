from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import ClaimNextTaskUseCase
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.infrastructure.repositories import PgAutomationTaskRepository, PgZoneLeaseRepository
from common.db import execute, fetch


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


async def _insert_task(
    *,
    zone_id: int,
    idempotency_key: str,
    due_at: datetime,
    scheduled_for: datetime,
    overall_deadline_at: datetime | None = None,
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
            created_at,
            updated_at,
            topology,
            current_stage,
            workflow_phase,
            overall_deadline_at
        )
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $4, $3, $3, 'two_tank', 'startup', 'idle', $5)
        RETURNING id
        """,
        zone_id,
        idempotency_key,
        scheduled_for,
        due_at,
        overall_deadline_at,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
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


async def _isolate_claim_queue(*, now: datetime) -> None:
    """Убирает чужие pending-задачи из очереди claim для детерминизма integration-тестов."""
    await execute(
        """
        UPDATE ae_tasks
        SET status = 'failed',
            error_code = 'test_isolation',
            error_message = 'cleared for claim_next_task integration test',
            updated_at = $1
        WHERE status = 'pending'
          AND (due_at <= $1 OR overall_deadline_at <= $1)
        """,
        now,
    )


@pytest.mark.asyncio
async def test_claim_next_task_claims_earliest_due_pending_task() -> None:
    prefix = f"ae3-claim-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_one = await _insert_zone(f"{prefix}-zone-1")
        zone_two = await _insert_zone(f"{prefix}-zone-2")
        older_task_id = await _insert_task(
            zone_id=zone_one,
            idempotency_key=f"{prefix}-older",
            scheduled_for=now - timedelta(minutes=2),
            due_at=now - timedelta(minutes=1),
        )
        await _insert_task(
            zone_id=zone_two,
            idempotency_key=f"{prefix}-newer",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now,
        )

        result = await use_case.run(owner="worker-a", now=now, process_run_id=f"{prefix}-run-a")

        assert result is not None
        task, lease = result
        assert task.id == older_task_id
        assert task.status == "claimed"
        assert lease.zone_id == zone_one
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_claim_next_task_is_not_double_claimed_by_parallel_workers() -> None:
    prefix = f"ae3-race-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=5),
        )

        results = await asyncio.gather(
            use_case.run(owner="worker-a", now=now, process_run_id=f"{prefix}-run-a"),
            use_case.run(owner="worker-b", now=now, process_run_id=f"{prefix}-run-b"),
        )

        claimed = [item for item in results if item is not None]
        assert len(claimed) == 1

        rows = await fetch(
            """
            SELECT status, claimed_by
            FROM ae_tasks
            WHERE zone_id = $1
            """,
            zone_id,
        )
        assert len(rows) == 1
        assert str(rows[0]["status"]).lower() == "claimed"
        assert str(rows[0]["claimed_by"]) in {"worker-a", "worker-b"}
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_claim_next_task_reverts_claim_when_zone_lease_is_busy() -> None:
    prefix = f"ae3-busy-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=10),
        )
        await execute(
            """
            INSERT INTO ae_zone_leases (zone_id, owner, leased_until, updated_at)
            VALUES ($1, $2, $3, $4)
            """,
            zone_id,
            "busy-worker",
            now + timedelta(minutes=5),
            now,
        )

        result = await use_case.run(owner="new-worker", now=now, process_run_id=f"{prefix}-run-new")

        assert result is None
        rows = await fetch(
            """
            SELECT status, claimed_by, claimed_at, corr_limit_policy_logged
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert str(rows[0]["status"]).lower() == "pending"
        assert rows[0]["claimed_by"] is None
        assert rows[0]["claimed_at"] is None
        assert rows[0]["corr_limit_policy_logged"] is False
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_update_stage_requeues_task_as_unclaimed_pending() -> None:
    prefix = f"ae3-requeue-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=5),
        )

        claimed = await use_case.run(owner="worker-a", now=now, process_run_id=f"{prefix}-run-a")
        assert claimed is not None
        claimed_task, _lease = claimed
        assert claimed_task.id == task_id

        requeued = await task_repo.update_stage(
            task_id=task_id,
            owner="worker-a",
            workflow=WorkflowState(
                current_stage="prepare_recirculation_check",
                workflow_phase="tank_recirc",
                stage_deadline_at=now + timedelta(seconds=30),
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=1,
            ),
            correction=None,
            due_at=now - timedelta(seconds=1),
            now=now,
            claim_generation=int(claimed_task.claim_generation),
        )
        assert requeued is not None
        assert requeued.status == "pending"
        assert requeued.claimed_by is None
        assert requeued.claimed_at is None

        rows = await fetch(
            """
            SELECT status, claimed_by, claimed_at
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert str(rows[0]["status"]).lower() == "pending"
        assert rows[0]["claimed_by"] is None
        assert rows[0]["claimed_at"] is None

        released = await lease_repo.release(
            zone_id=zone_id,
            owner="worker-a",
            claim_generation=int(claimed_task.claim_generation),
        )
        assert released is True

        reclaimed = await use_case.run(owner="worker-b", now=now, process_run_id=f"{prefix}-run-b")
        assert reclaimed is not None
        reclaimed_task, reclaimed_lease = reclaimed
        assert reclaimed_task.id == task_id
        assert reclaimed_task.status == "claimed"
        assert reclaimed_task.claimed_by == "worker-b"
        assert reclaimed_lease.zone_id == zone_id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_overall_deadline_persists_across_requeue_and_restart_claim() -> None:
    prefix = f"ae3-deadline-requeue-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
        overall_deadline_sec=60,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=5),
        )

        claimed = await use_case.run(owner="worker-a", now=now, process_run_id=f"{prefix}-run-a")
        assert claimed is not None
        claimed_task, _lease = claimed
        assert claimed_task.id == task_id
        assert claimed_task.overall_deadline_at == now + timedelta(seconds=60)

        requeued_due_at = now + timedelta(hours=1)
        requeued = await task_repo.update_stage(
            task_id=task_id,
            owner="worker-a",
            workflow=WorkflowState(
                current_stage="prepare_recirculation_check",
                workflow_phase="tank_recirc",
                stage_deadline_at=now + timedelta(seconds=30),
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=1,
            ),
            correction=None,
            due_at=requeued_due_at,
            now=now,
            claim_generation=int(claimed_task.claim_generation),
        )
        assert requeued is not None
        assert requeued.status == "pending"
        assert requeued.overall_deadline_at == claimed_task.overall_deadline_at

        released = await lease_repo.release(
            zone_id=zone_id,
            owner="worker-a",
            claim_generation=int(claimed_task.claim_generation),
        )
        assert released is True

        restart_now = now + timedelta(seconds=61)
        restarted_use_case = ClaimNextTaskUseCase(
            task_repository=task_repo,
            zone_lease_repository=lease_repo,
            lease_ttl_sec=120,
            overall_deadline_sec=604800,
        )
        reclaimed = await restarted_use_case.run(
            owner="worker-b",
            now=restart_now,
            process_run_id=f"{prefix}-run-b",
        )

        assert reclaimed is not None
        reclaimed_task, reclaimed_lease = reclaimed
        assert reclaimed_task.id == task_id
        assert reclaimed_task.due_at == requeued_due_at
        assert reclaimed_task.overall_deadline_at == claimed_task.overall_deadline_at
        assert reclaimed_lease.zone_id == zone_id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_claim_next_task_claims_future_due_task_when_overall_deadline_expired() -> None:
    prefix = f"ae3-deadline-future-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now + timedelta(hours=6),
            overall_deadline_at=now - timedelta(seconds=1),
        )

        claimed = await use_case.run(owner="worker-a", now=now, process_run_id=f"{prefix}-run-a")

        assert claimed is not None
        claimed_task, lease = claimed
        assert claimed_task.id == task_id
        assert claimed_task.status == "claimed"
        assert claimed_task.overall_deadline_at == now - timedelta(seconds=1)
        assert lease.zone_id == zone_id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_zone_lease_can_be_reclaimed_after_expiry_or_release() -> None:
    prefix = f"ae3-reclaim-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    lease_repo = PgZoneLeaseRepository()

    try:
        await _isolate_claim_queue(now=now)
        zone_id = await _insert_zone(f"{prefix}-zone")
        await execute(
            """
            INSERT INTO ae_zone_leases (zone_id, owner, leased_until, updated_at)
            VALUES ($1, $2, $3, $4)
            """,
            zone_id,
            "stale-worker",
            now - timedelta(seconds=1),
            now - timedelta(seconds=1),
        )

        reclaimed = await lease_repo.claim(
            zone_id=zone_id,
            owner="worker-a",
            now=now,
            lease_ttl_sec=90,
        )
        assert reclaimed is not None
        assert reclaimed.owner == "worker-a"

        released = await lease_repo.release(
            zone_id=zone_id,
            owner="worker-a",
            claim_generation=int(reclaimed.claim_generation),
        )
        assert released is True

        claimed_after_release = await lease_repo.claim(
            zone_id=zone_id,
            owner="worker-b",
            now=now,
            lease_ttl_sec=90,
        )
        assert claimed_after_release is not None
        assert claimed_after_release.owner == "worker-b"
    finally:
        await _cleanup(prefix)
