"""Интеграционные тесты StaleTaskReconcileUseCase (TaskJanitor, PR3)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases import StaleTaskReconcileUseCase, StartupRecoveryUseCase
from ae3lite.infrastructure.gateways import SequentialCommandGateway
from ae3lite.infrastructure.metrics import STALE_TASKS_RECLAIMED
from ae3lite.infrastructure.repositories import (
    PgAeCommandRepository,
    PgAutomationTaskRepository,
    PgZoneLeaseRepository,
    PgZoneWorkflowRepository,
)

from test_ae3lite_startup_recovery_integration import (
    _AlertRepositoryRecorder,
    _UnusedHistoryLoggerClient,
    _cleanup,
    _insert_ae_command,
    _insert_greenhouse,
    _insert_legacy_command,
    _insert_lease,
    _insert_task,
    _insert_zone,
)

pytestmark = pytest.mark.integration

_STALE_CLAIMED_TTL_SEC = 120
_STALE_RUNNING_TTL_SEC = 960
_STALE_WAITING_COMMAND_TTL_SEC = 210
_STALE_UNCONFIRMED_TTL_SEC = 120


def _build_startup_recovery_use_case(
    *,
    task_repo: PgAutomationTaskRepository,
    lease_repo: PgZoneLeaseRepository,
    alert_repository: _AlertRepositoryRecorder | None = None,
) -> StartupRecoveryUseCase:
    command_repo = PgAeCommandRepository()
    workflow_repo = PgZoneWorkflowRepository()
    gateway = SequentialCommandGateway(
        task_repository=task_repo,
        command_repository=command_repo,
        history_logger_client=_UnusedHistoryLoggerClient(),
        poll_interval_sec=0.05,
    )
    return StartupRecoveryUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        command_gateway=gateway,
        workflow_repository=workflow_repo,
        topology_registry=TopologyRegistry(),
        alert_repository=alert_repository,
        use_startup_recovery_lock=False,
    )


def _build_stale_reconcile_use_case(
    *,
    alert_repository: _AlertRepositoryRecorder | None = None,
    startup_recovery_use_case: StartupRecoveryUseCase | None = None,
    foreign_lease_skip_escalate_sec: int = 300,
) -> tuple[StaleTaskReconcileUseCase, PgAutomationTaskRepository, PgZoneLeaseRepository]:
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    recovery = startup_recovery_use_case or _build_startup_recovery_use_case(
        task_repo=task_repo,
        lease_repo=lease_repo,
        alert_repository=alert_repository,
    )
    command_gateway = getattr(recovery, "_command_gateway", None)
    use_case = StaleTaskReconcileUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        alert_repository=alert_repository,
        startup_recovery_use_case=recovery,
        command_gateway=command_gateway,
        stale_claimed_ttl_sec=_STALE_CLAIMED_TTL_SEC,
        stale_running_ttl_sec=_STALE_RUNNING_TTL_SEC,
        stale_waiting_command_ttl_sec=_STALE_WAITING_COMMAND_TTL_SEC,
        stale_unconfirmed_command_ttl_sec=_STALE_UNCONFIRMED_TTL_SEC,
        foreign_lease_skip_escalate_sec=foreign_lease_skip_escalate_sec,
        batch_limit=16,
    )
    return use_case, task_repo, lease_repo


async def _backdate_task(
    *,
    task_id: int,
    claimed_at: datetime,
    updated_at: datetime,
) -> None:
    from common.db import execute

    await execute(
        """
        UPDATE ae_tasks
        SET claimed_at = $2,
            updated_at = $3
        WHERE id = $1
        """,
        task_id,
        claimed_at,
        updated_at,
    )


async def _fetch_reclaimed_events(*, zone_id: int) -> list[dict]:
    from common.db import fetch

    rows = await fetch(
        """
        SELECT type, payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = 'AE_TASK_RECLAIMED'
        ORDER BY id ASC
        """,
        zone_id,
    )
    return [dict(row) for row in rows]


@pytest.mark.asyncio
async def test_stale_claimed_without_commands_requeues_and_emits_observability() -> None:
    prefix = f"ae3-stale-req-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_CLAIMED_TTL_SEC + 30)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

    before_requeue = STALE_TASKS_RECLAIMED.labels(from_status="claimed", action="requeue")._value.get()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=stale_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.requeued_tasks == 1
        assert result.failed_tasks == 0
        assert result.kick_needed is True
        assert updated is not None
        assert updated.status == "pending"
        assert updated.claimed_by is None

        events = await _fetch_reclaimed_events(zone_id=zone_id)
        assert len(events) == 1
        payload = events[0]["payload_json"]
        assert payload["task_id"] == task_id
        assert payload["from_status"] == "claimed"
        assert payload["action"] == "requeue"
        assert payload["age_sec"] >= float(_STALE_CLAIMED_TTL_SEC)

        after_requeue = STALE_TASKS_RECLAIMED.labels(from_status="claimed", action="requeue")._value.get()
        assert after_requeue == before_requeue + 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_stale_running_with_commands_fails_with_ae3_stale_task_reclaimed() -> None:
    prefix = f"ae3-stale-fail-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_RUNNING_TTL_SEC + 30)
    alerts = _AlertRepositoryRecorder()
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case(alert_repository=alerts)

    before_fail = STALE_TASKS_RECLAIMED.labels(from_status="running", action="fail")._value.get()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=stale_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)
        legacy_id = await _insert_legacy_command(
            zone_id=zone_id,
            cmd_id=f"{prefix}-cmd",
            status="ACK",
            ack_at=stale_at,
            now=stale_at,
        )
        await _insert_ae_command(
            task_id=task_id,
            now=stale_at,
            cmd_id=f"{prefix}-cmd",
            external_id=str(legacy_id),
        )

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.failed_tasks == 1
        assert result.requeued_tasks == 0
        assert result.kick_needed is True
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "ae3_stale_task_reclaimed"
        assert len(alerts.calls) == 1

        events = await _fetch_reclaimed_events(zone_id=zone_id)
        assert len(events) == 1
        assert events[0]["payload_json"]["action"] == "fail"

        after_fail = STALE_TASKS_RECLAIMED.labels(from_status="running", action="fail")._value.get()
        assert after_fail == before_fail + 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_stale_task_skipped_when_foreign_active_lease() -> None:
    prefix = f"ae3-stale-skip-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_CLAIMED_TTL_SEC + 30)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=stale_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)
        await _insert_lease(
            zone_id=zone_id,
            owner="live-worker-b",
            leased_until=now + timedelta(seconds=300),
            updated_at=now,
        )

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.skipped_lease_tasks == 1
        assert result.requeued_tasks == 0
        assert result.failed_tasks == 0
        assert updated is not None
        assert updated.status == "claimed"
        events = await _fetch_reclaimed_events(zone_id=zone_id)
        assert events == []
    finally:
        await _cleanup(prefix)


_FOREIGN_LEASE_ESCALATE_SEC = 60
_STALE_ESCALATE_ANCHOR_SEC = _STALE_CLAIMED_TTL_SEC + 30


@pytest.mark.asyncio
async def test_stale_task_escalates_foreign_lease_when_task_age_exceeds_threshold() -> None:
    prefix = f"ae3-stale-escalate-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_ESCALATE_ANCHOR_SEC)
    alerts = _AlertRepositoryRecorder()
    use_case, task_repo, lease_repo = _build_stale_reconcile_use_case(
        alert_repository=alerts,
        foreign_lease_skip_escalate_sec=_FOREIGN_LEASE_ESCALATE_SEC,
    )

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=stale_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)
        await _insert_lease(
            zone_id=zone_id,
            owner="live-worker-b",
            leased_until=now + timedelta(seconds=300),
            updated_at=now,
        )

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        lease = await lease_repo.get(zone_id=zone_id)
        assert result.skipped_lease_tasks == 0
        assert result.failed_tasks == 1
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "ae3_foreign_lease_stale"
        assert lease is not None
        assert lease.owner == "live-worker-b"
        assert len(alerts.calls) == 1
        assert alerts.calls[0]["code"] == "biz_ae3_task_failed"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_fresh_claimed_not_reclaimed() -> None:
    prefix = f"ae3-stale-fresh-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh_at = now - timedelta(seconds=30)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=fresh_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=fresh_at, updated_at=fresh_at)

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.scanned_tasks == 0
        assert result.requeued_tasks == 0
        assert result.failed_tasks == 0
        assert updated is not None
        assert updated.status == "claimed"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_concurrent_stale_reconcile_skip_locked_prevents_double_requeue() -> None:
    prefix = f"ae3-stale-concurrent-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_CLAIMED_TTL_SEC + 30)
    use_case_a, task_repo, _lease_repo = _build_stale_reconcile_use_case()
    use_case_b, _, _ = _build_stale_reconcile_use_case()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="claimed",
            now=stale_at,
        )
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)

        result_a, result_b = await asyncio.gather(
            use_case_a.run(now=now, owner="janitor-a"),
            use_case_b.run(now=now, owner="janitor-b"),
        )

        total_requeued = result_a.requeued_tasks + result_b.requeued_tasks
        assert total_requeued == 1

        updated = await task_repo.get_by_id(task_id=task_id)
        assert updated is not None
        assert updated.status == "pending"
        events = await _fetch_reclaimed_events(zone_id=zone_id)
        assert len(events) == 1
    finally:
        await _cleanup(prefix)


async def _insert_unconfirmed_ae_command(
    *,
    task_id: int,
    now: datetime,
    cmd_id: str,
) -> int:
    from common.db import fetch

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
            NULL,
            'published_unconfirmed',
            $3,
            $3
        )
        RETURNING id
        """,
        task_id,
        {"cmd": "set_relay", "params": {"state": True}, "cmd_id": cmd_id},
        now,
    )
    return int(rows[0]["id"])


