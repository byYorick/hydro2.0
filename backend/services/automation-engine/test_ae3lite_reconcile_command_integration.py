from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import ReconcileCommandUseCase
from ae3lite.infrastructure.repositories import PgAeCommandRepository, PgAutomationTaskRepository
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


async def _insert_task(zone_id: int, *, prefix: str, now: datetime) -> int:
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
            workflow_phase
        )
        VALUES ($1, 'cycle_start', 'waiting_command', $2, $3, $3, 'worker-a', $3, $3, $3, 'two_tank', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        f"{prefix}-task",
        now,
    )
    return int(rows[0]["id"])


async def _insert_ae_command(
    *,
    task_id: int,
    now: datetime,
    cmd_id: str,
    external_id: str | None = None,
) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_commands (
            task_id,
            step_no,
            node_uid,
            channel,
            payload,
            external_id,
            publish_status,
            created_at,
            updated_at
        )
        VALUES (
            $1,
            1,
            'nd-irrig-1',
            'pump_main',
            $2::jsonb,
            $3::varchar,
            CASE WHEN $3::varchar IS NULL THEN 'pending' ELSE 'accepted' END,
            $4,
            $4
        )
        RETURNING id
        """,
        task_id,
        {"cmd": "set_relay", "params": {"state": True}, "cmd_id": cmd_id},
        external_id,
        now,
    )
    return int(rows[0]["id"])


async def _insert_legacy_command(
    *,
    zone_id: int,
    cmd_id: str,
    status: str,
    now: datetime,
    ack_at: datetime | None = None,
    failed_at: datetime | None = None,
    error_message: str | None = None,
) -> int:
    rows = await fetch(
        """
        INSERT INTO commands (
            zone_id,
            channel,
            cmd,
            params,
            status,
            cmd_id,
            source,
            ack_at,
            failed_at,
            error_message,
            created_at,
            updated_at
        )
        VALUES ($1, 'pump_main', 'set_relay', '{"state": true}'::jsonb, $2, $3, 'automation-engine', $4, $5, $6, $7, $7)
        RETURNING id
        """,
        zone_id,
        status,
        cmd_id,
        ack_at,
        failed_at,
        error_message,
        now,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_reconcile_command_backfills_external_id_and_completes_task_on_done() -> None:
    prefix = f"ae3-reconcile-done-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    use_case = ReconcileCommandUseCase(task_repository=task_repo, command_repository=command_repo)

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, now=now)
        await _insert_ae_command(task_id=task_id, now=now, cmd_id="ae3-cmd-done-1")
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-cmd-done-1",
            status="DONE",
            ack_at=now + timedelta(seconds=5),
            now=now + timedelta(seconds=5),
        )

        task = await task_repo.get_by_id(task_id=task_id)
        result = await use_case.run(task=task, now=now + timedelta(seconds=6))

        row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.is_terminal is True
        assert result.terminal_status == "DONE"
        assert result.external_id == str(legacy_id)
        assert row is not None
        assert row["external_id"] == str(legacy_id)
        assert row["terminal_status"] == "DONE"
        assert row["ack_received_at"] is not None

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert updated_task is not None
        assert updated_task.status == "completed"
        assert updated_task.completed_at is not None
        assert updated_task.error_code is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_reconcile_command_fails_task_on_timeout_terminal() -> None:
    prefix = f"ae3-reconcile-timeout-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    use_case = ReconcileCommandUseCase(task_repository=task_repo, command_repository=command_repo)

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, now=now)
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-cmd-timeout-1",
            status="TIMEOUT",
            failed_at=now + timedelta(seconds=8),
            error_message="closed_loop_timeout",
            now=now + timedelta(seconds=8),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-cmd-timeout-1",
            external_id=str(legacy_id),
        )

        task = await task_repo.get_by_id(task_id=task_id)
        result = await use_case.run(task=task, now=now + timedelta(seconds=9))

        row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.is_terminal is True
        assert result.terminal_status == "TIMEOUT"
        assert row is not None
        assert row["terminal_status"] == "TIMEOUT"
        assert "closed_loop_timeout" in str(row["last_error"])

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "command_timeout"
        assert "closed_loop_timeout" in str(updated_task.error_message)
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_reconcile_command_keeps_waiting_on_ack_non_terminal() -> None:
    prefix = f"ae3-reconcile-ack-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    use_case = ReconcileCommandUseCase(task_repository=task_repo, command_repository=command_repo)

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, now=now)
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-cmd-ack-1",
            status="ACK",
            ack_at=now + timedelta(seconds=4),
            now=now + timedelta(seconds=4),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-cmd-ack-1",
            external_id=str(legacy_id),
        )

        task = await task_repo.get_by_id(task_id=task_id)
        result = await use_case.run(task=task, now=now + timedelta(seconds=5))

        row = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.is_terminal is False
        assert result.terminal_status is None
        assert result.legacy_status == "ACK"
        assert row is not None
        assert row["terminal_status"] is None
        assert row["ack_received_at"] is not None

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert updated_task is not None
        assert updated_task.status == "waiting_command"
        assert updated_task.completed_at is None
    finally:
        await _cleanup(prefix)
