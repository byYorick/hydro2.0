"""Lease, чужая задача и зависший in-flight не держат зону."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from ae4.application.execute_claimed import execute_claimed_task
from ae4.application.frame_recovery import fail_stale_inflight_tasks
from ae4.domain.entities import Ae4Task


class _Lease:
    def __init__(self, *, ok: bool) -> None:
        self.ok = ok
        self.released = False

    async def claim(self, **kwargs: Any) -> object | None:
        return object() if self.ok else None

    async def release(self, **kwargs: Any) -> bool:
        self.released = True
        return True


class _Tasks:
    def __init__(self, running: Any) -> None:
        self.running = running
        self.failed: list[dict[str, Any]] = []

    async def mark_running(self, **kwargs: Any) -> Any:
        return self.running

    async def mark_failed(self, **kwargs: Any) -> None:
        self.failed.append(kwargs)

    async def mark_completed(self, **kwargs: Any) -> None:
        return None

    async def mark_waiting_command(self, **kwargs: Any) -> None:
        return None


class _Inflight:
    def __init__(self, tasks: list[Ae4Task]) -> None:
        self.tasks = tasks
        self.failed: list[dict[str, Any]] = []

    async def list_inflight_for_ae4(self, *, worker_owner: str) -> list[Ae4Task]:
        return self.tasks

    async def mark_failed(self, **kwargs: Any) -> None:
        self.failed.append(kwargs)


async def _noop_report(**kwargs: Any) -> None:
    return None


def _ae_task(*, updated_at: datetime) -> Ae4Task:
    return Ae4Task(
        id=11,
        zone_id=4,
        task_type="irrigation_start",
        status="waiting_command",
        idempotency_key="stuck",
        due_at=updated_at,
        claimed_by="ae4-runtime-worker",
        claimed_at=updated_at,
        error_code=None,
        error_message=None,
        intent_meta={},
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        created_at=updated_at,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_lease_lost_fails_task_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ae4.application.execute_claimed.report_failure", _noop_report)
    tasks = _Tasks(running=None)
    lease = _Lease(ok=False)
    await execute_claimed_task(
        claimed_task_id=5,
        zone_id=1,
        worker_owner="ae4-runtime-worker",
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        task_repository=tasks,  # type: ignore[arg-type]
        command_repository=object(),  # type: ignore[arg-type]
        lease_repository=lease,  # type: ignore[arg-type]
        gateway=object(),  # type: ignore[arg-type]
    )
    assert tasks.failed[0]["error_code"] == "ae4_lease_lost"
    assert lease.released is False


@pytest.mark.asyncio
async def test_foreign_kind_is_rejected_and_lease_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ae4.application.execute_claimed.report_failure", _noop_report)
    running = SimpleNamespace(id=6, zone_id=2, intent_meta={}, task_type="dispatcher")
    tasks = _Tasks(running=running)
    lease = _Lease(ok=True)
    await execute_claimed_task(
        claimed_task_id=6,
        zone_id=2,
        worker_owner="ae4-runtime-worker",
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        task_repository=tasks,  # type: ignore[arg-type]
        command_repository=object(),  # type: ignore[arg-type]
        lease_repository=lease,  # type: ignore[arg-type]
        gateway=object(),  # type: ignore[arg-type]
    )
    assert tasks.failed[0]["error_code"] == "ae4_foreign_task_rejected"
    assert lease.released is True


@pytest.mark.asyncio
async def test_stale_waiting_command_is_failed_fresh_task_stays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ae4.application.frame_recovery.report_failure", _noop_report)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    repo = _Inflight(
        [
            _ae_task(updated_at=now - timedelta(seconds=30)),
            _ae_task(updated_at=now - timedelta(seconds=1000)),
        ]
    )
    repo.tasks[1] = Ae4Task(
        id=22,
        zone_id=9,
        task_type=repo.tasks[1].task_type,
        status=repo.tasks[1].status,
        idempotency_key="old",
        due_at=repo.tasks[1].due_at,
        claimed_by=repo.tasks[1].claimed_by,
        claimed_at=repo.tasks[1].claimed_at,
        error_code=None,
        error_message=None,
        intent_meta={},
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        created_at=repo.tasks[1].created_at,
        updated_at=repo.tasks[1].updated_at,
    )
    failed = await fail_stale_inflight_tasks(
        task_repository=repo,  # type: ignore[arg-type]
        worker_owner="ae4-runtime-worker",
        now=now,
        max_age_sec=900,
    )
    assert failed == 1
    assert repo.failed[0]["task_id"] == 22
    assert repo.failed[0]["error_code"] == "ae4_task_stale"
