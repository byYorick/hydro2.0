from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.infrastructure.read_models import PgTaskStatusReadModel
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


async def _insert_zone(prefix: str, *, greenhouse_id: int, automation_runtime: str) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', $4, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"{prefix}-zone",
        f"zn-{uuid4().hex[:20]}",
        automation_runtime,
    )
    return int(rows[0]["id"])


async def _insert_task(zone_id: int, *, prefix: str, status: str, now: datetime) -> int:
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
            completed_at,
            topology,
            current_stage,
            workflow_phase
        )
        VALUES ($1, 'cycle_start', $2, $3, $4, $4, 'worker-a', $4, $4, $4, NULL, 'two_tank', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        status,
        f"{prefix}-task",
        now,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_task_status_read_model_returns_canonical_view_for_ae3_zone() -> None:
    prefix = f"ae3-task-status-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    read_model = PgTaskStatusReadModel()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id, automation_runtime="ae3")
        task_id = await _insert_task(zone_id, prefix=prefix, status="waiting_command", now=now)

        view = await read_model.get_by_task_id(task_id=task_id)

        assert view is not None
        assert view.task_id == task_id
        assert view.zone_id == zone_id
        assert view.task_type == "cycle_start"
        assert view.status == "waiting_command"
        assert view.error_code is None
        assert view.completed_at is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_task_status_read_model_hides_tasks_for_non_ae3_zone() -> None:
    prefix = f"ae3-task-status-hidden-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    read_model = PgTaskStatusReadModel()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id, automation_runtime="ae2")
        task_id = await _insert_task(zone_id, prefix=prefix, status="completed", now=now)

        view = await read_model.get_by_task_id(task_id=task_id)

        assert view is None
    finally:
        await _cleanup(prefix)
