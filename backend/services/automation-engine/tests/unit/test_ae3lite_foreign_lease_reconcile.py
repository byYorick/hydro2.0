"""Unit-тесты foreign lease reconcile policy (H6)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.application.services.foreign_lease_reconcile import (
    ForeignLeaseAction,
    ForeignLeaseContext,
    default_foreign_lease_escalate_sec,
    resolve_foreign_active_lease,
    task_reconcile_age_sec,
)
from ae3lite.domain.entities import AutomationTask

_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _task(
    *,
    claimed_at: datetime | None,
    updated_at: datetime | None,
    status: str = "claimed",
) -> AutomationTask:
    return AutomationTask.from_row(
        {
            "id": 1,
            "zone_id": 10,
            "task_type": "cycle_start",
            "status": status,
            "idempotency_key": "k",
            "scheduled_for": updated_at,
            "due_at": updated_at,
            "claimed_by": "worker-a",
            "claimed_at": claimed_at,
            "error_code": None,
            "error_message": None,
            "created_at": updated_at,
            "updated_at": updated_at,
            "completed_at": None,
            "topology": "two_tank",
            "intent_source": None,
            "intent_trigger": None,
            "intent_id": None,
            "intent_meta": {},
            "current_stage": "startup",
            "workflow_phase": "idle",
            "stage_deadline_at": None,
            "stage_retry_count": 0,
            "stage_entered_at": updated_at,
            "clean_fill_cycle": 1,
            "corr_step": None,
        }
    )


def test_default_foreign_lease_escalate_sec() -> None:
    assert default_foreign_lease_escalate_sec(lease_ttl_sec=300, stale_claimed_ttl_sec=120) == 600
    assert default_foreign_lease_escalate_sec(lease_ttl_sec=60, stale_claimed_ttl_sec=120) == 240


def test_task_reconcile_age_sec_uses_claimed_at_for_claimed_status() -> None:
    now = _NOW
    claimed_at = now - timedelta(seconds=400)
    task = _task(claimed_at=claimed_at, updated_at=now - timedelta(seconds=10))
    assert task_reconcile_age_sec(task=task, now=now) == pytest.approx(400.0)


@pytest.mark.asyncio
async def test_resolve_foreign_active_lease_skips_when_young() -> None:
    now = _NOW
    lease = MagicMock()
    lease.owner = "other-worker"
    lease.leased_until = now + timedelta(minutes=10)
    lease_repo = AsyncMock()
    lease_repo.get = AsyncMock(return_value=lease)
    task = _task(claimed_at=now - timedelta(seconds=30), updated_at=now - timedelta(seconds=30))

    action, ctx = await resolve_foreign_active_lease(
        lease_repository=lease_repo,
        zone_id=10,
        worker_owner="janitor-a",
        task=task,
        now=now,
        escalate_sec=300,
    )

    assert action == ForeignLeaseAction.SKIP
    assert ctx == ForeignLeaseContext(lease_owner="other-worker", leased_until=lease.leased_until)


@pytest.mark.asyncio
async def test_resolve_foreign_active_lease_escalates_when_task_age_exceeds_threshold() -> None:
    now = _NOW
    lease = MagicMock()
    lease.owner = "other-worker"
    lease.leased_until = now + timedelta(minutes=10)
    lease_repo = AsyncMock()
    lease_repo.get = AsyncMock(return_value=lease)
    task = _task(claimed_at=now - timedelta(seconds=400), updated_at=now - timedelta(seconds=400))

    action, ctx = await resolve_foreign_active_lease(
        lease_repository=lease_repo,
        zone_id=10,
        worker_owner="janitor-a",
        task=task,
        now=now,
        escalate_sec=300,
    )

    assert action == ForeignLeaseAction.ESCALATE
    assert ctx is not None
    assert ctx.lease_owner == "other-worker"


@pytest.mark.asyncio
async def test_resolve_foreign_active_lease_allows_when_no_foreign_block() -> None:
    now = _NOW
    lease_repo = AsyncMock()
    lease_repo.get = AsyncMock(return_value=None)
    task = _task(claimed_at=now - timedelta(seconds=400), updated_at=now - timedelta(seconds=400))

    action, ctx = await resolve_foreign_active_lease(
        lease_repository=lease_repo,
        zone_id=10,
        worker_owner="janitor-a",
        task=task,
        now=now,
        escalate_sec=300,
    )

    assert action == ForeignLeaseAction.ALLOW
    assert ctx is None
