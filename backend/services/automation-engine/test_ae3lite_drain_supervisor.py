"""Unit tests for AE3 drain supervisor, per-task crash isolation and honest health."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.domain.errors import TaskClaimRollbackError
from ae3lite.infrastructure.metrics import (
    CLAIM_ROLLBACK_FAILED,
    DRAIN_CRASHES,
    TASK_EXECUTION_CRASHED,
)
from ae3lite.runtime import Ae3RuntimeWorker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _noop_logger() -> object:
    return type(
        "Logger",
        (),
        {
            "warning": staticmethod(lambda *args, **kwargs: None),
            "debug": staticmethod(lambda *args, **kwargs: None),
            "error": staticmethod(lambda *args, **kwargs: None),
        },
    )()


def _build_worker(
    *,
    claim_run: AsyncMock | None = None,
    execute_run: AsyncMock | None = None,
    next_pending_due_at: AsyncMock | None = None,
    task_repository: object | None = None,
    shutdown_grace_sec: float = 0.2,
) -> Ae3RuntimeWorker:
    claim_run = claim_run or AsyncMock(return_value=None)
    execute_run = execute_run or AsyncMock(return_value=None)
    claim_use_case = SimpleNamespace(run=claim_run)
    if next_pending_due_at is not None:
        claim_use_case.next_pending_due_at = next_pending_due_at

    return Ae3RuntimeWorker(
        owner="drain-supervisor-test",
        claim_next_task_use_case=claim_use_case,
        idle_poll_interval_sec=0.01,
        execute_task_use_case=SimpleNamespace(run=execute_run),
        startup_recovery_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        task_repository=task_repository,
        zone_lease_repository=SimpleNamespace(release=AsyncMock(return_value=True)),
        zone_intent_repository=SimpleNamespace(
            mark_running=AsyncMock(return_value=None),
            mark_terminal=AsyncMock(return_value=None),
        ),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(
            coro,
            name=str(kwargs.get("task_name") or "ae3-drain-supervisor-test"),
        ),
        now_fn=_utcnow,
        logger=_noop_logger(),
        lease_ttl_sec=120,
        max_task_execution_sec=900,
        max_parallel_tasks=1,
        shutdown_grace_sec=shutdown_grace_sec,
    )


@pytest.mark.asyncio
async def test_drain_supervisor_restarts_after_crash_with_backoff_and_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _build_worker()
    crash_attempts = 0
    sleep_calls: list[float] = []

    async def _flaky_drain() -> None:
        nonlocal crash_attempts
        crash_attempts += 1
        if crash_attempts <= 2:
            raise RuntimeError("drain boom")
        worker._last_drain_exit_ok = True
        worker._last_drain_exit_reason = "idle"

    async def _sleep_stub(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(worker, "_drain_pending_tasks", _flaky_drain)
    monkeypatch.setattr(asyncio, "sleep", _sleep_stub)

    before = DRAIN_CRASHES._value.get()
    await worker._drain_supervisor()

    assert crash_attempts == 3
    assert DRAIN_CRASHES._value.get() == before + 2
    assert sleep_calls == [1.0, 2.0]


@pytest.mark.asyncio
async def test_execution_crash_isolates_task_and_continues_drain() -> None:
    executed: list[int] = []
    fail_calls: list[dict[str, object]] = []

    task_one = SimpleNamespace(
        id=1,
        zone_id=10,
        intent_id=100,
        topology="generic_cycle_start",
        status="claimed",
        is_active=True,
        error_code=None,
        error_message=None,
    )
    task_two = SimpleNamespace(
        id=2,
        zone_id=11,
        intent_id=101,
        topology="generic_cycle_start",
        status="claimed",
        is_active=False,
        error_code=None,
        error_message=None,
    )

    async def _execute_side_effect(**kwargs: object) -> SimpleNamespace:
        task = kwargs["task"]
        executed.append(int(task.id))
        if int(task.id) == 1:
            raise RuntimeError("task execution boom")
        return task_two

    claim_run = AsyncMock(
        side_effect=[
            (task_one, SimpleNamespace()),
            (task_two, SimpleNamespace()),
            None,
            None,
        ]
    )
    task_repository = SimpleNamespace(
        fail_for_recovery=AsyncMock(
            side_effect=lambda **kwargs: fail_calls.append(dict(kwargs)) or task_one
        )
    )
    worker = _build_worker(
        claim_run=claim_run,
        execute_run=AsyncMock(side_effect=_execute_side_effect),
        task_repository=task_repository,
    )

    before = TASK_EXECUTION_CRASHED.labels(error="RuntimeError")._value.get()
    await worker._drain_pending_tasks()

    assert executed == [1, 2]
    assert fail_calls
    assert fail_calls[0]["task_id"] == 1
    assert fail_calls[0]["error_code"] == "ae3_task_execution_crashed"
    assert TASK_EXECUTION_CRASHED.labels(error="RuntimeError")._value.get() == before + 1
    assert worker._last_drain_exit_reason == "idle"


@pytest.mark.asyncio
async def test_task_claim_rollback_error_keeps_drain_alive() -> None:
    claim_run = AsyncMock(
        side_effect=[
            TaskClaimRollbackError("rollback failed"),
            None,
        ]
    )
    worker = _build_worker(claim_run=claim_run)

    before = CLAIM_ROLLBACK_FAILED._value.get()
    await worker._drain_pending_tasks()

    assert CLAIM_ROLLBACK_FAILED._value.get() == before + 1
    assert worker._last_drain_exit_reason == "idle"


@pytest.mark.asyncio
async def test_drain_health_dead_with_pending() -> None:
    now = _utcnow()
    worker = _build_worker(
        next_pending_due_at=AsyncMock(return_value=now - timedelta(seconds=1)),
    )
    done_task = asyncio.create_task(asyncio.sleep(0), name="dead-drain")
    await done_task
    worker._drain_task = done_task
    worker._last_drain_exit_ok = True
    worker._last_drain_exit_reason = "idle"

    ok, reason = await worker.drain_health()
    assert ok is False
    assert reason == "drain_dead_with_pending"


@pytest.mark.asyncio
async def test_drain_health_idle_without_pending() -> None:
    worker = _build_worker(next_pending_due_at=AsyncMock(return_value=None))
    done_task = asyncio.create_task(asyncio.sleep(0), name="idle-drain")
    await done_task
    worker._drain_task = done_task
    worker._last_drain_exit_ok = True
    worker._last_drain_exit_reason = "idle"

    ok, reason = await worker.drain_health()
    assert ok is True
    assert reason == "idle"


@pytest.mark.asyncio
async def test_shutdown_with_active_supervisor_completes_gracefully() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_execute(**kwargs: object) -> None:
        started.set()
        await release.wait()

    task = SimpleNamespace(id=42, zone_id=7, intent_id=0, topology="single_tank")
    claim_run = AsyncMock(side_effect=[(task, SimpleNamespace()), None])
    worker = _build_worker(
        claim_run=claim_run,
        execute_run=AsyncMock(side_effect=_slow_execute),
        shutdown_grace_sec=1.0,
    )
    worker.kick()
    await asyncio.wait_for(started.wait(), timeout=1.0)

    shutdown_task = asyncio.create_task(worker.shutdown(grace_sec=0.5))
    await asyncio.sleep(0.05)
    assert not shutdown_task.done()

    release.set()
    await asyncio.wait_for(shutdown_task, timeout=2.0)
    drain = worker._drain_task
    assert drain is not None
    assert drain.done()
    assert worker._last_drain_exit_reason == "shutdown"
