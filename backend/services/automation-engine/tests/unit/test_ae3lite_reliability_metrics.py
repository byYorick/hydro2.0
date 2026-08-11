"""Unit-тесты метрик R2.2 и COMMAND_DISPATCH_DURATION."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.infrastructure.gateways.command_publish_pipeline import CommandPublishPipeline
from ae3lite.infrastructure.metrics import COMMAND_DISPATCH_DURATION, OLDEST_ACTIVE_TASK_AGE_SECONDS
from ae3lite.infrastructure.repositories.automation_task_repository import PgAutomationTaskRepository
from ae3lite.runtime.worker import Ae3RuntimeWorker


@pytest.mark.asyncio
async def test_command_publish_pipeline_observes_dispatch_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[float] = []
    original_observe = COMMAND_DISPATCH_DURATION.observe

    def _capture(value: float) -> None:
        observed.append(value)
        original_observe(value)

    monkeypatch.setattr(COMMAND_DISPATCH_DURATION, "observe", _capture)

    async def _slow_publish(**_kwargs) -> str:
        return "legacy-cmd-1"

    command_repo = MagicMock()
    command_repo.resolve_greenhouse_uid = AsyncMock(return_value="gh-1")
    command_repo.get_next_step_no = AsyncMock(return_value=1)
    command_repo.allocate_and_create_pending = AsyncMock(return_value=(9, 1, False, "pending"))
    command_repo.mark_publish_published_unconfirmed = AsyncMock()
    command_repo.mark_publish_accepted = AsyncMock(return_value=True)
    command_repo.resolve_legacy_command_id = AsyncMock(return_value=1001)

    hl_client = MagicMock()
    hl_client.publish = AsyncMock(side_effect=_slow_publish)

    pipeline = CommandPublishPipeline(
        command_repository=command_repo,
        history_logger_client=hl_client,
    )
    task = MagicMock(id=1, zone_id=1)
    command = PlannedCommand(
        node_uid="nd-1",
        channel="pump_main",
        step_no=1,
        payload={"cmd": "set_relay", "params": {"state": True}},
    )

    await pipeline.publish(task=task, command=command, now=datetime(2026, 7, 7, 12, 0, 0))

    assert len(observed) == 1
    assert observed[0] >= 0.0


@pytest.mark.asyncio
async def test_refresh_active_task_age_metrics_sets_gauges(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = PgAutomationTaskRepository()
    now = datetime(2026, 7, 7, 12, 0, 0)

    async def fake_fetch(query: str, *args):
        assert "GROUP BY status" in query
        return [
            {"status": "running", "oldest_age_sec": 42.5},
            {"status": "waiting_command", "oldest_age_sec": 10.0},
        ]

    monkeypatch.setattr(repo, "_fetch", fake_fetch)

    await repo.refresh_active_task_age_metrics(now=now)

    assert OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status="running")._value.get() == 42.5
    assert OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status="waiting_command")._value.get() == 10.0
    assert OLDEST_ACTIVE_TASK_AGE_SECONDS.labels(status="claimed")._value.get() == 0.0


def _build_metrics_worker(*, task_repository: object) -> Ae3RuntimeWorker:
    return Ae3RuntimeWorker(
        owner="metrics-test",
        claim_next_task_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        idle_poll_interval_sec=0.01,
        execute_task_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        startup_recovery_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        waiting_command_reconcile_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        task_repository=task_repository,
        zone_lease_repository=SimpleNamespace(release=AsyncMock(return_value=True)),
        zone_intent_repository=SimpleNamespace(
            mark_running=AsyncMock(return_value=None),
            mark_terminal=AsyncMock(return_value=None),
        ),
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(
            coro,
            name=str(kwargs.get("task_name") or "ae3-metrics-test"),
        ),
        now_fn=lambda: datetime(2026, 7, 7, 12, 0, 0),
        logger=MagicMock(),
        stale_task_reconcile_interval_sec=60.0,
    )


@pytest.mark.asyncio
async def test_worker_refresh_active_task_age_metrics_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    refresh = AsyncMock()
    task_repository = SimpleNamespace(refresh_active_task_age_metrics=refresh)
    worker = _build_metrics_worker(task_repository=task_repository)
    worker._active_task_age_metrics_interval_sec = 60.0

    await worker._maybe_refresh_active_task_age_metrics_once()
    await worker._maybe_refresh_active_task_age_metrics_once()

    assert refresh.await_count == 1
    refresh.assert_awaited_once_with(now=datetime(2026, 7, 7, 12, 0, 0))

    worker._last_active_task_age_metrics_monotonic = None
    monkeypatch.setattr("ae3lite.runtime.worker.time.monotonic", lambda: 100.0)
    await worker._maybe_refresh_active_task_age_metrics_once()
    assert refresh.await_count == 2
