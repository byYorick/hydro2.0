"""
Тесты для метрик overflow в history-logger.
Проверяет метрики queue_size, dropped, overflow alerts.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from common.redis_queue import TelemetryQueue, TelemetryQueueItem


@pytest.mark.asyncio
async def test_queue_size_metric():
    """Тест метрики размера очереди."""
    queue = TelemetryQueue()
    
    with patch('common.redis_queue.get_redis_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.llen.return_value = 100
        
        # Мокаем QUEUE_SIZE
        with patch('common.redis_queue.QUEUE_SIZE') as mock_gauge:
            await queue.push(TelemetryQueueItem(
                node_uid="nd-1",
                metric_type="TEMPERATURE",
                value=25.0
            ))
            
            # Проверяем, что метрика была обновлена
            assert mock_gauge.set.called
            mock_gauge.set.assert_called_with(100)


@pytest.mark.asyncio
async def test_queue_overflow_dropped():
    """Тест метрики dropped при overflow."""
    queue = TelemetryQueue()
    
    with patch('common.redis_queue.get_redis_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.llen.return_value = TelemetryQueue.MAX_QUEUE_SIZE
        
        # Мокаем QUEUE_DROPPED
        with patch('common.redis_queue.QUEUE_DROPPED') as mock_dropped:
            result = await queue.push(TelemetryQueueItem(
                node_uid="nd-1",
                metric_type="TEMPERATURE",
                value=25.0
            ))
            
            # Проверяем, что сообщение было отклонено
            assert result is False
            # Проверяем, что метрика была увеличена
            assert mock_dropped.labels.called


@pytest.mark.asyncio
async def test_queue_overflow_alert():
    """Тест алерта при overflow."""
    queue = TelemetryQueue()
    
    with patch('common.redis_queue.get_redis_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        mock_client.llen.return_value = int(TelemetryQueue.MAX_QUEUE_SIZE * 0.96)
        mock_client.exists.return_value = False  # Throttle не активен
        
        # Мокаем QUEUE_OVERFLOW_ALERTS
        with patch('common.redis_queue.QUEUE_OVERFLOW_ALERTS') as mock_alerts:
            with patch('common.redis_queue.create_zone_event', new_callable=AsyncMock):
                result = await queue.push(TelemetryQueueItem(
                    node_uid="nd-1",
                    metric_type="TEMPERATURE",
                    value=25.0
                ))
                
                # Проверяем, что алерт был отправлен
                assert mock_alerts.inc.called


@pytest.mark.asyncio
async def test_backpressure_sampling():
    """Тест backpressure sampling при высокой загрузке очереди."""
    queue = TelemetryQueue()
    
    with patch('common.redis_queue.get_redis_client') as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        # 96% заполнения - должно применяться sampling
        mock_client.llen.return_value = int(TelemetryQueue.MAX_QUEUE_SIZE * 0.96)
        
        # Мокаем random для детерминированного теста
        with patch('common.redis_queue.random.random', return_value=0.9):  # > 0.8, должно быть отклонено
            with patch('common.redis_queue.QUEUE_DROPPED') as mock_dropped:
                result = await queue.push(TelemetryQueueItem(
                    node_uid="nd-1",
                    metric_type="TEMPERATURE",
                    value=25.0
                ))
                
                # Проверяем, что сообщение было отклонено из-за backpressure
                assert result is False
                assert mock_dropped.labels.called
