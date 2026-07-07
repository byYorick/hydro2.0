"""Unit-тесты retry intent↔task sync и метрики ae3_intent_sync_failed_total."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.infrastructure.metrics import INTENT_SYNC_FAILED
from ae3lite.runtime.worker import Ae3RuntimeWorker


def _build_worker(*, intent_repo: AsyncMock) -> Ae3RuntimeWorker:
    return Ae3RuntimeWorker(
        owner="test-worker",
        claim_next_task_use_case=MagicMock(),
        idle_poll_interval_sec=0.1,
        execute_task_use_case=MagicMock(),
        startup_recovery_use_case=MagicMock(),
        zone_lease_repository=MagicMock(),
        zone_intent_repository=intent_repo,
        spawn_background_task_fn=MagicMock(),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=logging.getLogger("test-intent-sync"),
        intent_sync_max_retries=2,
    )


@pytest.mark.asyncio
async def test_safe_mark_intent_running_retries_then_increments_metric() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_running = AsyncMock(side_effect=[RuntimeError("db"), RuntimeError("db"), RuntimeError("db")])
    worker = _build_worker(intent_repo=intent_repo)

    before = INTENT_SYNC_FAILED.labels(operation="mark_running")._value.get()
    await worker._safe_mark_intent_running(intent_id=42)
    after = INTENT_SYNC_FAILED.labels(operation="mark_running")._value.get()

    assert intent_repo.mark_running.await_count == 3
    assert after == before + 1


@pytest.mark.asyncio
async def test_safe_mark_intent_terminal_succeeds_on_second_attempt() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_terminal = AsyncMock(side_effect=[RuntimeError("db"), None])
    worker = _build_worker(intent_repo=intent_repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    before = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()
    await worker._safe_mark_intent_terminal_result(
        intent_id=7,
        now=now,
        success=False,
        error_code="command_timeout",
        error_message="timeout",
    )
    after = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()

    assert intent_repo.mark_terminal.await_count == 2
    assert after == before
