from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.infrastructure.repositories import PgAutomationTaskRepository
from common.db import execute, fetch


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


async def _insert_waiting_task(zone_id: int, *, prefix: str, now: datetime) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key,
            scheduled_for, due_at, claimed_by, claimed_at,
            created_at, updated_at,
            topology, current_stage, workflow_phase
        )
        VALUES (
            $1, 'cycle_start', 'waiting_command', $2,
            $3, $3, 'worker-a', $3,
            $3, $3,
            'two_tank', 'clean_fill_stop_to_solution', 'tank_filling'
        )
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
        now,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_update_stage_requeues_waiting_command_task_as_pending() -> None:
    prefix = f"ae3-requeue-waiting-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_waiting_task(zone_id, prefix=prefix, now=now)

        requeued = await task_repo.update_stage(
            task_id=task_id,
            owner="worker-a",
            workflow=WorkflowState(
                current_stage="solution_fill_start",
                workflow_phase="tank_filling",
                stage_deadline_at=now + timedelta(seconds=30),
                stage_retry_count=0,
                stage_entered_at=now,
                clean_fill_cycle=0,
            ),
            correction=None,
            due_at=now - timedelta(seconds=1),
            now=now,
        )

        assert requeued is not None
        assert requeued.status == "pending"
        assert requeued.current_stage == "solution_fill_start"
        assert requeued.claimed_by is None
        assert requeued.claimed_at is None

        rows = await fetch(
            """
            SELECT status, current_stage, claimed_by, claimed_at
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        assert str(rows[0]["status"]).lower() == "pending"
        assert str(rows[0]["current_stage"]) == "solution_fill_start"
        assert rows[0]["claimed_by"] is None
        assert rows[0]["claimed_at"] is None
    finally:
        await _cleanup(prefix)
