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
        *,
        release_result: bool = True,
        release_results: list[bool] | None = None,
    ) -> None:
        self._task = task
        self.release_calls = []
        self.release_result = release_result
        self.release_results = list(release_results) if release_results is not None else None
        self.fail_for_recovery_calls: list[dict] = []

    async def claim_next_pending(self, *, owner: str, now: datetime) -> AutomationTask | None:
        return self._task

    async def release_claim(self, *, task_id: int, owner: str, now: datetime) -> bool:
        self.release_calls.append({"task_id": task_id, "owner": owner, "now": now})
        if self.release_results is not None:
            if not self.release_results:
                return False
            return bool(self.release_results.pop(0))
        return self.release_result

    async def fail_for_recovery(
        self,
        *,
        task_id: int,
        error_code: str,
        error_message: str,
        now: datetime,
    ) -> AutomationTask | None:
        self.fail_for_recovery_calls.append(
            {
                "task_id": task_id,
                "error_code": error_code,
                "error_message": error_message,
                "now": now,
            }
        )
        return self._task


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
async def test_claim_next_task_fails_closed_when_claim_rollback_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now), release_result=False)
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )
    alerts: list[dict] = []

    async def fake_sleep(_delay: float) -> None:
        return None

    async def fake_alert(**kwargs) -> None:
        alerts.append(kwargs)

    monkeypatch.setattr("ae3lite.application.use_cases.claim_next_task.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "ae3lite.application.use_cases.claim_next_task.send_infra_alert",
        fake_alert,
    )

    with pytest.raises(TaskClaimRollbackError):
        await use_case.run(owner="worker-a", now=now)

    assert len(task_repo.release_calls) == 3
    assert len(task_repo.fail_for_recovery_calls) == 1
    assert task_repo.fail_for_recovery_calls[0]["task_id"] == 15
    assert task_repo.fail_for_recovery_calls[0]["error_code"] == "ae3_claim_rollback_failed"
    assert len(alerts) == 1
    assert alerts[0]["code"] == "ae3_claim_rollback_failed"


@pytest.mark.asyncio
async def test_claim_next_task_retries_release_claim_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    task_repo = _FakeTaskRepository(_task(now), release_results=[False, False, True])
    lease_repo = _FakeLeaseRepository(None)
    use_case = ClaimNextTaskUseCase(
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        lease_ttl_sec=60,
    )

    async def fake_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("ae3lite.application.use_cases.claim_next_task.asyncio.sleep", fake_sleep)

    result = await use_case.run(owner="worker-a", now=now)

    assert result is None
    assert len(task_repo.release_calls) == 3
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
