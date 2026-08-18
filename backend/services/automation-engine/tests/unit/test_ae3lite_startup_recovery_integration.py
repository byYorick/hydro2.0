from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases import StartupRecoveryUseCase, WaitingCommandReconcileUseCase
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)
from common.db import execute, fetch


class _AlertRepositoryRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def raise_active(self, **kwargs):
        self.calls.append(kwargs)
        return True


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
    task_type: str = "cycle_start",
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
        VALUES ($1, $2, $3, $4, $5, $5, 'worker-a', $5, $5, $5,
                $6, $7, $8, $9)
        RETURNING id
        """,
        zone_id,
        task_type,
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
    planner_step: str | None = "test-stage:0:pump_main",
    step_no: int = 1,
    node_uid: str = "nd-irrig-1",
    channel: str = "pump_main",
    payload: dict | None = None,
) -> int:
    rows = await fetch(
        """
        INSERT INTO ae_commands (
            task_id,
            step_no,
            planner_step,
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
            $5,
            $6,
            $7,
            $8,
            $2::jsonb,
            $3::varchar,
            CASE WHEN $3::varchar IS NULL THEN 'pending' ELSE 'accepted' END,
            $4,
            $4
        )
        RETURNING id
        """,
        task_id,
        payload or {"cmd": "set_relay", "params": {"state": True}, "cmd_id": cmd_id},
        external_id,
        now,
        step_no,
        planner_step,
        node_uid,
        channel,
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


async def _insert_zone_workflow_state(
    zone_id: int,
    *,
    workflow_phase: str,
    payload: dict,
    scheduler_task_id: str | None,
    now: datetime,
) -> None:
    await execute(
        """
        INSERT INTO zone_workflow_state (
            zone_id, workflow_phase, started_at, updated_at, payload, scheduler_task_id, version
        )
        VALUES ($1, $2, $3, $3, $4::jsonb, $5, 1)
        """,
        zone_id,
        workflow_phase,
        now,
        payload,
        scheduler_task_id,
    )


async def _insert_pending_irrigation_task(
    zone_id: int,
    *,
    prefix: str,
    now: datetime,
    intent_id: int | None,
    claimed_by: str | None = None,
) -> int:
    claimed_at = now if claimed_by else None
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key, scheduled_for, due_at,
            claimed_by, claimed_at,
            created_at, updated_at, topology, current_stage, workflow_phase, intent_id
        )
        VALUES ($1, 'irrigation_start', 'pending', $2, $3, $3, $4, $5, $3, $3,
                'two_tank', 'await_ready', 'ready', $6)
        RETURNING id
        """,
        zone_id,
        f"{prefix}-irr-pend",
        now,
        claimed_by,
        claimed_at,
        intent_id,
    )
    return int(rows[0]["id"])


class _UnusedHistoryLoggerClient:
    async def publish(self, **kwargs):
        raise AssertionError("history-logger publish must not be used during startup recovery")


