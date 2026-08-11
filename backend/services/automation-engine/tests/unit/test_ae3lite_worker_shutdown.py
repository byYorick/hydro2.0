"""Unit tests for AE3 runtime worker graceful shutdown (phase 4)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.runtime import Ae3RuntimeWorker
from ae3lite.runtime.env import Ae3RuntimeConfig


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _noop_logger() -> object:
    return type(
        "Logger",
        (),
        {
            "warning": staticmethod(lambda *args, **kwargs: None),
            "debug": staticmethod(lambda *args, **kwargs: None),
        },
    )()


def _build_shutdown_worker(
    *,
    claim_run: AsyncMock | None = None,
    execute_run: AsyncMock | None = None,
    task_repository: object | None = None,
    command_repository: object | None = None,
    shutdown_grace_sec: float = 0.2,
) -> Ae3RuntimeWorker:
    claim_run = claim_run or AsyncMock(return_value=None)
    execute_run = execute_run or AsyncMock(return_value=None)

    return Ae3RuntimeWorker(
        owner="shutdown-test-worker",
        claim_next_task_use_case=SimpleNamespace(run=claim_run),
        idle_poll_interval_sec=0.01,
        execute_task_use_case=SimpleNamespace(run=execute_run),
        startup_recovery_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        task_repository=task_repository,
        command_repository=command_repository,
        zone_lease_repository=SimpleNamespace(release=AsyncMock(return_value=True)),
        zone_intent_repository=SimpleNamespace(
            mark_running=AsyncMock(return_value=None),
            mark_terminal=AsyncMock(return_value=None),
        ),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(
            coro,
            name=str(kwargs.get("task_name") or "ae3-shutdown-test"),
        ),
        now_fn=_utcnow,
        logger=_noop_logger(),
        lease_ttl_sec=120,
        max_task_execution_sec=900,
        max_parallel_tasks=1,
        shutdown_grace_sec=shutdown_grace_sec,
    )


@pytest.mark.asyncio
async def test_kick_ignored_during_shutdown() -> None:
    worker = _build_shutdown_worker()
    await worker.shutdown(grace_sec=0.0)
    before = worker._drain_task
    after = worker.kick()
    assert after is before
    assert worker._pending_kicks == 0


@pytest.mark.asyncio
async def test_shutdown_waits_for_inflight_before_exit() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_execute(**kwargs: object) -> None:
        started.set()
        await release.wait()

    task = SimpleNamespace(id=42, zone_id=7, intent_id=0, topology="single_tank")
    claim_run = AsyncMock(
        side_effect=[
            (task, SimpleNamespace()),
            None,
        ]
    )
    worker = _build_shutdown_worker(
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


@pytest.mark.asyncio
async def test_shutdown_releases_unpublished_claim() -> None:
    task = SimpleNamespace(id=99, zone_id=3, intent_id=0, topology="single_tank")
    claimed = SimpleNamespace(id=99, zone_id=3, status="claimed")

    task_repository = SimpleNamespace(
        requeue_unpublished_execution=AsyncMock(return_value=claimed),
        list_unpublished_execution_by_owner=AsyncMock(return_value=[claimed]),
        release_claim=AsyncMock(return_value=True),
        get_by_id=AsyncMock(return_value=claimed),
    )
    command_repository = SimpleNamespace(get_latest_for_task=AsyncMock(return_value=None))
    lease_repository = SimpleNamespace(release=AsyncMock(return_value=True))

    worker = _build_shutdown_worker(
        task_repository=task_repository,
        command_repository=command_repository,
    )
    worker._zone_lease_repository = lease_repository

    released = await worker._maybe_release_unpublished_claim(task)
    assert released is True
    task_repository.requeue_unpublished_execution.assert_awaited_once()
    lease_repository.release.assert_awaited_once_with(zone_id=3, owner="shutdown-test-worker")

    task_repository.requeue_unpublished_execution.reset_mock()
    lease_repository.release.reset_mock()
    count = await worker._release_unpublished_claims_for_owner()
    assert count == 1
    task_repository.requeue_unpublished_execution.assert_awaited_once()
    lease_repository.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_requeues_running_without_ae_command() -> None:
    task = SimpleNamespace(id=77, zone_id=5, intent_id=0, topology="single_tank")
    running = SimpleNamespace(id=77, zone_id=5, status="running")
    task_repository = SimpleNamespace(
        requeue_unpublished_execution=AsyncMock(return_value=running),
        list_unpublished_execution_by_owner=AsyncMock(return_value=[running]),
    )
    lease_repository = SimpleNamespace(release=AsyncMock(return_value=True))
    worker = _build_shutdown_worker(task_repository=task_repository)
    worker._zone_lease_repository = lease_repository

    released = await worker._maybe_release_unpublished_claim(task)
    assert released is True
    task_repository.requeue_unpublished_execution.assert_awaited_once()
    call_kwargs = task_repository.requeue_unpublished_execution.await_args.kwargs
    assert call_kwargs["task_id"] == 77
    assert call_kwargs["owner"] == "shutdown-test-worker"


@pytest.mark.asyncio
async def test_shutdown_does_not_release_claim_when_ae_command_exists() -> None:
    task = SimpleNamespace(id=55, zone_id=2, intent_id=0, topology="single_tank")
    claimed = SimpleNamespace(id=55, zone_id=2, status="claimed")
    task_repository = SimpleNamespace(
        requeue_unpublished_execution=AsyncMock(return_value=None),
        get_by_id=AsyncMock(return_value=claimed),
        release_claim=AsyncMock(return_value=True),
        list_claimed_by_owner=AsyncMock(return_value=[claimed]),
    )
    command_repository = SimpleNamespace(
        get_latest_for_task=AsyncMock(return_value={"id": 1, "status": "published"})
    )
    worker = _build_shutdown_worker(
        task_repository=task_repository,
        command_repository=command_repository,
    )
    released = await worker._maybe_release_unpublished_claim(task)
    assert released is False
    task_repository.requeue_unpublished_execution.assert_awaited_once()
    task_repository.release_claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_respawn_guard_ignored_during_shutdown() -> None:
    worker = _build_shutdown_worker()
    worker._pending_kicks = 2
    drain = asyncio.create_task(asyncio.sleep(60), name="drain-stub")
    worker._drain_task = drain
    worker._shutting_down = True
    worker._arm_respawn_on_done(drain)
    drain.cancel()
    with pytest.raises(asyncio.CancelledError):
        await drain
    await asyncio.sleep(0.01)
    assert worker._drain_task is drain
    assert worker._drain_task.done()


@pytest.mark.asyncio
async def test_shutdown_cancels_inflight_after_grace_timeout() -> None:
    started = asyncio.Event()

    async def _slow_execute(**kwargs: object) -> None:
        started.set()
        await asyncio.Event().wait()

    task = SimpleNamespace(id=11, zone_id=4, intent_id=0, topology="single_tank")
    claim_run = AsyncMock(side_effect=[(task, SimpleNamespace()), None])
    worker = _build_shutdown_worker(
        claim_run=claim_run,
        execute_run=AsyncMock(side_effect=_slow_execute),
        shutdown_grace_sec=0.05,
    )
    worker.kick()
    await asyncio.wait_for(started.wait(), timeout=1.0)

    await asyncio.wait_for(worker.shutdown(grace_sec=0.05), timeout=2.0)
    assert worker._drain_task is not None
    assert worker._drain_task.done()


def test_env_shutdown_grace_sec_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AE_SHUTDOWN_GRACE_SEC", raising=False)
    cfg = Ae3RuntimeConfig.from_env()
    assert cfg.shutdown_grace_sec == 30.0


def test_env_shutdown_grace_sec_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE_SHUTDOWN_GRACE_SEC", "12.5")
    cfg = Ae3RuntimeConfig.from_env()
    assert cfg.shutdown_grace_sec == 12.5
