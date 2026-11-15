"""Reconcile polling preserves order, cancellation and recovery from outages."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from ae3lite.runtime.reconcile_loop import ReconcileLoop


def loop_for(*, steps, wake=None, is_stopping=lambda: False):
    return ReconcileLoop(
        steps=steps,
        is_stopping=is_stopping,
        wake=wake or asyncio.Event(),
        poll_interval_sec=0.25,
        owner='worker-test',
        logger=logging.getLogger('reconcile-test'),
        log_debug=Mock(),
    )


@pytest.mark.asyncio
async def test_steps_run_in_order_and_shutdown_skips_polling():
    calls = []
    stopping = False

    async def first():
        calls.append('first')

    async def last():
        nonlocal stopping
        calls.append('last')
        stopping = True

    loop = loop_for(steps=[first, last], is_stopping=lambda: stopping)
    await asyncio.wait_for(loop.run(), timeout=1)
    assert calls == ['first', 'last']
    assert loop.consecutive_errors == 0


@pytest.mark.asyncio
async def test_failures_skip_remaining_steps_and_backoff_resets_after_success(monkeypatch):
    sleeps = []
    ticks = 0
    stopping = False
    tail = AsyncMock()

    async def step():
        nonlocal ticks, stopping
        ticks += 1
        if ticks <= 8 or ticks == 10:
            raise OSError('database unavailable')
        if ticks == 11:
            stopping = True

    async def wait_for(awaitable, *, timeout):
        # Complete the Event coroutine before simulating a timeout.
        awaitable.close()
        sleeps.append(timeout)
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, 'wait_for', wait_for)
    loop = loop_for(steps=[step, tail], is_stopping=lambda: stopping)
    await loop.run()
    assert sleeps == [0.25, 0.25, 2, 4, 8, 16, 30, 30, 0.25, 0.25]
    assert tail.await_count == 2
    assert loop.consecutive_errors == 0


@pytest.mark.asyncio
async def test_cancellation_from_a_step_is_not_counted_as_reconcile_failure():
    step = AsyncMock(side_effect=asyncio.CancelledError)
    tail = AsyncMock()
    loop = loop_for(steps=[step, tail])
    with pytest.raises(asyncio.CancelledError):
        await loop.run()
    assert loop.consecutive_errors == 0
    tail.assert_not_awaited()


@pytest.mark.asyncio
async def test_wake_interrupts_failure_backoff_and_is_cleared():
    reached_backoff = asyncio.Event()

    class WakeEvent(asyncio.Event):
        async def wait(self):
            reached_backoff.set()
            return await super().wait()

    wake = WakeEvent()
    ticks = 0
    stopping = False

    async def step():
        nonlocal ticks, stopping
        ticks += 1
        if ticks == 1:
            raise OSError('database unavailable')
        stopping = True

    loop = loop_for(steps=[step], wake=wake, is_stopping=lambda: stopping)
    loop.consecutive_errors = 2
    running = asyncio.create_task(loop.run())
    try:
        await asyncio.wait_for(reached_backoff.wait(), timeout=1)
        assert loop.consecutive_errors == 3
        wake.set()
        await asyncio.wait_for(running, timeout=1)
    finally:
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
    assert ticks == 2
    assert not wake.is_set()
    assert loop.consecutive_errors == 0


@pytest.mark.asyncio
async def test_cancelling_during_poll_propagates():
    entered = asyncio.Event()
    wake = asyncio.Event()

    async def step():
        entered.set()

    loop = loop_for(steps=[step], wake=wake)
    loop._poll_interval_sec = 60
    running = asyncio.create_task(loop.run())
    await asyncio.wait_for(entered.wait(), timeout=1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
