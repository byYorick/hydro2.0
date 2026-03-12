"""
Тесты для Redis queue модуля (telemetry buffering).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from common.redis_queue import (
    TelemetryQueue,
    TelemetryQueueItem,
    get_redis_client,
    close_redis_client,
)


@pytest.fixture
def mock_redis_client():
    """Создает мок Redis клиента."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.llen = AsyncMock(return_value=0)
    client.rpush = AsyncMock(return_value=1)
    client.lpop = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    client.pipeline = MagicMock(return_value=AsyncMock())
    return client


@pytest.fixture
def telemetry_queue_item():
    """Создает тестовый элемент очереди."""
    return TelemetryQueueItem(
        node_uid="nd-ph-1",
        zone_uid="zn-1",
        metric_type="PH",
        value=6.5,
        ts=datetime.now(),
        raw={"sensor": "ph"},
        channel="ph_sensor"
    )


@pytest.mark.asyncio
async def test_telemetry_queue_push_success(mock_redis_client, telemetry_queue_item):
    """Тест успешного добавления элемента в очередь."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        mock_redis_client.llen.return_value = 100  # Очередь не переполнена
        
        result = await queue.push(telemetry_queue_item)
        
        assert result is True
        mock_redis_client.rpush.assert_called_once()
        # Проверяем, что был вызван rpush с правильным ключом
        call_args = mock_redis_client.rpush.call_args
        assert call_args[0][0] == TelemetryQueue.QUEUE_KEY


@pytest.mark.asyncio
async def test_telemetry_queue_push_queue_full(mock_redis_client, telemetry_queue_item):
    """Тест добавления в переполненную очередь."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        # Очередь переполнена
        mock_redis_client.llen.return_value = TelemetryQueue.MAX_QUEUE_SIZE + 1
        
        result = await queue.push(telemetry_queue_item)
        
        assert result is False
        mock_redis_client.rpush.assert_not_called()


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_empty(mock_redis_client):
    """Тест извлечения из пустой очереди."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        mock_redis_client.llen.return_value = 0
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[])
        mock_redis_client.pipeline.return_value = mock_pipeline
        
        items = await queue.pop_batch(100)
        
        assert items == []


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_success(mock_redis_client):
    """Тест успешного извлечения батча из очереди."""
    import json
    
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        # Создаем тестовые данные
        test_item = {
            "node_uid": "nd-ph-1",
            "zone_uid": "zn-1",
            "metric_type": "PH",
            "value": 6.5,
            "ts": datetime.now().isoformat(),
            "raw": {"sensor": "ph"},
            "channel": "ph_sensor"
        }
        test_json = json.dumps(test_item).encode('utf-8')
        
        mock_redis_client.llen.return_value = 1
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[test_json])
        mock_redis_client.pipeline.return_value = mock_pipeline
        
        items = await queue.pop_batch(100)
        
        assert len(items) == 1
        assert items[0].node_uid == "nd-ph-1"
        assert items[0].metric_type == "PH"
        assert items[0].value == 6.5


@pytest.mark.asyncio
async def test_telemetry_queue_size(mock_redis_client):
    """Тест получения размера очереди."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        mock_redis_client.llen.return_value = 42
        
        size = await queue.size()
        
        assert size == 42
        mock_redis_client.llen.assert_called_once_with(TelemetryQueue.QUEUE_KEY)


@pytest.mark.asyncio
async def test_telemetry_queue_clear(mock_redis_client):
    """Тест очистки очереди."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        await queue.clear()
        
        mock_redis_client.delete.assert_called_once_with(TelemetryQueue.QUEUE_KEY)


@pytest.mark.asyncio
async def test_telemetry_queue_item_serialization(telemetry_queue_item):
    """Тест сериализации элемента очереди."""
    item_dict = telemetry_queue_item.dict()
    
    assert item_dict["node_uid"] == "nd-ph-1"
    assert item_dict["zone_uid"] == "zn-1"
    assert item_dict["metric_type"] == "PH"
    assert item_dict["value"] == 6.5
    assert "ts" in item_dict


@pytest.mark.asyncio
async def test_telemetry_queue_push_redis_error(mock_redis_client, telemetry_queue_item):
    """Тест обработки ошибки Redis при добавлении."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        mock_redis_client.llen.return_value = 100
        mock_redis_client.rpush.side_effect = Exception("Redis connection error")
        
        result = await queue.push(telemetry_queue_item)
        
        assert result is False


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_invalid_json(mock_redis_client):
    """Тест обработки невалидного JSON при извлечении."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        mock_redis_client.llen.return_value = 1
        mock_pipeline = AsyncMock()
        # Возвращаем невалидный JSON
        mock_pipeline.execute = AsyncMock(return_value=[b"invalid json"])
        mock_redis_client.pipeline.return_value = mock_pipeline
        
        items = await queue.pop_batch(100)
        
        # Невалидные элементы должны быть пропущены
        assert items == []


@pytest.mark.asyncio
async def test_get_redis_client_connection():
    """Тест получения Redis клиента."""
    with patch('common.redis_queue.redis.Redis') as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_redis_class.return_value = mock_client
        
        client = await get_redis_client()
        
        assert client is not None
        mock_client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_get_redis_client_connection_failure():
    """Тест обработки ошибки подключения к Redis."""
    with patch('common.redis_queue.redis.Redis') as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
        mock_redis_class.return_value = mock_client
        
        with pytest.raises(Exception):
            await get_redis_client()


@pytest.mark.asyncio
async def test_close_redis_client(mock_redis_client):
    """Тест закрытия Redis клиента."""
    with patch('common.redis_queue._redis_client', mock_redis_client):
        await close_redis_client()
        
        mock_redis_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_partial(mock_redis_client):
    """Тест извлечения частичного батча (меньше запрошенного)."""
    import json
    
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        
        # Создаем тестовые данные
        test_item = {
            "node_uid": "nd-ph-1",
            "metric_type": "PH",
            "value": 6.5,
            "ts": datetime.now().isoformat(),
        }
        test_json = json.dumps(test_item).encode('utf-8')
        
        # В очереди только 1 элемент, запрашиваем 100
        mock_redis_client.llen.return_value = 1
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[test_json, None])  # Второй lpop вернет None
        mock_redis_client.pipeline.return_value = mock_pipeline
        
        items = await queue.pop_batch(100)
        
        assert len(items) == 1
        assert items[0].node_uid == "nd-ph-1"

