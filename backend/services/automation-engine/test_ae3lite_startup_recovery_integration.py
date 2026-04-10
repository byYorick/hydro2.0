from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import StartupRecoveryUseCase
from ae3lite.domain.services.topology_registry import TopologyRegistry
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)
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


async def _insert_task(
    zone_id: int,
    *,
    prefix: str,
    task_status: str,
    now: datetime,
    topology: str = "two_tank",
    current_stage: str = "startup",
    workflow_phase: str = "idle",
    intent_id: int | None = None,
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
            intent_id
        )
        VALUES ($1, 'cycle_start', $2, $3, $4, $4, 'worker-a', $4, $4, $4,
                $5, $6, $7, $8)
        RETURNING id
        """,
        zone_id,
        task_status,
        f"{prefix}-task",
        now,
        topology,
        current_stage,
        workflow_phase,
        intent_id,
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


async def _insert_intent(
    *,
    zone_id: int,
    prefix: str,
    status: str,
    now: datetime,
) -> int:
    rows = await fetch(
        """
        INSERT INTO zone_automation_intents (
            zone_id,
            intent_type,
            payload,
            idempotency_key,
            status,
            claimed_at,
            created_at,
            updated_at
        )
        VALUES ($1, 'start_cycle', '{"workflow":"cycle_start"}'::jsonb, $2, $3, $4, $4, $4)
        RETURNING id
        """,
        zone_id,
        f"{prefix}-intent",
        status,
        now,
    )
    return int(rows[0]["id"])


async def _insert_lease(*, zone_id: int, owner: str, leased_until: datetime, updated_at: datetime) -> None:
    await execute(
        """
        INSERT INTO ae_zone_leases (zone_id, owner, leased_until, updated_at)
        VALUES ($1, $2, $3, $4)
        """,
        zone_id,
        owner,
        leased_until,
        updated_at,
    )


async def _count_ae_commands(*, task_id: int) -> int:
    rows = await fetch(
        """
        SELECT COUNT(*) AS cnt
        FROM ae_commands
        WHERE task_id = $1
        """,
        task_id,
    )
    return int(rows[0]["cnt"])


async def _count_active_recovery_tasks() -> int:
    rows = await fetch(
        """
        SELECT COUNT(*) AS cnt
        FROM ae_tasks
        WHERE status IN ('claimed', 'running', 'waiting_command')
        """
    )
    return int(rows[0]["cnt"])


async def _count_waiting_command_tasks() -> int:
    rows = await fetch(
        """
        SELECT COUNT(*) AS cnt
        FROM ae_tasks
        WHERE status = 'waiting_command'
        """
    )
    return int(rows[0]["cnt"])


async def _cleanup(prefix: str) -> None:
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


class _UnusedHistoryLoggerClient:
    async def publish(self, **kwargs):
        raise AssertionError("history-logger publish must not be used during startup recovery")


def _build_use_case() -> tuple[StartupRecoveryUseCase, PgAutomationTaskRepository, PgAeCommandRepository, PgZoneLeaseRepository]:
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    lease_repo = PgZoneLeaseRepository()
    gateway = SequentialCommandGateway(
        task_repository=task_repo,
        command_repository=command_repo,
        history_logger_client=_UnusedHistoryLoggerClient(),
        poll_interval_sec=0.05,
    )
    recovery_use_case = StartupRecoveryUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        command_gateway=gateway,
    )
    return recovery_use_case, task_repo, command_repo, lease_repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_status", "create_local_command"),
    [
        ("claimed", False),
        ("running", True),
    ],
)
async def test_startup_recovery_fails_task_without_confirmed_external_command(
    task_status: str,
    create_local_command: bool,
) -> None:
    prefix = f"ae3-recovery-unconfirmed-{task_status}-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo = _build_use_case()
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, task_status=task_status, now=now)
        if create_local_command:
            await _insert_ae_command(task_id=task_id, now=now, cmd_id=f"ae3-recovery-missing-{task_status}")

        result = await recovery_use_case.run(now=now + timedelta(seconds=3))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "startup_recovery_unconfirmed_command"
        assert await _count_ae_commands(task_id=task_id) == (1 if create_local_command else 0)
        if create_local_command:
            ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
            assert ae_command is not None
            assert ae_command["external_id"] is None
            assert ae_command["terminal_status"] is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_releases_only_expired_leases() -> None:
    prefix = f"ae3-recovery-leases-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, _task_repo, _command_repo, lease_repo = _build_use_case()
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        expired_zone_id = await _insert_zone(f"{prefix}-expired", greenhouse_id=greenhouse_id)
        fresh_zone_id = await _insert_zone(f"{prefix}-fresh", greenhouse_id=greenhouse_id)
        await _insert_lease(
            zone_id=expired_zone_id,
            owner="worker-expired",
            leased_until=now - timedelta(seconds=30),
            updated_at=now - timedelta(seconds=30),
        )
        await _insert_lease(
            zone_id=fresh_zone_id,
            owner="worker-fresh",
            leased_until=now + timedelta(minutes=5),
            updated_at=now,
        )

        result = await recovery_use_case.run(now=now)

        expired_lease = await lease_repo.get(zone_id=expired_zone_id)
        fresh_lease = await lease_repo.get(zone_id=fresh_zone_id)
        assert result.released_expired_leases == 1
        assert result.scanned_tasks == baseline_scanned
        assert expired_lease is None
        assert fresh_lease is not None
        assert fresh_lease.owner == "worker-fresh"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_native_two_tank_done_requeues_next_stage_without_republish() -> None:
    prefix = f"ae3-recovery-native-two-tank-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    lease_repo = PgZoneLeaseRepository()
    workflow_repo = PgZoneWorkflowRepository()
    gateway = SequentialCommandGateway(
        task_repository=task_repo,
        command_repository=command_repo,
        history_logger_client=_UnusedHistoryLoggerClient(),
        poll_interval_sec=0.05,
    )
    recovery_use_case = StartupRecoveryUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        command_gateway=gateway,
        workflow_repository=workflow_repo,
        topology_registry=TopologyRegistry(),
    )
    baseline_scanned = await _count_active_recovery_tasks()
    baseline_waiting = await _count_waiting_command_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        intent_id = await _insert_intent(zone_id=zone_id, prefix=prefix, status="running", now=now)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=now,
            intent_id=intent_id,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-recovery-native-two-tank-1",
            status="DONE",
            ack_at=now + timedelta(seconds=4),
            now=now + timedelta(seconds=4),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-recovery-native-two-tank-1",
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=5))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.completed_tasks == 0
        assert result.failed_tasks == 0
        assert result.waiting_command_tasks == baseline_waiting + 1
        assert result.recovered_waiting_command_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "pending"
        assert updated_task.current_stage == "clean_fill_check"
        expected_due_at = (now + timedelta(seconds=5)).replace(microsecond=0, tzinfo=None)
        assert updated_task.due_at == expected_due_at
        assert workflow_row is not None
        assert workflow_row.workflow_phase == "tank_filling"
        assert ae_command is not None
        assert ae_command["terminal_status"] == "DONE"
        assert await _count_ae_commands(task_id=task_id) == 1
    finally:
        await _cleanup(prefix)
