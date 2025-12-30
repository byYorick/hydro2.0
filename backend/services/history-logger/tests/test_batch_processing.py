"""
Тесты для batch processing в history-logger.
Проверяет кеширование, batch resolve, batch insert и batch upsert.
"""
import time
from datetime import datetime
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
                metric_type='TEMP_AIR',
                value=25.0,
                ts=datetime.utcnow()
            ),
            TelemetrySampleModel(
                zone_uid='zn-2',
                gh_uid='gh-1',
                node_uid='nd-2',
                metric_type='HUMIDITY',
                value=60.0,
                ts=datetime.utcnow()
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
        
        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMP_AIR',
                value=25.0,
                ts=datetime.utcnow()
            ),
        ]

        _sensor_cache.clear()
        _sensor_cache[(1, None, "TEMPERATURE", "TEMP_AIR")] = 101
        
        await process_telemetry_batch(samples)
        
        # Проверяем, что был вызван batch upsert (один запрос для всех обновлений)
        upsert_calls = [call for call in mock_execute.call_args_list 
                       if 'telemetry_last' in str(call)]
        assert len(upsert_calls) > 0


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

        mock_fetch.side_effect = [
            [],
            [{'id': 101, 'zone_id': 1, 'node_id': 10, 'type': 'PH', 'label': 'ph_sensor'}],
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
                ts=datetime.utcnow()
            ),
        ]

        await process_telemetry_batch(samples)

        assert len(mock_fetch.call_args_list) >= 2
        insert_query = mock_fetch.call_args_list[1][0][0]
        assert "ON CONFLICT (zone_id, node_id, scope, type, label)" in insert_query
        assert (1, 10, "PH", "ph_sensor") in _sensor_cache
