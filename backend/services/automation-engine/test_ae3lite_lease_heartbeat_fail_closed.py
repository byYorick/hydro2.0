"""Unit-тесты fail-closed lease heartbeat (K6 / R4.1)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.infrastructure.metrics import LEASE_HEARTBEAT_FAILED, ZONE_LEASE_LOST
from ae3lite.runtime.worker import Ae3RuntimeWorker


def _build_worker(*, lease_repo: AsyncMock) -> Ae3RuntimeWorker:
    return Ae3RuntimeWorker(
        owner="test-worker",
        claim_next_task_use_case=MagicMock(),
        idle_poll_interval_sec=0.1,
        execute_task_use_case=MagicMock(),
        startup_recovery_use_case=MagicMock(),
        zone_lease_repository=lease_repo,
        zone_intent_repository=MagicMock(),
        spawn_background_task_fn=lambda coro, **_: asyncio.create_task(coro),
        now_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        logger=logging.getLogger("test-lease-heartbeat"),
        lease_ttl_sec=90,
        lease_heartbeat_max_failures=3,
        lease_heartbeat_transient_retries=1,
    )


@pytest.mark.asyncio
async def test_lease_heartbeat_signals_lost_after_consecutive_extend_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease_repo = AsyncMock()
    lease_repo.extend = AsyncMock(return_value=False)
    worker = _build_worker(lease_repo=lease_repo)
    lease_lost = asyncio.Event()
    alerts: list[dict] = []

    async def fake_sleep(_delay: float) -> None:
        return None

    async def fake_alert(**kwargs) -> None:
        alerts.append(kwargs)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr("ae3lite.runtime.worker.send_infra_alert", fake_alert)

    before_lost = ZONE_LEASE_LOST.labels(zone_id="7")._value.get()
    before_hb_failed = LEASE_HEARTBEAT_FAILED.labels(zone_id="7")._value.get()

    await worker._lease_heartbeat(zone_id=7, lease_lost_event=lease_lost)

    assert lease_lost.is_set()
    assert lease_repo.extend.await_count == 3
    assert ZONE_LEASE_LOST.labels(zone_id="7")._value.get() == before_lost + 1
    assert LEASE_HEARTBEAT_FAILED.labels(zone_id="7")._value.get() == before_hb_failed + 3
    assert len(alerts) == 1
    assert alerts[0]["code"] == "ae3_zone_lease_lost"


@pytest.mark.asyncio
async def test_extend_lease_with_transient_retry_recovers_from_db_error() -> None:
    lease_repo = AsyncMock()
    lease_repo.extend = AsyncMock(side_effect=[RuntimeError("db down"), True])
    worker = _build_worker(lease_repo=lease_repo)

    extended = await worker._extend_lease_with_transient_retry(zone_id=3)

    assert extended is True
    assert lease_repo.extend.await_count == 2