async def _backdate_ae_command(*, command_id: int, updated_at: datetime) -> None:
    from common.db import execute

    await execute(
        """
        UPDATE ae_commands
        SET updated_at = $2
        WHERE id = $1
        """,
        command_id,
        updated_at,
    )


@pytest.mark.asyncio
async def test_stale_waiting_command_fails_with_ae3_stale_waiting_command() -> None:
    prefix = f"ae3-stale-wc-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_WAITING_COMMAND_TTL_SEC + 30)
    alerts = _AlertRepositoryRecorder()
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = StaleTaskReconcileUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        alert_repository=alerts,
        startup_recovery_use_case=None,
        stale_claimed_ttl_sec=_STALE_CLAIMED_TTL_SEC,
        stale_running_ttl_sec=_STALE_RUNNING_TTL_SEC,
        stale_waiting_command_ttl_sec=_STALE_WAITING_COMMAND_TTL_SEC,
        stale_unconfirmed_command_ttl_sec=_STALE_UNCONFIRMED_TTL_SEC,
        batch_limit=16,
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
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)
        await _insert_ae_command(task_id=task_id, now=stale_at, cmd_id=f"{prefix}-cmd")

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.failed_tasks == 1
        assert result.requeued_tasks == 0
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_code == "ae3_stale_waiting_command"
        assert len(alerts.calls) == 1
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_stale_running_unconfirmed_reconciles_to_waiting_command() -> None:
    prefix = f"ae3-stale-unconf-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_UNCONFIRMED_TTL_SEC + 30)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

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
        command_id = await _insert_unconfirmed_ae_command(
            task_id=task_id,
            now=now,
            cmd_id=f"{prefix}-cmd",
        )
        await _backdate_ae_command(command_id=command_id, updated_at=stale_at)

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.requeued_tasks == 1
        assert result.failed_tasks == 0
        assert updated is not None
        assert updated.status == "waiting_command"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_stale_waiting_command_skips_inflight_task() -> None:
    prefix = f"ae3-stale-wc-inflight-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(seconds=_STALE_WAITING_COMMAND_TTL_SEC + 30)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

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
        await _backdate_task(task_id=task_id, claimed_at=stale_at, updated_at=stale_at)
        await _insert_ae_command(task_id=task_id, now=stale_at, cmd_id=f"{prefix}-cmd")

        result = await use_case.run(now=now, owner="janitor-a", inflight_task_ids=frozenset({task_id}))

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.failed_tasks == 0
        assert result.requeued_tasks == 0
        assert updated is not None
        assert updated.status == "waiting_command"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_stale_waiting_command_long_duration_not_failed_before_poll_deadline() -> None:
    prefix = f"ae3-stale-wc-long-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    waiting_since = now - timedelta(seconds=120)
    use_case, task_repo, _lease_repo = _build_stale_reconcile_use_case()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="waiting_command",
            now=waiting_since,
            topology="two_tank",
            current_stage="corr_dose_ec",
            workflow_phase="tank_filling",
        )
        await _backdate_task(task_id=task_id, claimed_at=waiting_since, updated_at=waiting_since)
        from common.db import execute

        await execute(
            """
            INSERT INTO ae_commands (
                task_id,
                step_no,
                node_uid,
                channel,
                payload,
                publish_status,
                created_at,
                updated_at
            )
            VALUES (
                $1,
                1,
                'nd-ec-1',
                'pump_nutrient_a',
                $2::jsonb,
                'accepted',
                $3,
                $3
            )
            """,
            task_id,
            {"cmd": "dose", "params": {"ml": 5.0, "duration_ms": 600_000}, "cmd_id": f"{prefix}-cmd"},
            waiting_since,
        )

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.failed_tasks == 0
        assert updated is not None
        assert updated.status == "waiting_command"
    finally:
        await _cleanup(prefix)
