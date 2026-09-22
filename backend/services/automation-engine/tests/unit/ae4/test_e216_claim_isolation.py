"""E216: claim AE3 не берёт зону ae4, claim AE4 не берёт зону ae3."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ae3lite.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository as Ae3TaskRepository,
)
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository as Ae4TaskRepository,
)
from ae4.runtime.env import Ae4RuntimeConfig
from ae4.runtime.worker import AE4_WORKER_OWNER, Ae4RuntimeWorker
from common.db import execute, fetch


async def _insert_greenhouse() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:20]}",
        "e216",
        f"gh_{uuid4().hex[:24]}",
    )
    return int(rows[0]["id"])


async def _insert_zone(greenhouse_id: int, *, runtime: str) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', $4, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"e216-{runtime}",
        f"zn-{uuid4().hex[:20]}",
        runtime,
    )
    return int(rows[0]["id"])


async def _insert_task(zone_id: int, *, due_at: datetime) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key,
            scheduled_for, due_at, created_at, updated_at
        )
        VALUES ($1, 'cycle_start', 'pending', $2, $3, $4, $3, $3)
        RETURNING id
        """,
        zone_id,
        f"e216-{uuid4().hex}",
        due_at,
        due_at,
    )
    return int(rows[0]["id"])


async def _park_other_due_tasks(keep_ids: list[int], now: datetime) -> list[tuple[int, datetime]]:
    rows = await fetch(
        """
        SELECT id, due_at
        FROM ae_tasks
        WHERE status = 'pending'
          AND due_at <= $1
          AND NOT (id = ANY($2::bigint[]))
        """,
        now,
        keep_ids,
    )
    parked = [(int(row["id"]), row["due_at"]) for row in rows]
    if not parked:
        return []
    await execute(
        """
        UPDATE ae_tasks
        SET due_at = $1
        WHERE id = ANY($2::bigint[])
        """,
        now + timedelta(days=3650),
        [task_id for task_id, _due_at in parked],
    )
    return parked


async def _release_claim(task_id: int, owner: str) -> None:
    await execute(
        """
        UPDATE ae_tasks
        SET status = 'pending',
            claimed_by = NULL,
            claimed_at = NULL,
            updated_at = NOW()
        WHERE id = $1
          AND status = 'claimed'
          AND claimed_by = $2
        """,
        task_id,
        owner,
    )


async def _restore_due_at(parked: list[tuple[int, datetime]]) -> None:
    for task_id, due_at in parked:
        await execute(
            "UPDATE ae_tasks SET due_at = $2 WHERE id = $1",
            task_id,
            due_at,
        )


async def test_e216_workers_claim_only_their_runtime() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    greenhouse_id: int | None = None
    zone_ae3: int | None = None
    zone_ae4: int | None = None
    zone_ae4_later: int | None = None
    parked: list[tuple[int, datetime]] = []
    try:
        greenhouse_id = await _insert_greenhouse()
        zone_ae3 = await _insert_zone(greenhouse_id, runtime="ae3")
        zone_ae4 = await _insert_zone(greenhouse_id, runtime="ae4")
        zone_ae4_later = await _insert_zone(greenhouse_id, runtime="ae4")
        old_due = datetime(2000, 1, 1, tzinfo=timezone.utc)
        task_ae4 = await _insert_task(zone_ae4, due_at=old_due)
        task_ae3 = await _insert_task(zone_ae3, due_at=now)
        future_ae4 = await _insert_task(zone_ae4_later, due_at=now + timedelta(days=1))
        parked = await _park_other_due_tasks([task_ae3, task_ae4, future_ae4], now)
        ae3_repo = Ae3TaskRepository()
        ae4_worker = Ae4RuntimeWorker(
            config=Ae4RuntimeConfig(reconcile_poll_interval_sec=0.5),
            repository=Ae4TaskRepository(),
        )

        claimed_ae3 = await ae3_repo.claim_next_pending(owner="ae3-runtime-worker", now=now)
        if claimed_ae3 is not None and int(claimed_ae3.id) != task_ae3:
            await _release_claim(int(claimed_ae3.id), "ae3-runtime-worker")
        assert claimed_ae3 is not None
        assert int(claimed_ae3.id) == task_ae3
        assert int(claimed_ae3.zone_id) == zone_ae3

        claimed_ae4 = await ae4_worker.claim_next(now=now)
        if claimed_ae4 is not None and claimed_ae4.id != task_ae4:
            await _release_claim(claimed_ae4.id, AE4_WORKER_OWNER)
        assert claimed_ae4 is not None
        assert claimed_ae4.id == task_ae4
        assert claimed_ae4.zone_id == zone_ae4
        assert claimed_ae4.claimed_by == AE4_WORKER_OWNER

        assert await ae3_repo.claim_next_pending(owner="ae3-runtime-worker", now=now) is None
        assert await ae4_worker.claim_next(now=now) is None

        future_rows = await fetch("SELECT status, due_at FROM ae_tasks WHERE id = $1", future_ae4)
        assert future_rows[0]["status"] == "pending"
    finally:
        await _restore_due_at(parked)
        zone_ids = [
            zone_id
            for zone_id in (zone_ae3, zone_ae4, zone_ae4_later)
            if zone_id is not None
        ]
        if zone_ids:
            await execute(
                "DELETE FROM ae_tasks WHERE zone_id = ANY($1::bigint[])",
                zone_ids,
            )
            await execute("DELETE FROM zones WHERE id = ANY($1::bigint[])", zone_ids)
        if greenhouse_id is not None:
            await execute("DELETE FROM greenhouses WHERE id = $1", greenhouse_id)
