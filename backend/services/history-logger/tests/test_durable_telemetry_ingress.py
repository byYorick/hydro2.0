"""QoS1 telemetry must remain unacknowledged during Redis backpressure."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

import state
from telemetry import ingress


@pytest.mark.asyncio
async def test_durable_telemetry_waits_for_redis_admission():
    payload = ('{"metric_type":"ph","value":6.5,"ts":%d}' % time.time()).encode()
    with (
        patch.object(state, 'shutdown_event', asyncio.Event()),
        patch.object(state, 'telemetry_queue', object()),
        patch.object(ingress, 'push_with_retry', AsyncMock(side_effect=[False, False, True])) as push,
        patch.object(ingress.asyncio, 'sleep', AsyncMock()) as sleep,
    ):
        await ingress.handle_telemetry('hydro/gh-1/zn-1/nd-1/ph/telemetry', payload, durable=True)
    assert push.await_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_shutdown_cancels_unadmitted_telemetry_without_success():
    payload = ('{"metric_type":"ph","value":6.5,"ts":%d}' % time.time()).encode()
    event = asyncio.Event()
    event.set()
    with (
        patch.object(state, 'shutdown_event', event),
        patch.object(state, 'telemetry_queue', object()),
        patch.object(ingress, 'push_with_retry', AsyncMock(return_value=False)),
    ):
        with pytest.raises(asyncio.CancelledError):
            await ingress.handle_telemetry('hydro/gh-1/zn-1/nd-1/ph/telemetry', payload, durable=True)
