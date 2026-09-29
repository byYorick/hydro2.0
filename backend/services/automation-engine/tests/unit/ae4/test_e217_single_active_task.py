"""E217: вторая активная задача зоны ae4 не создаётся."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from common.db import fetch


async def _insert_greenhouse() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        f"gh-{uuid4().hex[:20]}",
        "e217",
        f"gh_{uuid4().hex[:24]}",
    )
    return int(rows[0]["id"])


async def _insert_zone(greenhouse_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (
            greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'online', 'ae4', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        "e217-zone",
        f"zn-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def test_e217_second_active_task_not_created() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    greenhouse_id = await _insert_greenhouse()
    zone_id = await _insert_zone(greenhouse_id)
    repo = PgAutomationTaskRepository()

    first = await repo.create_pending_if_idle(
        zone_id=zone_id,
        idempotency_key=f"e217-a-{uuid4().hex}",
        task_type="irrigation_start",
        current_stage="probe_command",
        workflow_phase="idle",
        scheduled_for=now,
        due_at=now,
        now=now,
        intent_meta={"kind": "probe_command"},
    )
    assert first is not None

    second = await repo.create_pending_if_idle(
        zone_id=zone_id,
        idempotency_key=f"e217-b-{uuid4().hex}",
        task_type="irrigation_start",
        current_stage="probe_command",
        workflow_phase="idle",
        scheduled_for=now,
        due_at=now,
        now=now,
        intent_meta={"kind": "probe_command"},
    )
    assert second is None

    rows = await fetch(
        """
        SELECT COUNT(*)::int AS cnt
        FROM ae_tasks
        WHERE zone_id = $1
          AND status = ANY($2::text[])
        """,
        zone_id,
        ["pending", "claimed", "running", "waiting_command"],
    )
    assert int(rows[0]["cnt"]) == 1
