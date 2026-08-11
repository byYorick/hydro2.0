"""Unit-тесты retry intent↔task sync и метрики ae3_intent_sync_failed_total."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ae3lite.application.use_cases.orphan_intent_reconcile import OrphanIntentReconcileUseCase
from ae3lite.infrastructure.metrics import INTENT_SYNC_FAILED, ORPHAN_INTENT_RECONCILED
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
    with patch("ae3lite.runtime.worker.send_infra_alert", new_callable=AsyncMock) as alert_mock:
        ok = await worker._safe_mark_intent_running(intent_id=42, task_id=7, zone_id=3)
    after = INTENT_SYNC_FAILED.labels(operation="mark_running")._value.get()

    assert ok is False
    assert intent_repo.mark_running.await_count == 3
    assert after == before + 1
    alert_mock.assert_awaited_once()
    assert alert_mock.await_args.kwargs["code"] == "ae3_intent_sync_failed"
    assert alert_mock.await_args.kwargs["intent_id"] == 42


@pytest.mark.asyncio
async def test_execute_claimed_task_aborts_when_intent_sync_exhausted() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_running = AsyncMock(side_effect=RuntimeError("db"))
    intent_repo.mark_terminal = AsyncMock(return_value=None)
    task_repo = AsyncMock()
    task_repo.fail_for_recovery = AsyncMock(return_value=None)
    lease_repo = AsyncMock()
    lease_repo.release = AsyncMock(return_value=True)
    execute_uc = AsyncMock()

    worker = Ae3RuntimeWorker(
        owner="test-worker",
        claim_next_task_use_case=MagicMock(),
        idle_poll_interval_sec=0.1,
        execute_task_use_case=execute_uc,
        startup_recovery_use_case=MagicMock(),
        task_repository=task_repo,
        zone_lease_repository=lease_repo,
        zone_intent_repository=intent_repo,
        spawn_background_task_fn=MagicMock(),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=logging.getLogger("test-intent-sync"),
        intent_sync_max_retries=0,
    )
    task = MagicMock(id=7, zone_id=3, intent_id=42, topology="two_tank")

    with patch("ae3lite.runtime.worker.send_infra_alert", new_callable=AsyncMock):
        await worker._execute_claimed_task(task=task)

    execute_uc.run.assert_not_awaited()
    task_repo.fail_for_recovery.assert_awaited_once()
    assert task_repo.fail_for_recovery.await_args.kwargs["error_code"] == "ae3_intent_sync_failed"
    lease_repo.release.assert_awaited()
    intent_repo.mark_terminal.assert_awaited_once()


@pytest.mark.asyncio
async def test_safe_mark_intent_terminal_succeeds_on_second_attempt() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_terminal = AsyncMock(side_effect=[RuntimeError("db"), None])
    worker = _build_worker(intent_repo=intent_repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    before = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()
    with patch("ae3lite.runtime.worker.send_infra_alert", new_callable=AsyncMock) as alert_mock:
        synced = await worker._safe_mark_intent_terminal_result(
            intent_id=7,
            now=now,
            success=False,
            error_code="command_timeout",
            error_message="timeout",
            task_id=11,
            zone_id=3,
        )
    after = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()

    assert synced is True
    assert intent_repo.mark_terminal.await_count == 2
    assert after == before
    alert_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_safe_mark_intent_terminal_exhausted_sends_alert_and_returns_false() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_terminal = AsyncMock(side_effect=RuntimeError("db"))
    worker = _build_worker(intent_repo=intent_repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    before = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()
    with patch("ae3lite.runtime.worker.send_infra_alert", new_callable=AsyncMock) as alert_mock:
        synced = await worker._safe_mark_intent_terminal_result(
            intent_id=7,
            now=now,
            success=True,
            error_code=None,
            error_message=None,
            task_id=11,
            zone_id=3,
        )
    after = INTENT_SYNC_FAILED.labels(operation="mark_terminal")._value.get()

    assert synced is False
    assert intent_repo.mark_terminal.await_count == 3
    assert after == before + 1
    alert_mock.assert_awaited_once()
    assert alert_mock.await_args.kwargs["code"] == "ae3_intent_sync_failed"
    assert alert_mock.await_args.kwargs["intent_id"] == 7
    assert alert_mock.await_args.kwargs["details"]["task_id"] == 11


@pytest.mark.asyncio
async def test_orphan_intent_reconcile_retries_terminal_sync() -> None:
    intent_repo = AsyncMock()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    intent_repo.list_orphan_active_intents_with_terminal_tasks = AsyncMock(
        return_value=[
            {
                "intent_id": 42,
                "zone_id": 3,
                "task_id": 7,
                "task_status": "failed",
                "error_code": "command_timeout",
                "error_message": "timeout",
            }
        ]
    )
    use_case = OrphanIntentReconcileUseCase(zone_intent_repository=intent_repo, batch_limit=8)
    sync_fn = AsyncMock(return_value=True)

    before = ORPHAN_INTENT_RECONCILED.labels(outcome="succeeded")._value.get()
    result = await use_case.run(now=now, sync_terminal_fn=sync_fn)
    after = ORPHAN_INTENT_RECONCILED.labels(outcome="succeeded")._value.get()

    assert result.scanned_intents == 1
    assert result.reconciled_intents == 1
    assert result.failed_intents == 0
    assert after == before + 1
    sync_fn.assert_awaited_once_with(
        intent_id=42,
        now=now,
        success=False,
        error_code="command_timeout",
        error_message="timeout",
        task_id=7,
        zone_id=3,
    )


@pytest.mark.asyncio
async def test_sync_orphan_intent_terminal_resolves_alert_on_success() -> None:
    intent_repo = AsyncMock()
    intent_repo.mark_terminal = AsyncMock(return_value=None)
    worker = _build_worker(intent_repo=intent_repo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with patch("ae3lite.runtime.worker.send_infra_resolved_alert", new_callable=AsyncMock) as resolved_mock:
        synced = await worker._sync_orphan_intent_terminal(
            intent_id=42,
            now=now,
            success=False,
            error_code="command_timeout",
            error_message="timeout",
            task_id=7,
            zone_id=3,
        )

    assert synced is True
    resolved_mock.assert_awaited_once()
    assert resolved_mock.await_args.kwargs["code"] == "ae3_intent_sync_failed"
    assert resolved_mock.await_args.kwargs["intent_id"] == 42


@pytest.mark.asyncio
async def test_maybe_run_orphan_intent_reconcile_once_respects_interval() -> None:
    intent_repo = AsyncMock()
    orphan_use_case = AsyncMock()
    orphan_use_case.run = AsyncMock(
        return_value=MagicMock(scanned_intents=0, reconciled_intents=0, failed_intents=0)
    )
    worker = Ae3RuntimeWorker(
        owner="test-worker",
        claim_next_task_use_case=MagicMock(),
        idle_poll_interval_sec=0.1,
        execute_task_use_case=MagicMock(),
        startup_recovery_use_case=MagicMock(),
        zone_lease_repository=MagicMock(),
        zone_intent_repository=intent_repo,
        orphan_intent_reconcile_use_case=orphan_use_case,
        orphan_intent_reconcile_interval_sec=3600.0,
        spawn_background_task_fn=MagicMock(),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=logging.getLogger("test-intent-sync"),
    )

    await worker._maybe_run_orphan_intent_reconcile_once()
    await worker._maybe_run_orphan_intent_reconcile_once()

    orphan_use_case.run.assert_awaited_once()
