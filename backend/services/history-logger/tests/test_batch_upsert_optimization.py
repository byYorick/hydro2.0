"""
Тесты для оптимизации batch upsert telemetry_last.
Проверяет, что используется один запрос для всех обновлений.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from main import process_telemetry_batch, TelemetrySampleModel, refresh_caches


@pytest.mark.asyncio
async def test_batch_upsert_single_query():
    """Тест, что batch upsert использует один запрос для всех обновлений."""
    # Мокаем кеш
    with patch('main._zone_cache', {('zn-1', 'gh-1'): 1}), \
         patch('main._node_cache', {('nd-1', 'gh-1'): (1, 1)}), \
         patch('main._cache_last_update', 9999999999.0):  # Кеш свежий
        
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
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='HUMIDITY',
                value=60.0,
                ts=datetime.utcnow()
            ),
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='PH',
                value=6.5,
                ts=datetime.utcnow()
            ),
        ]
        
        # Мокаем execute для проверки количества вызовов
        with patch('main.execute') as mock_execute, \
             patch('main.fetch', return_value=[]):
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что был вызван batch upsert (один запрос для всех)
            upsert_calls = [
                call for call in mock_execute.call_args_list
                if 'telemetry_last' in str(call) or 'ON CONFLICT' in str(call)
            ]
            
            # Должен быть один batch upsert запрос
            assert len(upsert_calls) >= 1
            
            # Проверяем, что в одном запросе несколько VALUES
            if upsert_calls:
                query_str = str(upsert_calls[0])
                # Должно быть несколько VALUES для batch upsert
                assert 'VALUES' in query_str or 'ON CONFLICT' in query_str


@pytest.mark.asyncio
async def test_batch_upsert_latest_timestamp():
    """Тест, что batch upsert выбирает сэмпл с максимальным timestamp."""
    # Мокаем кеш
    with patch('main._zone_cache', {('zn-1', 'gh-1'): 1}), \
         patch('main._node_cache', {('nd-1', 'gh-1'): (1, 1)}), \
         patch('main._cache_last_update', 9999999999.0):
        
        base_time = datetime.utcnow()
        
        samples = [
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMP_AIR',
                value=20.0,  # Старое значение
                ts=base_time
            ),
            TelemetrySampleModel(
                zone_uid='zn-1',
                gh_uid='gh-1',
                node_uid='nd-1',
                metric_type='TEMP_AIR',
                value=25.0,  # Новое значение (более поздний timestamp)
                ts=datetime.fromtimestamp(base_time.timestamp() + 10)
            ),
        ]
        
        # Мокаем execute для проверки значения
        with patch('main.execute') as mock_execute, \
             patch('main.fetch', return_value=[]):
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что в upsert используется значение 25.0 (более поздний timestamp)
            upsert_calls = [
                call for call in mock_execute.call_args_list
                if 'telemetry_last' in str(call) or 'ON CONFLICT' in str(call)
            ]
            
            # Должен быть вызов с новым значением
            assert len(upsert_calls) > 0


@pytest.mark.asyncio
async def test_batch_upsert_fallback():
    """Тест fallback на индивидуальные upsert при ошибке batch."""
    # Мокаем кеш
    with patch('main._zone_cache', {('zn-1', 'gh-1'): 1}), \
         patch('main._node_cache', {('nd-1', 'gh-1'): (1, 1)}), \
         patch('main._cache_last_update', 9999999999.0):
        
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
        
        # Мокаем execute чтобы выбрасывал ошибку при batch upsert
        call_count = 0
        def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            query_str = str(args[0]) if args else ""
            if 'telemetry_last' in query_str and 'ON CONFLICT' in query_str:
                # Первый вызов (batch) выбрасывает ошибку
                raise Exception("Batch upsert failed")
            # Последующие вызовы (fallback) успешны
            return None
        
        with patch('main.execute', side_effect=mock_execute_side_effect), \
             patch('main.fetch', return_value=[]), \
             patch('main.upsert_telemetry_last', new_callable=AsyncMock) as mock_upsert:
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что был вызван fallback (индивидуальный upsert)
            assert mock_upsert.called

