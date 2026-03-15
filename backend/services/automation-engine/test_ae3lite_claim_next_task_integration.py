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
            workflow_phase
        )
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $4, $3, $3, 'two_tank', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        idempotency_key,
        scheduled_for,
        due_at,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM zones WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_claim_next_task_claims_earliest_due_pending_task() -> None:
    prefix = f"ae3-claim-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
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

        result = await use_case.run(owner="worker-a", now=now)

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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=5),
        )

        results = await asyncio.gather(
            use_case.run(owner="worker-a", now=now),
            use_case.run(owner="worker-b", now=now),
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
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

        result = await use_case.run(owner="new-worker", now=now)

        assert result is None
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
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_update_stage_requeues_task_as_unclaimed_pending() -> None:
    prefix = f"ae3-requeue-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=120,
    )

    try:
        zone_id = await _insert_zone(f"{prefix}-zone")
        task_id = await _insert_task(
            zone_id=zone_id,
            idempotency_key=f"{prefix}-task",
            scheduled_for=now - timedelta(minutes=1),
            due_at=now - timedelta(seconds=5),
        )

        claimed = await use_case.run(owner="worker-a", now=now)
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

        released = await lease_repo.release(zone_id=zone_id, owner="worker-a")
        assert released is True

        reclaimed = await use_case.run(owner="worker-b", now=now)
        assert reclaimed is not None
        reclaimed_task, reclaimed_lease = reclaimed
        assert reclaimed_task.id == task_id
        assert reclaimed_task.status == "claimed"
        assert reclaimed_task.claimed_by == "worker-b"
        assert reclaimed_lease.zone_id == zone_id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_zone_lease_can_be_reclaimed_after_expiry_or_release() -> None:
    prefix = f"ae3-reclaim-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lease_repo = PgZoneLeaseRepository()

    try:
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

        released = await lease_repo.release(zone_id=zone_id, owner="worker-a")
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
