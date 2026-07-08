"""
Тесты для Redis queue модуля (telemetry buffering).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from common.redis_queue import (
    PopBatchResult,
    TelemetryQueue,
    TelemetryQueueItem,
    get_redis_client,
    close_redis_client,
    QUEUE_SIZE,
    QUEUE_UTILIZATION,
    update_redis_health,
    REDIS_CONNECTED,
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
        
        result = await queue.pop_batch(100)

        assert result.entries == []


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_success(mock_redis_client):
    """Тест успешного извлечения батча из очереди."""
    import json

    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        queue._pop_script = AsyncMock()

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

        queue._pop_script.return_value = [test_json]

        result = await queue.pop_batch(100)

        assert len(result.entries) == 1
        assert result.entries[0].item.node_uid == "nd-ph-1"
        assert result.entries[0].item.metric_type == "PH"
        assert result.entries[0].item.value == 6.5


@pytest.mark.asyncio
async def test_telemetry_queue_get_health_metrics(mock_redis_client):
    """Тест сбора health-метрик очереди телеметрии."""
    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client

        async def _llen_side_effect(key):
            if key == TelemetryQueue.QUEUE_KEY:
                return 100
            if key == TelemetryQueue.PROCESSING_KEY:
                return 25
            if key == TelemetryQueue.DEAD_KEY:
                return 2
            return 0

        mock_redis_client.llen.side_effect = _llen_side_effect
        mock_redis_client.lindex.return_value = None

        metrics = await queue.get_health_metrics()

        assert metrics["size"] == 100
        assert metrics["processing_size"] == 25
        assert metrics["depth"] == 125
        assert metrics["utilization"] == pytest.approx(125 / TelemetryQueue.MAX_QUEUE_SIZE)
        assert metrics["dead_list_size"] == 2
        assert QUEUE_SIZE._value.get() == 100
        assert QUEUE_UTILIZATION._value.get() == pytest.approx(125 / TelemetryQueue.MAX_QUEUE_SIZE)


def test_update_redis_health_sets_gauge():
    update_redis_health(True)
    assert REDIS_CONNECTED._value.get() == 1
    update_redis_health(False)
    assert REDIS_CONNECTED._value.get() == 0


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

        mock_redis_client.delete.assert_called_once_with(
            TelemetryQueue.QUEUE_KEY,
            TelemetryQueue.PROCESSING_KEY,
        )


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
        queue._pop_script = AsyncMock(return_value=[b"invalid json"])
        queue._move_raw_to_dead = AsyncMock(return_value=True)

        result = await queue.pop_batch(100)

        assert result.entries == []
        queue._move_raw_to_dead.assert_called_once()


@pytest.mark.asyncio
async def test_get_redis_client_connection():
    """Тест получения Redis клиента."""
    with patch('common.redis_queue.redis_async.Redis') as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_redis_class.return_value = mock_client
        
        # Сбрасываем глобальный клиент
        import common.redis_queue
        common.redis_queue._redis_client = None
        
        client = await get_redis_client()
        
        assert client is not None
        mock_client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_get_redis_client_connection_failure():
    """Тест обработки ошибки подключения к Redis."""
    with patch('common.redis_queue.redis_async.Redis') as mock_redis_class:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("Connection failed"))
        mock_redis_class.return_value = mock_client
        
        # Сбрасываем глобальный клиент
        import common.redis_queue
        common.redis_queue._redis_client = None
        
        with pytest.raises(Exception):
            await get_redis_client()


@pytest.mark.asyncio
async def test_close_redis_client(mock_redis_client):
    """Тест закрытия Redis клиента."""
    import common.redis_queue
    common.redis_queue._redis_client = mock_redis_client
    mock_redis_client.aclose = AsyncMock()
    
    await close_redis_client()
    
    mock_redis_client.aclose.assert_called_once()
    assert common.redis_queue._redis_client is None


@pytest.mark.asyncio
async def test_telemetry_queue_pop_batch_partial(mock_redis_client):
    """Тест извлечения частичного батча (меньше запрошенного)."""
    import json

    with patch('common.redis_queue.get_redis_client', return_value=mock_redis_client):
        queue = TelemetryQueue()
        queue._client = mock_redis_client
        queue._pop_script = AsyncMock()

        test_item = {
            "node_uid": "nd-ph-1",
            "metric_type": "PH",
            "value": 6.5,
            "ts": datetime.now().isoformat(),
        }
        test_json = json.dumps(test_item).encode('utf-8')
        queue._pop_script.return_value = [test_json]

        result = await queue.pop_batch(100)

        assert len(result.entries) == 1
        assert result.entries[0].item.node_uid == "nd-ph-1"


@pytest.mark.asyncio
async def test_telemetry_dead_list_replay(mock_redis_client):
    import base64
    import json

    from common.utils.time import utcnow

    inner = json.dumps({"node_uid": "nd-ph-1", "metric_type": "PH", "value": 6.5}).encode("utf-8")
    dead_payload = json.dumps(
        {
            "reason": "max_pg_retries",
            "retry": 2,
            "payload_b64": base64.b64encode(inner).decode("ascii"),
            "moved_at": utcnow().isoformat(),
        }
    ).encode("utf-8")

    mock_redis_client.lindex = AsyncMock(return_value=dead_payload)
    mock_redis_client.lpush = AsyncMock(return_value=1)
    mock_redis_client.lrem = AsyncMock(return_value=1)
    mock_redis_client.llen = AsyncMock(return_value=0)

    queue = TelemetryQueue()
    queue._client = mock_redis_client

    assert await queue.replay_dead(0) is True
    mock_redis_client.lpush.assert_awaited_once()
    mock_redis_client.lrem.assert_awaited_once()


@pytest.mark.asyncio
async def test_telemetry_dead_list_prune_expired(mock_redis_client):
    import base64
    import json
    from datetime import timedelta

    from common.utils.time import utcnow

    inner = json.dumps({"node_uid": "nd-ph-1"}).encode("utf-8")
    expired_payload = json.dumps(
        {
            "reason": "deserialize_failed",
            "retry": 0,
            "payload_b64": base64.b64encode(inner).decode("ascii"),
            "moved_at": (utcnow() - timedelta(days=8)).isoformat(),
        }
    ).encode("utf-8")
    fresh_payload = json.dumps(
        {
            "reason": "deserialize_failed",
            "retry": 0,
            "payload_b64": base64.b64encode(inner).decode("ascii"),
            "moved_at": utcnow().isoformat(),
        }
    ).encode("utf-8")

    mock_redis_client.lrange = AsyncMock(return_value=[expired_payload, fresh_payload])
    mock_redis_client.lrem = AsyncMock(return_value=1)
    mock_redis_client.llen = AsyncMock(return_value=1)

    queue = TelemetryQueue()
    queue._client = mock_redis_client

    removed = await queue.prune_expired_dead()
    assert removed == 1
    mock_redis_client.lrem.assert_awaited_once_with(queue.DEAD_KEY, 1, expired_payload)
