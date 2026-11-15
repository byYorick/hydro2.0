"""Worker policies preserve fencing, cancellation and per-zone failure budgets."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ae3lite.runtime import intent_sync, lease_heartbeat


@pytest.mark.asyncio
async def test_heartbeat_failure_budget_is_per_zone_and_resets_after_success(monkeypatch):
    original_sleep = asyncio.sleep

    async def tick(_seconds):
        await original_sleep(0)

    monkeypatch.setattr(asyncio, 'sleep', tick)
    outcomes = {1: [None, True, None, False], 2: [None, None]}
    calls = {1: 0, 2: 0}
    signals = {}
    events = {1: asyncio.Event(), 2: asyncio.Event()}

    async def extend(*, zone_id, claim_generation):
        assert claim_generation == zone_id + 10
        calls[zone_id] += 1
        return outcomes[zone_id].pop(0)

    async def lost(*, zone_id, lease_lost_event, consecutive_failures):
        signals[zone_id] = consecutive_failures
        lease_lost_event.set()

    await asyncio.gather(
        *[
            lease_heartbeat.run_lease_heartbeat(
                zone_id=zone_id,
                claim_generation=zone_id + 10,
                lease_lost_event=events[zone_id],
                owner='owner',
                lease_ttl_sec=30,
                max_failures=2,
                extend_lease=extend,
                signal_lost=lost,
                logger=logging.getLogger('policy-test'),
                log_debug=MagicMock(),
            )
            for zone_id in (1, 2)
        ]
    )
    assert calls == {1: 4, 2: 2}
    assert signals == {1: 1, 2: 2}
    assert all(event.is_set() for event in events.values())


@pytest.mark.asyncio
async def test_transient_retry_keeps_fence_and_obtains_a_fresh_timestamp():
    repo = SimpleNamespace(extend=AsyncMock(side_effect=[OSError('transport'), True]))
    first = datetime(2026, 11, 14)
    times = iter([first, first + timedelta(seconds=1)])
    assert (
        await lease_heartbeat.extend_lease_with_transient_retry(
            zone_id=7,
            claim_generation=42,
            lease_repository=repo,
            owner='writer',
            now_fn=lambda: next(times),
            lease_ttl_sec=90,
            transient_retries=1,
            logger=logging.getLogger('policy-test'),
        )
        is True
    )
    assert [call.kwargs for call in repo.extend.await_args_list] == [
        dict(zone_id=7, claim_generation=42, owner='writer', now=now, lease_ttl_sec=90)
        for now in (first, first + timedelta(seconds=1))
    ]


@pytest.mark.asyncio
async def test_alert_outage_cannot_prevent_lease_lost_signal():
    lost = asyncio.Event()
    alert = AsyncMock(side_effect=OSError('alert service down'))
    await lease_heartbeat.signal_lease_lost(
        zone_id=7,
        lease_lost_event=lost,
        consecutive_failures=1,
        owner='writer',
        logger=logging.getLogger('policy-test'),
        send_alert=alert,
    )
    assert lost.is_set()
    alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_lease_extension_is_never_retried():
    repo = SimpleNamespace(extend=AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await lease_heartbeat.extend_lease_with_transient_retry(
            zone_id=7,
            claim_generation=42,
            lease_repository=repo,
            owner='writer',
            now_fn=datetime.now,
            lease_ttl_sec=90,
            transient_retries=5,
            logger=logging.getLogger('policy-test'),
        )
    assert repo.extend.await_count == 1


@pytest.mark.parametrize('operation', ['running', 'terminal'])
@pytest.mark.asyncio
async def test_cancelled_intent_sync_does_not_retry_or_emit_exhaustion(operation):
    update = AsyncMock(side_effect=asyncio.CancelledError)
    repo = SimpleNamespace(mark_running=update, mark_terminal=update)
    notify = AsyncMock()
    args = dict(
        intent_id=3,
        task_id=8,
        zone_id=7,
        intent_repository=repo,
        max_retries=5,
        logger=logging.getLogger('policy-test'),
        notify_exhausted=notify,
    )
    with pytest.raises(asyncio.CancelledError):
        if operation == 'running':
            await intent_sync.mark_intent_running(now_fn=datetime.now, **args)
        else:
            await intent_sync.mark_intent_terminal(
                now=datetime.now(), success=True, error_code=None, error_message=None, **args
            )
    assert update.await_count == 1
    notify.assert_not_awaited()
