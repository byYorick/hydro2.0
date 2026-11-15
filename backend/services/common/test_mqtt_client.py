"""MQTT reconnect, durable ACK timing and persistent subscription boundaries."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.mqtt import AsyncMqttClient, MqttClient


def test_disconnect_callback_leaves_reconnect_to_network_loop():
    """The network thread must return before it can process the new CONNACK."""

    client = MqttClient.__new__(MqttClient)
    client._connected = threading.Event()
    client._connected.set()
    client._client = MagicMock()
    client._on_disconnect(client._client, None, 7)
    assert not client._connected.is_set()
    client._client.reconnect.assert_not_called()
    # A subsequent CONNACK can now be dispatched by the same network thread.
    client._host, client._port, client._subs = 'mqtt', 1883, []
    client._on_connect(client._client, None, {}, 0)
    assert client._connected.is_set()


@pytest.mark.asyncio
async def test_durable_subscription_acks_only_after_async_handler_completes():

    client = MqttClient.__new__(MqttClient)
    client._manual_ack = True
    client._connection_generation = 1
    client._event_loop = asyncio.get_running_loop()
    started, release, acked = asyncio.Event(), asyncio.Event(), asyncio.Event()
    client._client = MagicMock()
    client._client.ack.side_effect = lambda *_: acked.set() or 0

    async def handler(topic, payload):
        started.set()
        await release.wait()

    message = SimpleNamespace(topic='test/telemetry', payload=b'{}', qos=1, mid=42)
    client._wrap(handler, ack_after_handler=True)(None, None, message)
    await asyncio.wait_for(started.wait(), 1)
    client._client.ack.assert_not_called()
    release.set()
    await asyncio.wait_for(acked.wait(), 1)
    client._client.ack.assert_called_once_with(42, 1)


@pytest.mark.asyncio
async def test_durable_delivery_from_old_connection_cannot_ack_reused_mid():

    client = MqttClient.__new__(MqttClient)
    client._manual_ack = True
    client._connection_generation = 1
    client._event_loop = asyncio.get_running_loop()
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    client._client = MagicMock()

    async def handler(topic, payload):
        started.set()
        await release.wait()
        finished.set()

    message = SimpleNamespace(topic='test/telemetry', payload=b'{}', qos=1, mid=42)
    client._wrap(handler, ack_after_handler=True)(None, None, message)
    await asyncio.wait_for(started.wait(), 1)
    client._connection_generation += 1
    release.set()
    await asyncio.wait_for(finished.wait(), 1)
    await asyncio.sleep(0)
    client._client.ack.assert_not_called()


@pytest.mark.asyncio
async def test_failed_durable_handler_is_not_acknowledged():

    client = MqttClient.__new__(MqttClient)
    client._manual_ack = True
    client._connection_generation = 1
    client._event_loop = asyncio.get_running_loop()
    completed = asyncio.Event()
    client._client = MagicMock()

    async def handler(topic, payload):
        completed.set()
        raise RuntimeError('synthetic handler failure')

    message = SimpleNamespace(topic='test/telemetry', payload=b'{}', qos=1, mid=42)
    client._wrap(handler, ack_after_handler=True)(None, None, message)
    await asyncio.wait_for(completed.wait(), 1)
    await asyncio.sleep(0)
    client._client.ack.assert_not_called()


@pytest.mark.asyncio
async def test_persistent_subscriptions_can_be_registered_before_connect():

    with patch('common.mqtt.MqttClient') as constructor:
        base = constructor.return_value
        client = AsyncMqttClient(manual_ack=True)
        handler = AsyncMock()
        await client.subscribe('test/telemetry', handler, ack_after_handler=True, start=False)
        base.start.assert_not_called()
        base.subscribe.assert_called_once_with('test/telemetry', handler, 1, ack_after_handler=True)
        await client.start()
        base.start.assert_called_once()


def test_durable_subscription_rejects_noncanonical_qos_zero():

    client = MqttClient.__new__(MqttClient)
    client._connection_generation = 1
    client._client = MagicMock()
    handler = AsyncMock()
    message = SimpleNamespace(topic='test/telemetry', payload=b'{}', qos=0, mid=42)
    client._wrap(handler, ack_after_handler=True)(None, None, message)
    handler.assert_not_called()
    client._client.ack.assert_not_called()


@pytest.mark.parametrize(('manual_ack', 'qos'), [(False, 1), (True, 0)])
def test_deferred_subscription_rejects_unsafe_ack_configuration(manual_ack, qos):

    client = MqttClient.__new__(MqttClient)
    client._manual_ack = manual_ack
    with pytest.raises(ValueError):
        client.subscribe('test/telemetry', AsyncMock(), qos=qos, ack_after_handler=True)