def _build_use_case(
    *,
    alert_repository: _AlertRepositoryRecorder | None = None,
    workflow_repository: PgZoneWorkflowRepository | None = None,
    use_startup_recovery_lock: bool = False,
    worker_owner: str | None = None,
    foreign_lease_skip_escalate_sec: int = 300,
) -> tuple[
    StartupRecoveryUseCase,
    PgAutomationTaskRepository,
    PgAeCommandRepository,
    PgZoneLeaseRepository,
    _AlertRepositoryRecorder | None,
]:
    task_repo = PgAutomationTaskRepository()
    command_repo = PgAeCommandRepository()
    lease_repo = PgZoneLeaseRepository()
    workflow_repo = workflow_repository or PgZoneWorkflowRepository()
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
        alert_repository=alert_repository,
        use_startup_recovery_lock=use_startup_recovery_lock,
        worker_owner=worker_owner,
        foreign_lease_skip_escalate_sec=foreign_lease_skip_escalate_sec,
    )
    return recovery_use_case, task_repo, command_repo, lease_repo, alert_repository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task_status", "create_local_command", "expect_fail"),
    [
        ("claimed", False, True),
        ("running", False, True),
        ("running", True, False),
    ],
)
async def test_startup_recovery_fails_task_without_confirmed_external_command(
    task_status: str,
    create_local_command: bool,
    expect_fail: bool,
) -> None:
    prefix = f"ae3-recovery-unconfirmed-{task_status}-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo, _alerts = _build_use_case()
    # Pre-sweep: other integration tests in the same pytest session may leave
    # orphan active-status tasks (seeded from migrations, tests that crashed
    # before cleanup, etc.). Run recovery once before the test-specific setup
    # so the post-setup assertion sees only this test's task in the scan.
    await recovery_use_case.run(now=now)
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
        assert await _count_ae_commands(task_id=task_id) == (1 if create_local_command else 0)
        if expect_fail:
            assert result.failed_tasks == 1
            assert updated_task is not None
            assert updated_task.status == "failed"
            assert updated_task.error_code == "startup_recovery_unconfirmed_command"
        else:
            assert result.failed_tasks == 0
            assert result.waiting_command_tasks == 1
            assert updated_task is not None
            assert updated_task.status == "waiting_command"
        if create_local_command:
            ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
            assert ae_command is not None
            assert ae_command["external_id"] is None
            assert ae_command["terminal_status"] is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_releases_lease_and_records_outcome_after_fail() -> None:
    prefix = f"ae3-recovery-lease-release-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, _command_repo, lease_repo, _alerts = _build_use_case()
    await recovery_use_case.run(now=now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, task_status="claimed", now=now)
        await _insert_lease(
            zone_id=zone_id,
            owner="worker-a",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=1))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        lease = await lease_repo.get(zone_id=zone_id)
        assert lease is None
        events = await fetch(
            """
            SELECT type, payload_json
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'AE_STARTUP_RECOVERY_OUTCOME'
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        assert events
        payload = events[0]["payload_json"]
        assert payload["outcome"] == "failed"
        assert payload["task_id"] == task_id
        assert payload["recovery_source"] == "startup_recovery"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_releases_only_expired_leases() -> None:
    prefix = f"ae3-recovery-leases-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, _task_repo, _command_repo, lease_repo, _alerts = _build_use_case()
    # Pre-sweep orphans from prior tests in the session.
    await recovery_use_case.run(now=now)
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
async def test_startup_recovery_native_two_tank_done_requeues_same_stage_without_republish() -> None:
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
        use_startup_recovery_lock=False,
    )
    # Pre-sweep orphans from prior tests in the session.
    await recovery_use_case.run(now=now)
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
        assert updated_task.current_stage == "clean_fill_start"
        expected_due_at = (now + timedelta(seconds=5)).replace(microsecond=0, tzinfo=None)
        assert updated_task.due_at == expected_due_at
        assert workflow_row is not None
        assert workflow_row.workflow_phase == "tank_filling"
        assert ae_command is not None
        assert ae_command["terminal_status"] == "DONE"
        assert await _count_ae_commands(task_id=task_id) == 1
        events = await fetch(
            """
            SELECT type, payload_json
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'AE_STARTUP_RECOVERY_OUTCOME'
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        assert events
        payload = events[0]["payload_json"]
        assert payload["outcome"] == "recovered_waiting_command"
        assert payload["stage"] == "clean_fill_start"
        assert payload["task_id"] == task_id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_fails_pending_irrigation_when_workflow_idle_terminal_stop() -> None:
    prefix = f"ae3-reconcile-pending-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alerts = _AlertRepositoryRecorder()
    recovery_use_case, task_repo, _command_repo, lease_repo, _ = _build_use_case(
        alert_repository=alerts,
    )
    await recovery_use_case.run(now=now)

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        await _insert_lease(
            zone_id=zone_id,
            owner="worker-a",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )
        await _insert_zone_workflow_state(
            zone_id,
            workflow_phase="idle",
            payload={"ae3_cycle_start_stage": "clean_fill_source_empty_stop"},
            scheduler_task_id="1",
            now=now,
        )
        intent_id = await _insert_intent(zone_id=zone_id, prefix=prefix, status="running", now=now)
        task_id = await _insert_pending_irrigation_task(
            zone_id,
            prefix=prefix,
            now=now,
            intent_id=intent_id,
            claimed_by="worker-a",
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=2))

        updated = await task_repo.get_by_id(task_id=task_id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "startup_recovery_pending_vs_terminal_workflow"
        assert result.failed_tasks >= 1
        assert len(alerts.calls) == 1
        assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
        assert alerts.calls[0]["details"]["recovery_source"] == "startup_recovery"
        lease = await lease_repo.get(zone_id=zone_id)
        assert lease is None
        events = await fetch(
            """
            SELECT type, payload_json
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'AE_STARTUP_RECOVERY_OUTCOME'
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        assert events
        assert events[0]["payload_json"]["outcome"] == "failed"
        assert events[0]["payload_json"]["error_code"] == "startup_recovery_pending_vs_terminal_workflow"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_foreign_lease_owner_not_released_on_fail() -> None:
    prefix = f"ae3-recovery-foreign-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, _command_repo, lease_repo, _ = _build_use_case(
        worker_owner="worker-b",
    )
    await recovery_use_case.run(now=now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, task_status="claimed", now=now)
        await _insert_lease(
            zone_id=zone_id,
            owner="other-worker",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=1))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert updated_task is not None
        assert updated_task.status == "claimed"
        lease = await lease_repo.get(zone_id=zone_id)
        assert lease is not None
        assert lease.owner == "other-worker"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_running_prepare_recirc_done_resumes_same_stage() -> None:
    """Регрессия: DONE одной команды не завершает весь prepare_recirculation_start batch."""
    prefix = f"ae3-recovery-running-recirc-{uuid4().hex}"
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
        use_startup_recovery_lock=False,
    )
    await recovery_use_case.run(now=now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        intent_id = await _insert_intent(zone_id=zone_id, prefix=prefix, status="running", now=now)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            intent_id=intent_id,
            topology="two_tank",
            current_stage="prepare_recirculation_start",
            workflow_phase="tank_recirc",
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-recovery-running-recirc-1",
            status="DONE",
            ack_at=now + timedelta(seconds=4),
            now=now + timedelta(seconds=4),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-recovery-running-recirc-1",
            external_id=str(legacy_id),
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=5))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert result.recovered_waiting_command_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "pending"
        assert updated_task.current_stage == "prepare_recirculation_start"
        assert updated_task.error_code is None
        assert workflow_row is not None
        assert workflow_row.workflow_phase == "tank_recirc"
        assert workflow_row.payload.get("ae3_cycle_start_stage") == "prepare_recirculation_start"
        assert await _count_ae_commands(task_id=task_id) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_running_without_ae_command_fails() -> None:
    prefix = f"ae3-recovery-running-no-cmd-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, _command_repo, _lease_repo, _ = _build_use_case()
    await recovery_use_case.run(now=now)
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
            current_stage="prepare_recirculation_start",
            workflow_phase="tank_recirc",
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=1))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "startup_recovery_unconfirmed_command"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_running_with_ack_stays_waiting_command() -> None:
    prefix = f"ae3-recovery-running-ack-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, task_repo, command_repo, _lease_repo, _ = _build_use_case()
    await recovery_use_case.run(now=now)
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
            cmd_id="ae3-recovery-running-ack-1",
            status="ACK",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-recovery-running-ack-1",
            external_id=str(legacy_id),
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=2))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 0
        assert result.waiting_command_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "waiting_command"
        assert ae_command is not None
        assert ae_command["terminal_status"] is None
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_startup_recovery_gateway_command_error_integration() -> None:
    prefix = f"ae3-recovery-gateway-error-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alerts = _AlertRepositoryRecorder()
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
        alert_repository=alerts,
        use_startup_recovery_lock=False,
    )
    await recovery_use_case.run(now=now)
    baseline_scanned = await _count_active_recovery_tasks()

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
        await _insert_lease(
            zone_id=zone_id,
            owner="worker-a",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-recovery-gateway-error-1",
            status="ERROR",
            failed_at=now + timedelta(seconds=2),
            error_message="pump fault",
            now=now + timedelta(seconds=2),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-recovery-gateway-error-1",
            external_id=str(legacy_id),
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=3))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "command_error"
        assert len(alerts.calls) == 1
        assert alerts.calls[0]["details"]["error_code"] == "command_error"
        assert workflow_row is not None
        assert workflow_row.workflow_phase == "idle"
        assert workflow_row.payload.get("ae3_failure_rollback") is True
        lease = await lease_repo.get(zone_id=zone_id)
        assert lease is None
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert ae_command is not None
        assert ae_command["terminal_status"] == "ERROR"
    finally:
        await _cleanup(prefix)


def _build_waiting_command_reconcile_use_case(
    *,
    alert_repository: _AlertRepositoryRecorder | None = None,
    use_startup_recovery_lock: bool = False,
    foreign_lease_skip_escalate_sec: int = 300,
) -> tuple[
    WaitingCommandReconcileUseCase,
    StartupRecoveryUseCase,
    PgAutomationTaskRepository,
    PgAeCommandRepository,
    PgZoneWorkflowRepository,
]:
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
        alert_repository=alert_repository,
        use_startup_recovery_lock=False,
    )
    reconcile_use_case = WaitingCommandReconcileUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        startup_recovery_use_case=recovery_use_case,
        alert_repository=alert_repository,
        foreign_lease_skip_escalate_sec=foreign_lease_skip_escalate_sec,
        batch_limit=16,
    )
    return reconcile_use_case, recovery_use_case, task_repo, command_repo, workflow_repo


@pytest.mark.asyncio
async def test_waiting_command_reconcile_delayed_done_resumes_command_stage() -> None:
    """W5: delayed DONE возвращает command-stage для проверки полного batch."""
    prefix = f"ae3-wc-reconcile-delayed-{uuid4().hex}"
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
            cmd_id="ae3-wc-reconcile-delayed-1",
            status="ACK",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-wc-reconcile-delayed-1",
            external_id=str(legacy_id),
        )

        first = await reconcile_use_case.run(now=now + timedelta(seconds=2), worker_owner="worker-a")
        assert first.progressed_tasks == 0
        assert first.unchanged_tasks == 1
        task_after_ack = await task_repo.get_by_id(task_id=task_id)
        assert task_after_ack is not None
        assert task_after_ack.status == "waiting_command"

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
        updated_task = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)
        events = await fetch(
            """
            SELECT payload_json
            FROM zone_events
            WHERE zone_id = $1
              AND type = 'AE_STARTUP_RECOVERY_OUTCOME'
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )

        assert second.progressed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "pending"
        assert updated_task.current_stage == "clean_fill_start"
        assert workflow_row is not None
        assert workflow_row.payload.get("ae3_cycle_start_stage") == "clean_fill_start"
        assert events
        assert events[0]["payload_json"]["recovery_source"] == "waiting_command_reconcile"
        assert events[0]["payload_json"]["outcome"] == "recovered_waiting_command"
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert ae_command is not None
        assert ae_command["terminal_status"] == "DONE"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_waiting_command_reconcile_poll_stage_done_does_not_complete_task() -> None:
    """W5b: DONE на poll-stage solution_fill_check не должен terminal-complete cycle_start."""
    prefix = f"ae3-wc-reconcile-poll-stage-{uuid4().hex}"
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
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-wc-reconcile-poll-1",
            status="DONE",
            ack_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-wc-reconcile-poll-1",
            external_id=str(legacy_id),
        )

        result = await reconcile_use_case.run(now=now + timedelta(seconds=2), worker_owner="worker-a")
        updated_task = await task_repo.get_by_id(task_id=task_id)
        workflow_row = await workflow_repo.get(zone_id=zone_id)

        assert result.progressed_tasks == 1
        assert result.failed_tasks == 0
        assert updated_task is not None
        assert updated_task.status == "pending"
        assert updated_task.current_stage == "solution_fill_check"
        assert updated_task.completed_at is None
        assert workflow_row is not None
        assert workflow_row.payload.get("ae3_cycle_start_stage") == "solution_fill_check"
        assert workflow_row.workflow_phase == "tank_filling"
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert ae_command is not None
        assert ae_command["terminal_status"] == "DONE"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_waiting_command_reconcile_progresses_done_despite_foreign_active_lease() -> None:
    """Terminal DONE must reconcile before foreign-lease gate (H3)."""
    prefix = f"ae3-wc-reconcile-foreign-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reconcile_use_case, _recovery, task_repo, _command_repo, _workflow_repo = (
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
            cmd_id="ae3-wc-reconcile-foreign-1",
            status="DONE",
            ack_at=now + timedelta(seconds=2),
            now=now + timedelta(seconds=2),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-wc-reconcile-foreign-1",
            external_id=str(legacy_id),
        )
        await _insert_lease(
            zone_id=zone_id,
            owner="other-worker",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )

        result = await reconcile_use_case.run(now=now + timedelta(seconds=3), worker_owner="worker-a")

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.skipped_lease_tasks == 0
        assert result.progressed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "pending"
        assert updated_task.current_stage == "clean_fill_start"
    finally:
        await _cleanup(prefix)


