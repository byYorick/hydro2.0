"""Failure-path tests exercising application code, with transport boundaries controlled."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import asyncpg
import pytest

from common.db import get_pool
from common.mqtt import MqttClient, _make_async_done_callback


def test_publish_transport_error_propagates_to_caller():
    client = MqttClient(client_id_suffix='_chaos')
    client._connected.set()
    client._client = MagicMock()
    client._client.publish.return_value.rc = 4  # MQTT_ERR_NO_CONN
    with pytest.raises(RuntimeError, match='publish failed'):
        client.publish_json('hydro/gh/zn/nd/ph/command', {'cmd': 'stop'})
    client._client.publish.assert_called_once()


def test_start_retries_transport_errors_then_fails_closed():
    client = MqttClient(client_id_suffix='_chaos')
    client._client = MagicMock()
    client._client._thread = None
    client._client.connect.side_effect = ConnectionError('broker unavailable')
    with patch.object(client._connected, 'wait', return_value=False):
        with pytest.raises(Exception, match='broker unavailable|failed to connect'):
            client.start()
    assert client._client.connect.call_count == 6
    assert not client.is_connected()


def test_handler_exception_is_logged_without_crashing_mqtt_callback(caplog):
    client = MqttClient(client_id_suffix='_chaos')
    handler = MagicMock(side_effect=ValueError('invalid telemetry'))
    handler.__name__ = 'broken_handler'
    callback = client._wrap(handler)
    callback(None, None, SimpleNamespace(topic='hydro/gh/zn/nd/ph/telemetry', payload=b'{}'))
    handler.assert_called_once()
    assert 'invalid telemetry' in caplog.text


def test_failed_async_handler_notifies_recovery_callback():
    handler = MagicMock()
    handler.__name__ = 'telemetry_ingest'
    future = Future()
    future.set_exception(ValueError('DB unavailable'))
    with patch('common.mqtt._notify_async_handler_error') as notify:
        _make_async_done_callback(handler, 'hydro/test')(future)
    notify.assert_called_once()
    assert isinstance(notify.call_args.args[2], ValueError)


@pytest.mark.asyncio
async def test_read_only_database_rejects_writes_and_pool_recovers():
    pool = await get_pool()
    async with pool.acquire() as conn:
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            async with conn.transaction(readonly=True):
                assert await conn.fetchval('SELECT 1') == 1
                # UPDATE is forbidden in a read-only transaction even for zero rows.
                # The system table exists before Laravel migrations too.
                await conn.execute('UPDATE pg_catalog.pg_class SET relname = relname WHERE false')
    async with pool.acquire() as conn:
        assert await conn.fetchval('SELECT 1') == 1
        assert await conn.fetchval('SHOW transaction_read_only') == 'off'
