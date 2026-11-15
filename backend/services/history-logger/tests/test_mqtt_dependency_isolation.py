"""Message-local dependency bindings must survive overlap, nesting and failure."""
import asyncio
from unittest.mock import AsyncMock

import pytest

import mqtt_handlers
import telemetry_processing
from handlers import command_response, heartbeat_status, node_event
from handlers.dependencies import snapshot
from telemetry.dependencies import snapshot as telemetry_snapshot
from telemetry import helpers as telemetry_helpers


@pytest.mark.asyncio
async def test_overlapping_command_responses_keep_their_own_fetch(monkeypatch):
    started, resume = asyncio.Event(), asyncio.Event()
    calls = []
    first, second = AsyncMock(), AsyncMock()
    original = command_response.fetch

    async def handle(topic, payload):
        if topic == 'first':
            started.set()
            await resume.wait()
        await snapshot({'fetch': original}).fetch(topic)
        calls.append(topic)

    monkeypatch.setattr(mqtt_handlers, '_handle_command_response_impl', handle)
    monkeypatch.setattr(mqtt_handlers, 'fetch', first)
    task = asyncio.create_task(mqtt_handlers.handle_command_response('first', b'{}'))
    await started.wait()
    monkeypatch.setattr(mqtt_handlers, 'fetch', second)
    await mqtt_handlers.handle_command_response('second', b'{}')
    resume.set()
    await task
    first.assert_awaited_once_with('first')
    second.assert_awaited_once_with('second')
    assert command_response.fetch is original
    assert calls == ['second', 'first']


@pytest.mark.asyncio
async def test_nested_handler_failure_restores_outer_context(monkeypatch):
    fetch = AsyncMock()
    defaults = {'fetch': object()}
    seen = []
    originals = (heartbeat_status.fetch, node_event.create_zone_event)

    async def event(topic, payload):
        seen.append(snapshot(defaults).fetch)
        raise RuntimeError('nested handler failed')

    async def heartbeat(topic, payload):
        seen.append(snapshot(defaults).fetch)
        with pytest.raises(RuntimeError, match='nested handler failed'):
            await mqtt_handlers.handle_node_event('event', b'{}')
        seen.append(snapshot(defaults).fetch)

    monkeypatch.setattr(mqtt_handlers, 'fetch', fetch)
    monkeypatch.setattr(mqtt_handlers, '_handle_heartbeat_impl', heartbeat)
    monkeypatch.setattr(mqtt_handlers, '_handle_node_event_impl', event)
    await mqtt_handlers.handle_heartbeat('heartbeat', b'{}')
    assert seen == [fetch, fetch, fetch]
    assert snapshot(defaults).fetch is defaults['fetch']
    assert (heartbeat_status.fetch, node_event.create_zone_event) == originals


@pytest.mark.asyncio
async def test_telemetry_binding_does_not_rewrite_helper_or_handler_globals(monkeypatch):
    fetch = AsyncMock()
    helper_fetch, handler_fetch = telemetry_helpers.fetch, command_response.fetch

    async def process(samples, entries=None):
        assert telemetry_snapshot({'fetch': helper_fetch}).fetch is fetch
        assert snapshot({'fetch': handler_fetch}).fetch is handler_fetch
        raise RuntimeError('write failed')

    monkeypatch.setattr(telemetry_processing, 'fetch', fetch)
    monkeypatch.setattr(telemetry_processing, '_process_telemetry_batch_impl', process)
    with pytest.raises(RuntimeError, match='write failed'):
        await telemetry_processing.process_telemetry_batch([])
    assert telemetry_helpers.fetch is helper_fetch
    assert command_response.fetch is handler_fetch
    assert telemetry_snapshot({'fetch': helper_fetch}).fetch is helper_fetch


@pytest.mark.asyncio
async def test_telemetry_component_callbacks_inherit_the_batch_context(monkeypatch):
    from types import SimpleNamespace
    from telemetry.dependencies import bind_dependencies

    started, resume = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr(telemetry_processing, '_zone_cache', {})

    async def fetch_first(query, zone_uids):
        started.set()
        await resume.wait()
        return [{'id': 1, 'uid': zone_uids[0]}]

    first = AsyncMock(side_effect=fetch_first)
    second = AsyncMock(return_value=[{'id': 2, 'uid': 'zn-second'}])

    async def resolve(uid, fetch):
        with bind_dependencies(fetch=fetch):
            return await telemetry_processing._resolve_batch_zones(
                samples=[SimpleNamespace(zone_uid=uid, gh_uid=None)]
            )

    task = asyncio.create_task(resolve('zn-first', first))
    await started.wait()
    assert await resolve('zn-second', second) == {('zn-second', None): 2}
    resume.set()
    assert await task == {('zn-first', None): 1}
    first.assert_awaited_once()
    second.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_route_scope_is_reset_after_failure(monkeypatch):
    import command_routes
    from commands.dependencies import async_dependency

    async def default():
        return 'default'

    resolve = async_dependency('fetch', default)
    fetch = AsyncMock(return_value='request')

    async def lifecycle(**kwargs):
        assert await resolve() == 'request'
        raise RuntimeError('lifecycle failed')

    monkeypatch.setattr(command_routes, 'fetch', fetch)
    monkeypatch.setattr(command_routes, 'ensure_command_for_publish', lifecycle)
    with pytest.raises(RuntimeError, match='lifecycle failed'):
        await command_routes._ensure_command_for_publish()
    assert await resolve() == 'default'


def test_nested_command_scope_restores_outer_values_after_exception():
    from commands.dependencies import bind_dependencies, sync_dependency

    resolve = sync_dependency('probe', lambda: 'default')
    with bind_dependencies(probe=lambda: 'outer'):
        assert resolve() == 'outer'
        with pytest.raises(ValueError):
            with bind_dependencies(probe=lambda: 'inner'):
                assert resolve() == 'inner'
                raise ValueError('failed')
        assert resolve() == 'outer'
    assert resolve() == 'default'
