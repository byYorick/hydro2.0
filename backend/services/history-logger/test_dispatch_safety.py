"""Regression tests: restart recovery must not turn uncertainty into another dose."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from commands import drain, dispatch


@asynccontextmanager
async def claim(*args, **kwargs):
    yield True


@pytest.mark.asyncio
@pytest.mark.parametrize('cmd,age', [('dose', 1), ('run_pump', 1), ('state', 61), ('state', None)])
async def test_recovery_never_republishes_unsafe_or_expired_commands(cmd, age):
    row = dict(cmd_id='cmd-1', zone_id=1, node_id=1, node_uid='nd-1', channel='pump',
               cmd=cmd, params={}, source='automation-engine', status='SEND_FAILED',
               created_at=datetime.now(timezone.utc)-timedelta(seconds=age) if age is not None else None)
    with patch.object(drain, '_claim_stale_queued_command_rows', AsyncMock(return_value=[row])), \
         patch.object(drain, '_try_claim_cmd_for_publish', claim), \
         patch.object(drain, '_abandon_non_republishable_command', AsyncMock(return_value=True)) as abandon, \
         patch.object(drain, 'publish_command_with_retry', AsyncMock()) as publish:
        result = await drain.drain_stale_queued_commands_once()
    publish.assert_not_awaited()
    abandon.assert_awaited_once()
    assert result == dict(scanned=1, drained=0, skipped=1, failed=0)


@pytest.mark.asyncio
async def test_dispatch_reservation_fails_closed_when_already_reserved():
    with patch('common.db.execute', AsyncMock(return_value='UPDATE 0')):
        with pytest.raises(HTTPException) as exc:
            await dispatch.reserve_dispatch('cmd-1')
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_dispatch_reservation_requires_database_confirmation():
    with patch('common.db.execute', AsyncMock(side_effect=ConnectionError('unavailable'))):
        with pytest.raises(ConnectionError):
            await dispatch.reserve_dispatch('cmd-1')


@pytest.mark.asyncio
async def test_crash_marker_blocks_second_mutating_dispatch():
    from commands import lifecycle
    row = dict(status='QUEUED', source='api', sent_at=None, zone_id=1, node_id=1,
               channel='pump', cmd='dose', params={'ml': 1, '__hl_dispatch_started': True})
    with patch.object(lifecycle, 'fetch', AsyncMock(return_value=[row])):
        with pytest.raises(HTTPException) as exc:
            await lifecycle.ensure_command_for_publish(cmd_id='cmd-1', zone_id=1, node_id=1,
                node_uid='nd-1', channel='pump', cmd_name='dose', params={'ml': 1}, command_source='api')
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_shared_dispatch_lock_excludes_concurrent_requests():
    class Connection:
        locked = False
        async def fetchval(self, query, *args):
            if 'pg_try_advisory_lock' in query:
                if self.locked:
                    return False
                self.locked = True
                return True
            return 1
        async def execute(self, query, *args):
            self.locked = False
    connection = Connection()
    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield connection
    with patch.object(dispatch, 'get_pool', AsyncMock(return_value=Pool())):
        async with dispatch._try_claim_cmd_for_publish('cmd-1', allow_missing=True) as first:
            assert first
            async with dispatch._try_claim_cmd_for_publish('cmd-1', allow_missing=True) as second:
                assert not second
        async with dispatch._try_claim_cmd_for_publish('cmd-1', allow_missing=True) as third:
            assert third


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [('ok', 200), ('degraded', 503)])
async def test_readiness_reports_dependency_failure(status, code):
    import system_routes
    with patch.object(system_routes, 'health', AsyncMock(return_value={'status': status, 'components': {}})):
        response = await system_routes.readiness()
    assert response.status_code == code


def test_node_specific_wrap_credentials(tmp_path, monkeypatch):
    import json
    from commands.node_secret_wire import prepare_node_config_for_mqtt, unwrap_node_secret
    path = tmp_path / 'credentials.json'
    path.write_text(json.dumps({'nd-A': 'unique-node-A-password', 'nd-B': 'unique-node-B-password'}))
    monkeypatch.setenv('MQTT_NODE_PASSWORDS_FILE', str(path))
    payload = prepare_node_config_for_mqtt({}, node_uid='nd-A', node_secret='secret-A')
    assert unwrap_node_secret(payload['node_secret_enc'], 'unique-node-A-password', 'nd-A') == 'secret-A'
    with pytest.raises(Exception):
        unwrap_node_secret(payload['node_secret_enc'], 'unique-node-B-password', 'nd-A')
    with pytest.raises(HTTPException):
        prepare_node_config_for_mqtt({}, node_uid='nd-unknown', node_secret='secret')


@pytest.mark.asyncio
async def test_concurrent_request_dependencies_are_isolated():
    import asyncio
    from commands.dependencies import bind_dependencies, async_dependency
    async def default():
        return 'default'
    resolve = async_dependency('isolation_probe', default)
    async def request(value):
        async def dependency():
            return value
        with bind_dependencies(isolation_probe=dependency):
            await asyncio.sleep(0)
            return await resolve()
    assert await asyncio.gather(request('first'), request('second')) == ['first', 'second']
    assert await resolve() == 'default'


@pytest.mark.asyncio
async def test_dispatch_keeps_pool_capacity_for_lifecycle_queries():
    class Connection:
        async def fetchval(self, *args): return 1
        async def execute(self, *args): return 'SELECT 1'
    class Pool:
        acquired = 0
        def get_max_size(self): return 2
        @asynccontextmanager
        async def acquire(self):
            self.acquired += 1
            yield Connection()
    pool = Pool()
    with patch.object(dispatch, 'get_pool', AsyncMock(return_value=pool)):
        async with dispatch._try_claim_cmd_for_publish('cmd-A') as first:
            assert first
            async with dispatch._try_claim_cmd_for_publish('cmd-B') as second:
                assert not second
            assert pool.acquired == 1