_FOREIGN_LEASE_ESCALATE_SEC = 60
_FOREIGN_LEASE_ESCALATE_ANCHOR_SEC = 150


@pytest.mark.asyncio
async def test_startup_recovery_escalates_foreign_lease_when_task_age_exceeds_threshold() -> None:
    prefix = f"ae3-recovery-escalate-foreign-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_FOREIGN_LEASE_ESCALATE_ANCHOR_SEC)
    alerts = _AlertRepositoryRecorder()
    recovery_use_case, task_repo, _command_repo, lease_repo, _ = _build_use_case(
        worker_owner="worker-b",
        alert_repository=alerts,
        foreign_lease_skip_escalate_sec=_FOREIGN_LEASE_ESCALATE_SEC,
    )
    await recovery_use_case.run(now=now)
    baseline_scanned = await _count_active_recovery_tasks()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(zone_id, prefix=prefix, task_status="claimed", now=stale_at)
        from common.db import execute

        await execute(
            """
            UPDATE ae_tasks
            SET claimed_at = $2, updated_at = $2, claimed_by = 'worker-a'
            WHERE id = $1
            """,
            task_id,
            stale_at,
        )
        await _insert_lease(
            zone_id=zone_id,
            owner="other-worker",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )

        result = await recovery_use_case.run(now=now + timedelta(seconds=1))

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == baseline_scanned + 1
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "ae3_foreign_lease_stale"
        lease = await lease_repo.get(zone_id=zone_id)
        assert lease is not None
        assert lease.owner == "other-worker"
        assert len(alerts.calls) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_waiting_command_reconcile_escalates_foreign_lease_when_stale() -> None:
    prefix = f"ae3-wc-reconcile-escalate-foreign-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_FOREIGN_LEASE_ESCALATE_ANCHOR_SEC)
    alerts = _AlertRepositoryRecorder()
    reconcile_use_case, _recovery, task_repo, _command_repo, _workflow_repo = (
        _build_waiting_command_reconcile_use_case(
            alert_repository=alerts,
            foreign_lease_skip_escalate_sec=_FOREIGN_LEASE_ESCALATE_SEC,
        )
    )

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=stale_at,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        from common.db import execute

        await execute(
            """
            UPDATE ae_tasks
            SET claimed_at = $2, updated_at = $2,
                stage_deadline_at = $3
            WHERE id = $1
            """,
            task_id,
            stale_at,
            now + timedelta(hours=2),
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-wc-reconcile-escalate-foreign-1",
            status="SENT",
            ack_at=None,
            now=now,
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-wc-reconcile-escalate-foreign-1",
            external_id=str(legacy_id),
        )
        await _insert_lease(
            zone_id=zone_id,
            owner="other-worker",
            leased_until=now + timedelta(minutes=10),
            updated_at=now,
        )

        result = await reconcile_use_case.run(now=now + timedelta(seconds=3), worker_owner="worker-a")

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.skipped_lease_tasks == 0
        assert result.failed_tasks == 1
        assert updated_task is not None
        assert updated_task.status == "failed"
        # Reconcile-first: in-flight SENT + stale updated_at → poll deadline may fire before lease escalate.
        assert updated_task.error_code in {
            "ae3_foreign_lease_stale",
            "ae3_command_poll_deadline_exceeded",
        }
        if updated_task.error_code == "ae3_foreign_lease_stale":
            assert len(alerts.calls) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_waiting_command_reconcile_skips_inflight_task() -> None:
    """In-flight task на worker не должен reconcile'иться фоновым циклом."""
    prefix = f"ae3-wc-reconcile-inflight-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reconcile_use_case, _recovery, task_repo, _command_repo, _workflow_repo = (
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
            cmd_id="ae3-wc-reconcile-inflight-1",
            status="DONE",
            ack_at=now + timedelta(seconds=2),
            now=now + timedelta(seconds=2),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=now,
            cmd_id="ae3-wc-reconcile-inflight-1",
            external_id=str(legacy_id),
        )

        result = await reconcile_use_case.run(
            now=now + timedelta(seconds=3),
            worker_owner="worker-a",
            inflight_task_ids=frozenset({task_id}),
        )

        updated_task = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == 1
        assert result.progressed_tasks == 0
        assert result.failed_tasks == 0
        assert result.unchanged_tasks == 0
        assert result.skipped_lease_tasks == 0
        assert updated_task is not None
        assert updated_task.status == "waiting_command"
        assert updated_task.current_stage == "clean_fill_start"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_waiting_command_reconcile_poll_deadline_fails_stale_task() -> None:
    """W5: waiting_command с истёкшим poll deadline → fail-closed без republish."""
    prefix = f"ae3-wc-reconcile-deadline-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=150)
    reconcile_use_case, _recovery, task_repo, command_repo, _workflow_repo = (
        _build_waiting_command_reconcile_use_case()
    )

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=stale_at,
            topology="two_tank",
            current_stage="clean_fill_start",
            workflow_phase="tank_filling",
        )
        await execute(
            """
            UPDATE ae_tasks
            SET updated_at = $2
            WHERE id = $1
            """,
            task_id,
            stale_at,
        )
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id="ae3-wc-reconcile-deadline-1",
            status="ACK",
            ack_at=stale_at + timedelta(seconds=1),
            now=stale_at + timedelta(seconds=1),
        )
        await _insert_ae_command(
            task_id=task_id,
            now=stale_at,
            cmd_id="ae3-wc-reconcile-deadline-1",
            external_id=str(legacy_id),
        )

        result = await reconcile_use_case.run(now=now, worker_owner="worker-a")
        updated_task = await task_repo.get_by_id(task_id=task_id)

        assert result.failed_tasks == 1
        assert result.kick_needed is True
        assert updated_task is not None
        assert updated_task.status == "failed"
        assert updated_task.error_code == "ae3_command_poll_deadline_exceeded"
        ae_command = await command_repo.get_by_task_step(task_id=task_id, step_no=1)
        assert ae_command is not None
        assert ae_command["terminal_status"] is None or ae_command["terminal_status"] == ""
    finally:
        await _cleanup(prefix)
