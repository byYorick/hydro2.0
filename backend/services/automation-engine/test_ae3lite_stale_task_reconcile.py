"""Интеграционные тесты StaleTaskReconcileUseCase (TaskJanitor, PR3)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.use_cases import StaleTaskReconcileUseCase
from ae3lite.infrastructure.metrics import STALE_TASKS_RECLAIMED
from ae3lite.infrastructure.repositories import (
    PgAutomationTaskRepository,
    PgZoneLeaseRepository,
)

from test_ae3lite_startup_recovery_integration import (
    _AlertRepositoryRecorder,
    _cleanup,
    _insert_ae_command,
    _insert_greenhouse,
    _insert_lease,
    _insert_task,
    _insert_zone,
)

pytestmark = pytest.mark.integration

_STALE_CLAIMED_TTL_SEC = 120
_STALE_RUNNING_TTL_SEC = 960


def _build_stale_reconcile_use_case(
    *,
    alert_repository: _AlertRepositoryRecorder | None = None,
) -> tuple[StaleTaskReconcileUseCase, PgAutomationTaskRepository, PgZoneLeaseRepository]:
    task_repo = PgAutomationTaskRepository()
    lease_repo = PgZoneLeaseRepository()
    use_case = StaleTaskReconcileUseCase(
        task_repository=task_repo,
        lease_repository=lease_repo,
        alert_repository=alert_repository,
        stale_claimed_ttl_sec=_STALE_CLAIMED_TTL_SEC,
        stale_running_ttl_sec=_STALE_RUNNING_TTL_SEC,
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
        await _insert_ae_command(task_id=task_id, now=stale_at, cmd_id=f"{prefix}-cmd")

        result = await use_case.run(now=now, owner="janitor-a")

        updated = await task_repo.get_by_id(task_id=task_id)
        assert result.failed_tasks == 1
        assert result.requeued_tasks == 0
        assert result.kick_needed is False
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
