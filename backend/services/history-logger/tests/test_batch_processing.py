"""
Тесты для batch processing в history-logger.
Проверяет кеширование, batch resolve, batch insert и batch upsert.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from telemetry_processing import (
    _node_cache,
    _zone_cache,
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
        
        await process_telemetry_batch(samples)
        
        # Проверяем, что был вызван batch upsert (один запрос для всех обновлений)
        upsert_calls = [call for call in mock_execute.call_args_list 
                       if 'telemetry_last' in str(call)]
        assert len(upsert_calls) > 0
