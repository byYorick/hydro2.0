from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.application.use_cases import ClaimNextTaskUseCase
from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError


class _FakeTaskRepository:
    def __init__(self, task: AutomationTask | None, *, release_result: bool = True) -> None:
        self._task = task
        self.release_calls = []
        self.release_result = release_result

    async def claim_next_pending(self, *, owner: str, now: datetime) -> AutomationTask | None:
        return self._task

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        self.release_calls.append({"task_id": task_id, "owner": owner, "now": now})
        return self.release_result


class _FakeLeaseRepository:
    def __init__(self, lease: ZoneLease | None) -> None:
        self._lease = lease
        self.claim_calls = []

    async def claim(self, *, zone_id: int, owner: str, now: datetime, lease_ttl_sec: int) -> ZoneLease | None:
        self.claim_calls.append(
            {
                "zone_id": zone_id,
                "owner": owner,
                "now": now,
                "lease_ttl_sec": lease_ttl_sec,
            }
        )
        return self._lease


def _task(now: datetime) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 15, "zone_id": 7, "task_type": "cycle_start", "status": "claimed",
        "idempotency_key": "unit-key", "scheduled_for": now, "due_at": now,
        "claimed_by": "worker-a", "claimed_at": now, "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
        "clean_fill_cycle": 0, "corr_step": None,
    })


def _lease(now: datetime) -> ZoneLease:
    return ZoneLease(
        zone_id=7,
        owner="worker-a",
        leased_until=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_claim_next_task_returns_claimed_task_and_lease() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now))
    lease_repo = _FakeLeaseRepository(_lease(now))
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=90,
    )

    result = await use_case.run(owner="worker-a", now=now)

    assert result is not None
    task, lease = result
    assert task.id == 15
    assert lease.zone_id == 7
    assert task_repo.release_calls == []
    assert lease_repo.claim_calls[0]["lease_ttl_sec"] == 90


@pytest.mark.asyncio
async def test_claim_next_task_rolls_back_claim_when_lease_is_busy() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now))
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    result = await use_case.run(owner="worker-a", now=now)

    assert result is None
    assert task_repo.release_calls == [{"task_id": 15, "owner": "worker-a", "now": now}]


@pytest.mark.asyncio
async def test_claim_next_task_fails_closed_when_claim_rollback_fails() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now), release_result=False)
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    with pytest.raises(TaskClaimRollbackError):
        await use_case.run(owner="worker-a", now=now)
