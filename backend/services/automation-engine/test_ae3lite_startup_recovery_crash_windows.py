"""Контрактные crash-window тесты startup recovery (ae3lite.md §9.2, план фазы 5).

Каждый тест моделирует точку «краша» AE3 runtime и фиксирует ожидаемое
поведение recovery/reconcile без republish в MQTT.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.infrastructure.repositories import PgAutomationTaskRepository
from common.db import execute, fetch

from test_ae3lite_startup_recovery_integration import (
    _build_use_case,
    _build_waiting_command_reconcile_use_case,
    _cleanup,
    _count_ae_commands,
    _insert_ae_command,
    _insert_greenhouse,
    _insert_legacy_command,
    _insert_task,
    _insert_zone,
)

pytestmark = [pytest.mark.integration, pytest.mark.crash_window]


async def _count_active_recovery_tasks() -> int:
    rows = await fetch(
        """
        SELECT COUNT(*) AS cnt
        FROM ae_tasks
        WHERE status IN ('claimed', 'running', 'waiting_command')
        """
    )
    return int(rows[0]["cnt"])


async def _sweep_orphans(now: datetime) -> None:
    recovery_use_case, *_ = _build_use_case()
    await recovery_use_case.run(now=now)


@pytest.mark.asyncio
async def test_w1_crash_before_ae_commands_insert_fails_on_startup_recovery() -> None:
    """W1a: crash до insert `ae_commands` → startup recovery fail-closed."""
    prefix = f"ae3-cw-w1a-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, _command_repo, _lease_repo, _alerts = _build_use_case()
    await _sweep_orphans(now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=1))

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "startup_recovery_unconfirmed_command"
        assert await _count_ae_commands(task_id=task_id) == 0
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_w1_crash_before_ae_commands_insert_requeues_on_graceful_shutdown() -> None:
    """W1b: crash до insert `ae_commands` → phase-4 requeue `claimed` → `pending`."""
    prefix = f"ae3-cw-w1b-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )

        requeued = await task_repo.requeue_unpublished_execution(
            task_id=task_id,
            owner="worker-a",
            now=now + timedelta(seconds=1),
        )

        updated = await task_repo.get_by_id(task_id=task_id)
        assert requeued is not None
        assert requeued.status == "pending"
        assert requeued.claimed_by is None
        assert updated is not None
        assert updated.status == "pending"
        assert await _count_ae_commands(task_id=task_id) == 0
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_w2_crash_after_ae_commands_insert_before_publish_waits() -> None:
    """W2: crash после insert `ae_commands`, до publish → `waiting_command`."""
    prefix = f"ae3-cw-w2-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo, _alerts = _build_use_case()
    await _sweep_orphans(now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id=f"{prefix}-cmd",
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=2))

        updated = await task_repo.get_by_id(task_id=task_id)
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert result.waiting_command_tasks == 1
        assert updated is not None
        assert updated.status == "waiting_command"
        assert ae_command is not None
        assert ae_command["external_id"] is None
        assert ae_command["terminal_status"] is None
        assert await _count_ae_commands(task_id=task_id) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_w3_crash_after_publish_before_waiting_command_persists_waiting() -> None:
    """W3: crash после publish, до `waiting_command` → reconcile оставляет waiting."""
    prefix = f"ae3-cw-w3-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo, _alerts = _build_use_case()
    await _sweep_orphans(now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id=f"{prefix}-cmd",
            status="ACK",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id=f"{prefix}-cmd",
            external_id=str(legacy_id),
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=2))

        updated = await task_repo.get_by_id(task_id=task_id)
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert result.waiting_command_tasks == 1
        assert updated is not None
        assert updated.status == "waiting_command"
        assert ae_command is not None
        assert ae_command["terminal_status"] is None
        assert await _count_ae_commands(task_id=task_id) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_w4_crash_in_waiting_command_recovers_without_republish() -> None:
    """W4: crash в `waiting_command` → recovery без новых `ae_commands`."""
    prefix = f"ae3-cw-w4-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo, _alerts = _build_use_case()
    await _sweep_orphans(now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id=f"{prefix}-cmd",
            status="ACK",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id=f"{prefix}-cmd",
            external_id=str(legacy_id),
        )
        before_count = await _count_ae_commands(task_id=task_id)

        result = await recovery_use_case.run(now=now + timedelta(seconds=2))

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert result.waiting_command_tasks == 1
        assert updated is not None
        assert updated.status == "waiting_command"
        assert await _count_ae_commands(task_id=task_id) == before_count == 1
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert ae_command is not None
        assert ae_command["terminal_status"] is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_w5_delayed_terminal_done_after_restart_advances_stage() -> None:
    """W5: terminal DONE после restart → reconcile продвигает stage без republish."""
    prefix = f"ae3-cw-w5-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reconcile_use_case, _recovery, task_repo, command_repo, workflow_repo = (
        _build_waiting_command_reconcile_use_case()
    )

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=now,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id=f"{prefix}-cmd",
            status="ACK",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id=f"{prefix}-cmd",
            external_id=str(legacy_id),
        )

        first = await reconcile_use_case.run(now=now + timedelta(seconds=2), worker_owner="worker-a")
        assert first.progressed_tasks == 0
        assert await _count_ae_commands(task_id=task_id) == 1

        await execute(
            """
            UPDATE commands
            SET status = 'DONE',
                ack_at = $2,
                updated_at = $2
            WHERE id = $1
            """,
            legacy_id,
            now + timedelta(seconds=5),
        )

        second = await reconcile_use_case.run(now=now + timedelta(seconds=6), worker_owner="worker-a")
        updated = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)

        assert second.progressed_tasks == 1
        assert updated is not None
        assert updated.status == "pending"
        assert updated.current_stage == "clean_fill_check"
        assert workflow_row is not None
        assert workflow_row.payload.get("ae3_cycle_start_stage") == "clean_fill_check"
        assert ae_command is not None
        assert ae_command["terminal_status"] == "DONE"
        assert await _count_ae_commands(task_id=task_id) == 1
    finally:
        await _cleanup(prefix)
