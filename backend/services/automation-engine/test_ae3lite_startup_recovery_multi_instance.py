"""Фаза 6: multi-instance startup recovery (advisory lock + dedupe alerts)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import pytest

from ae3lite.application.services.task_failed_alert import recovery_task_failed_dedupe_key
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.domain.entities import ZoneLease
from ae3lite.infrastructure.advisory_locks import AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY
from common.env import get_settings

from test_ae3lite_recovery_topology import (
    NOW,
    _MockCommandGateway,
    _MockTaskRepo,
    _make_task,
)
from test_ae3lite_startup_recovery_integration import _build_use_case

pytestmark = pytest.mark.integration


def test_recovery_task_failed_dedupe_key_format() -> None:
    assert (
        recovery_task_failed_dedupe_key(
            alert_code="biz_ae3_task_failed",
            zone_id=1,
            task_id=6,
            recovery_source="startup_recovery",
        )
        == "biz_ae3_task_failed:1:6:startup_recovery"
    )
    assert (
        recovery_task_failed_dedupe_key(
            alert_code="biz_ae3_task_failed",
            zone_id=2,
            task_id=9,
            recovery_source="waiting_command_reconcile",
        )
        == "biz_ae3_task_failed:2:9:waiting_command_reconcile"
    )
    assert recovery_task_failed_dedupe_key(
        alert_code="biz_ae3_task_failed",
        zone_id=1,
        task_id=1,
        recovery_source="execute_task",
    ) is None


@pytest.mark.asyncio
async def test_startup_recovery_skips_when_advisory_lock_held() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recovery_use_case, *_ = _build_use_case(use_startup_recovery_lock=True)

    # ВАЖНО: внешний lock держим на выделенном прямом соединении, а НЕ через
    # общий pool. В pytest-режиме pool ограничен max_size=1
    # (common/db.py: PYTEST_CURRENT_TEST), и если занять его единственное
    # соединение через try_session_advisory_lock, recovery_use_case.run()
    # навсегда зависнет на pool.acquire() — deadlock, который вешал весь suite.
    s = get_settings()
    conn = await asyncpg.connect(
        host=s.pg_host,
        port=s.pg_port,
        database=s.pg_db,
        user=s.pg_user,
        password=s.pg_pass,
        timeout=10,
    )
    try:
        acquired = bool(
            await conn.fetchval(
                "SELECT pg_try_advisory_lock($1::bigint)",
                int(AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY),
            )
        )
        if not acquired:
            pytest.skip("startup recovery advisory lock удерживается другим процессом")
        result = await recovery_use_case.run(now=now)
        assert result.skipped_due_to_lock is True
        assert result.scanned_tasks == 0
        assert result.failed_tasks == 0
        assert result.released_expired_leases >= 0
    finally:
        try:
            await conn.execute(
                "SELECT pg_advisory_unlock($1::bigint)",
                int(AE3_STARTUP_RECOVERY_ADVISORY_LOCK_KEY),
            )
        finally:
            await conn.close()


class _LeaseRepoWithForeignLease:
    async def release_expired(self, *, now: datetime) -> int:
        return 0

    async def get(self, *, zone_id: int) -> ZoneLease:
        return ZoneLease(
            zone_id=zone_id,
            owner="worker-a",
            leased_until=NOW + timedelta(minutes=10),
            updated_at=NOW,
        )


@pytest.mark.asyncio
async def test_startup_recovery_worker_b_skips_foreign_lease_task_from_worker_a() -> None:
    """Recovery worker-b не трогает in-flight задачу worker-a с живым lease."""
    task = _make_task(
        task_id=42,
        zone_id=7,
        status="running",
        stage="clean_fill_start",
        claimed_by="worker-a",
    )
    repo = _MockTaskRepo(tasks=[task])
    recovery_b = StartupRecoveryUseCase(
        task_repository=repo,
        lease_repository=_LeaseRepoWithForeignLease(),
        command_gateway=_MockCommandGateway(recover_state="waiting_command"),
        topology_registry=TopologyRegistry(),
        use_startup_recovery_lock=False,
        worker_owner="worker-b",
    )

    result = await recovery_b.run(now=NOW)

    assert result.scanned_tasks == 1
    assert result.failed_tasks == 0
    assert result.waiting_command_tasks == 0
    assert repo.failed == []
    assert repo.waiting_command_persisted == []
    assert task.status == "running"
