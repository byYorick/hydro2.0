"""
Тесты для batch processing в history-logger.
Проверяет кеширование, batch resolve, batch insert и batch upsert.
"""
import time
from datetime import datetime
from common.utils.time import utcnow
from unittest.mock import patch

import pytest
import telemetry_processing as tp
from telemetry_processing import (
    _node_cache,
    _zone_cache,
    _sensor_cache,
    _zone_greenhouse_cache,
    process_telemetry_batch,
    refresh_caches,
)
from models import TelemetrySampleModel


@pytest.mark.asyncio
async def test_batch_resolve_zones():
    """Тест batch resolve для зон."""
    with patch('telemetry_processing.fetch') as mock_fetch:
        mock_fetch.return_value = [
            {'id': 1, 'uid': 'zn-1', 'gh_uid': 'gh-1'},
            {'id': 2, 'uid': 'zn-2', 'gh_uid': 'gh-1'},
        ]
        
        # Очищаем кеш
        global _zone_cache
        _zone_cache.clear()
        _sensor_cache.clear()
        
        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMPERATURE',
                value=25.0,
                ts=utcnow()
            ),
            TelemetrySampleModel(
                zone_uid='zn-2',
                gh_uid='gh-1',
                node_uid='nd-2',
                metric_type='HUMIDITY',
                value=60.0,
                ts=utcnow()
            ),
        ]
        
        # Первый вызов должен сделать batch resolve
        with patch('telemetry_processing.execute') as mock_execute:
            mock_execute.return_value = None
            await process_telemetry_batch(samples)
        
        # Проверяем, что был вызван batch resolve
        assert mock_fetch.called


@pytest.mark.asyncio
async def test_cache_refresh():
    """Тест обновления кеша."""
    with patch('telemetry_processing.fetch') as mock_fetch:
        mock_fetch.return_value = [
            {'id': 1, 'uid': 'zn-1', 'gh_uid': 'gh-1'},
        ]
        
        await refresh_caches()
        
        # Проверяем, что кеш обновлен
        assert ('zn-1', 'gh-1') in _zone_cache


@pytest.mark.asyncio
async def test_batch_upsert_telemetry_last():
    """Тест batch upsert для telemetry_last."""
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        mock_fetch.return_value = [
            {'id': 1, 'uid': 'zn-1', 'gh_uid': 'gh-1'},
        ]

        _zone_cache.clear()
        _node_cache.clear()
        tp._cache_last_update = time.time()
        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMPERATURE',
                value=25.0,
                ts=utcnow()
            ),
        ]

        _sensor_cache.clear()
        _sensor_cache[(1, 10, "TEMPERATURE", "TEMPERATURE")] = 101
        
        await process_telemetry_batch(samples)
        
        # Проверяем, что был вызван batch upsert (один запрос для всех обновлений)
        upsert_calls = [call for call in mock_execute.call_args_list 
                       if 'telemetry_last' in str(call)]
        assert len(upsert_calls) > 0


@pytest.mark.asyncio
async def test_batch_upsert_telemetry_last_joins_sensors_to_avoid_fk_errors():
    """Проверяем SQL-контракт: upsert telemetry_last фильтрует только существующие sensor_id."""
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        mock_fetch.return_value = [
            {'id': 1, 'uid': 'zn-1', 'gh_uid': 'gh-1'},
        ]

        _zone_cache.clear()
        _node_cache.clear()
        tp._cache_last_update = time.time()
        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMPERATURE',
                value=25.0,
                ts=utcnow()
            ),
        ]

        _sensor_cache.clear()
        _sensor_cache[(1, 10, "TEMPERATURE", "TEMPERATURE")] = 101

        await process_telemetry_batch(samples)

        telemetry_last_queries = [
            call.args[0]
            for call in mock_execute.call_args_list
            if call.args and 'telemetry_last' in str(call.args[0])
        ]
        assert telemetry_last_queries
        query = telemetry_last_queries[0]
        assert "JOIN sensors s ON s.id = i.sensor_id" in query
        assert "UNNEST(" in query


