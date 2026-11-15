"""MQTT facade dependencies must not leak between tasks or direct handlers."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from handlers import config_report
from handlers.dependencies import bind_dependencies, snapshot
import mqtt_handlers


@pytest.mark.asyncio
async def test_config_report_helpers_keep_task_local_database_dependencies():
    original_fetch = config_report.fetch
    original_execute = config_report.execute
    both_started = asyncio.Event()
    entered = []

    async def run(node_id):
        async def fetch(query, *args):
            entered.append(node_id)
            if len(entered) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), 2)
            return [{'id': node_id * 10, 'sensor_type': 'ph', 'meta': {}}]

        execute = AsyncMock()
        with bind_dependencies(fetch=fetch, execute=execute):
            await mqtt_handlers._complete_sensor_calibrations_after_config_report(
                node_id, {'calibration': {'ph': {'slope': 1}}}
            )
        execute.assert_awaited_once()
        assert execute.await_args.args[1] == node_id * 10

    await asyncio.gather(run(1), run(2))
    assert config_report.fetch is original_fetch
    assert config_report.execute is original_execute
    assert snapshot(vars(config_report)).fetch is original_fetch


def test_nested_dependency_scope_restores_parent_even_on_error():
    first, second = object(), object()
    with bind_dependencies(fetch=first):
        with pytest.raises(ValueError):
            with bind_dependencies(fetch=second):
                assert snapshot(vars(config_report)).fetch is second
                raise ValueError('synthetic error')
        assert snapshot(vars(config_report)).fetch is first
    assert snapshot(vars(config_report)).fetch is config_report.fetch
