from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.use_cases import ClaimNextTaskUseCase
from ae3lite.domain.entities import AutomationTask, ZoneLease
from ae3lite.domain.errors import TaskClaimRollbackError
from ae3lite.infrastructure.metrics import CLAIM_ROLLBACK_FAILED
from ae3lite.runtime.worker import Ae3RuntimeWorker


class _FakeTaskRepository:
    def __init__(
        self,
        task: AutomationTask | None,
        lease: ZoneLease | None,
    ) -> None:
        self._task = task
        self._lease = lease
        self.claim_calls: list[dict] = []
        self.release_calls: list[dict] = []
        self.fail_for_recovery_calls: list[dict] = []

    async def claim_next_with_zone_lease(
        self,
        *,
        owner: str,
        process_run_id: str,
        now: datetime,
        lease_ttl_sec: int,
        overall_deadline_sec: int,
    ):
        self.claim_calls.append(
            {
                "owner": owner,
                "process_run_id": process_run_id,
                "now": now,
                "lease_ttl_sec": lease_ttl_sec,
                "overall_deadline_sec": overall_deadline_sec,
            }
        )
        if self._task is None or self._lease is None:
            return None
        return self._task, self._lease


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
    task_repo = _FakeTaskRepository(_task(now), _lease(now))
    lease_repo = _FakeLeaseRepository(_lease(now))
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=90,
    )

    result = await use_case.run(owner="worker-a", now=now, process_run_id="run-a")

    assert result is not None
    task, lease = result
    assert task.id == 15
    assert lease.zone_id == 7
    assert task_repo.release_calls == []
    assert task_repo.claim_calls[0]["lease_ttl_sec"] == 90
    assert task_repo.claim_calls[0]["process_run_id"] == "run-a"
    assert lease_repo.claim_calls == []


@pytest.mark.asyncio
async def test_claim_next_task_returns_none_when_lease_is_busy() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now), None)
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    result = await use_case.run(owner="worker-a", now=now, process_run_id="run-a")

    assert result is None
    assert task_repo.release_calls == []
    assert task_repo.fail_for_recovery_calls == []
    assert lease_repo.claim_calls == []


@pytest.mark.asyncio
async def test_claim_next_task_rejects_empty_process_run_id() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now), _lease(now))
    lease_repo = _FakeLeaseRepository(_lease(now))
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    with pytest.raises(TaskClaimRollbackError):
        await use_case.run(owner="worker-a", now=now, process_run_id=" ")

    assert task_repo.claim_calls == []
    assert task_repo.release_calls == []
    assert task_repo.fail_for_recovery_calls == []


@pytest.mark.asyncio
async def test_claim_next_task_does_not_compensate_after_atomic_miss() -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(None, None)
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    result = await use_case.run(owner="worker-a", now=now, process_run_id="run-a")

    assert result is None
    assert len(task_repo.claim_calls) == 1
    assert task_repo.release_calls == []
    assert task_repo.fail_for_recovery_calls == []


@pytest.mark.asyncio
async def test_worker_claim_safe_escalates_rollback_instead_of_silent_empty() -> None:
    claim_use_case = SimpleNamespace(
        run=AsyncMock(side_effect=TaskClaimRollbackError("rollback failed after escalation")),
    )
    error_logs: list[str] = []
    logger = type(
        "Logger",
        (),
        {
            "error": staticmethod(lambda msg, *args: error_logs.append(msg % args if args else msg)),
            "warning": staticmethod(lambda *args, **kwargs: None),
            "debug": staticmethod(lambda *args, **kwargs: None),
        },
    )()
    worker = Ae3RuntimeWorker(
        owner="worker-a",
        claim_next_task_use_case=claim_use_case,
        idle_poll_interval_sec=0.1,
        execute_task_use_case=SimpleNamespace(run=AsyncMock()),
        startup_recovery_use_case=SimpleNamespace(run=AsyncMock()),
        zone_lease_repository=SimpleNamespace(release=AsyncMock(return_value=True)),
        zone_intent_repository=SimpleNamespace(
            mark_running=AsyncMock(),
            mark_terminal=AsyncMock(),
        ),
        spawn_background_task_fn=lambda coro, **_: asyncio.create_task(coro),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=logger,
    )

    before = CLAIM_ROLLBACK_FAILED._value.get()
    result = await worker._claim_next_task_safe()

    assert result is None
    assert CLAIM_ROLLBACK_FAILED._value.get() == before + 1
    assert error_logs
    assert "escalated via fail_for_recovery" in error_logs[0]