@pytest.mark.asyncio
async def test_batch_insert_telemetry_samples_joins_sensors_to_avoid_fk_errors():
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        # return_value instead of side_effect — fetch may be called
        # more than once (cache refresh, sensor filter, etc.)
        mock_fetch.return_value = [{'id': 101}]

        _zone_cache.clear()
        _node_cache.clear()
        _sensor_cache.clear()
        tp._cache_last_update = time.time()
        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)
        _sensor_cache[(1, 10, "TEMPERATURE", "TEMPERATURE")] = 101

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMPERATURE',
                value=25.0,
                ts=utcnow()
            ),
        ]

        mock_execute.return_value = "INSERT 0 1"

        await process_telemetry_batch(samples)

        telemetry_samples_queries = [
            call.args[0]
            for call in mock_execute.call_args_list
            if call.args and 'telemetry_samples' in str(call.args[0])
        ]
        assert telemetry_samples_queries
        query = telemetry_samples_queries[0]
        assert "WITH incoming (sensor_id, ts, zone_id, value, quality, metadata) AS" in query
        assert "FROM UNNEST(" in query
        assert "JOIN sensors s" in query
        assert "s.id = incoming.sensor_id" in query
        assert "s.zone_id = incoming.zone_id" in query
        assert "$1::bigint[]" in query
        assert "$3::bigint[]" in query


@pytest.mark.asyncio
async def test_filter_existing_sensor_ids_casts_bigint_array():
    with patch('telemetry_processing.fetch') as mock_fetch:
        mock_fetch.return_value = [{'id': 101}]

        result = await tp._filter_existing_sensor_ids([101])

        assert result == {101}
        query = mock_fetch.call_args.args[0]
        assert "ANY($1::bigint[])" in query


@pytest.mark.asyncio
async def test_batch_processing_drops_stale_sensor_cache_entries_before_insert():
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        _zone_cache.clear()
        _node_cache.clear()
        _sensor_cache.clear()
        tp._cache_last_update = time.time()
        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)
        _sensor_cache[(1, 10, "TEMPERATURE", "TEMPERATURE")] = 101

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMPERATURE',
                value=25.0,
                ts=utcnow()
            ),
        ]

        # Empty result means all sensor IDs are stale → insert is skipped
        mock_fetch.return_value = []

        await process_telemetry_batch(samples)

        assert mock_execute.call_count == 0
        assert (1, 10, "TEMPERATURE", "TEMPERATURE") not in _sensor_cache


@pytest.mark.asyncio
async def test_sensor_insert_uses_on_conflict_and_caches_id():
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        tp._cache_last_update = time.time()
        _zone_cache.clear()
        _node_cache.clear()
        _sensor_cache.clear()
        _zone_greenhouse_cache.clear()

        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)
        _zone_greenhouse_cache[1] = 99

        # Query-content-based mock: respond based on what the query does,
        # not call position, because the pipeline call order can change.
        async def _smart_fetch(*args, **kwargs):
            query = str(args[0]) if args else ""
            if "ON CONFLICT" in query and "sensor" in query.lower():
                return [{'id': 101, 'zone_id': 1, 'node_id': 10, 'type': 'PH', 'label': 'ph_sensor'}]
            if "ANY($1::bigint[])" in query:
                return [{'id': 101}]
            return []
        mock_fetch.side_effect = _smart_fetch
        mock_execute.return_value = None

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='PH',
                channel='ph_sensor',
                value=6.5,
                ts=utcnow()
            ),
        ]

        await process_telemetry_batch(samples)

        # Find the sensor insert/resolve query among all fetch calls
        sensor_insert_calls = [
            call.args[0]
            for call in mock_fetch.call_args_list
            if call.args and "ON CONFLICT" in str(call.args[0]) and "sensor" in str(call.args[0]).lower()
        ]
        assert sensor_insert_calls, "Expected at least one sensor insert/resolve fetch call"
        assert "ON CONFLICT (zone_id, node_id, scope, type, label)" in sensor_insert_calls[0]
        assert (1, 10, "PH", "ph_sensor") in _sensor_cache


@pytest.mark.asyncio
async def test_sensor_fk_violation_clears_caches_and_stops_batch():
    with patch('telemetry_processing.fetch') as mock_fetch, \
         patch('telemetry_processing.execute') as mock_execute:

        tp._cache_last_update = time.time()
        _zone_cache.clear()
        _node_cache.clear()
        _sensor_cache.clear()
        _zone_greenhouse_cache.clear()

        _zone_cache[('zn-1', 'gh-1')] = 1
        _node_cache[('nd-1', 'gh-1')] = (10, 1)
        _zone_greenhouse_cache[1] = 99

        mock_fetch.side_effect = [
            [],
            Exception('insert or update on table "sensors" violates foreign key constraint "sensors_greenhouse_id_foreign"'),
        ]
        mock_execute.return_value = None

        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='PH',
                channel='ph_sensor',
                value=6.5,
                ts=utcnow()
            ),
        ]

        await process_telemetry_batch(samples)

        assert _zone_cache == {}
        assert _node_cache == {}
        assert _sensor_cache == {}
        assert _zone_greenhouse_cache == {}
        assert tp._cache_last_update == 0.0
        assert not mock_execute.called
