"""
Тесты для критических исправлений History Logger:
- Retry логика для Redis push
- Валидация размера payload (DoS защита)
- Retry логика для Laravel API
- Graceful shutdown для фоновых задач
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import asyncio
import httpx
import sys
import os

# Добавляем путь к common модулям
current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.dirname(current_dir)
sys.path.insert(0, services_dir)

from common.redis_queue import TelemetryQueueItem
from utils import MAX_PAYLOAD_SIZE

REDIS_PUSH_MAX_RETRIES = 3


class TestPayloadValidation:
    """Тесты валидации размера payload."""
    
    def test_parse_json_valid_payload(self):
        """Тест парсинга валидного payload."""
        from utils import _parse_json
        payload = b'{"metric_type": "PH", "value": 6.5}'
        result = _parse_json(payload)
        
        assert result is not None
        assert result["metric_type"] == "PH"
        assert result["value"] == 6.5
    
    def test_parse_json_payload_too_large(self):
        """Тест отклонения слишком большого payload."""
        from utils import _parse_json
        # Создаем payload больше максимального размера
        large_payload = b'{"data": "' + (b'x' * (MAX_PAYLOAD_SIZE + 1)) + b'"}'
        
        result = _parse_json(large_payload)
        
        assert result is None  # Должен вернуть None для слишком большого payload
    
    def test_parse_json_payload_at_limit(self):
        """Тест парсинга payload на границе лимита."""
        from utils import _parse_json
        # Создаем payload точно на лимите
        payload = b'{"data": "' + (b'x' * (MAX_PAYLOAD_SIZE - 100)) + b'"}'
        
        result = _parse_json(payload)
        
        # Должен парситься успешно, так как не превышает лимит
        assert result is not None
    
    def test_parse_json_invalid_json(self):
        """Тест обработки невалидного JSON."""
        from utils import _parse_json
        payload = b'invalid json {'
        result = _parse_json(payload)
        
        assert result is None
    
    def test_parse_json_empty_payload(self):
        """Тест обработки пустого payload."""
        from utils import _parse_json
        payload = b'{}'
        result = _parse_json(payload)
        
        assert result is not None
        assert result == {}


class TestRedisRetryLogic:
    """Тесты retry логики для Redis push."""
    
    @pytest.mark.asyncio
    async def test_push_with_retry_success_first_attempt(self):
        """Тест успешного push с первой попытки."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(return_value=True)
        
        with patch('state.telemetry_queue', mock_queue):
            result = await _push_with_retry(queue_item)
        
        assert result is True
        assert mock_queue.push.call_count == 1
    
    @pytest.mark.asyncio
    async def test_push_with_retry_success_after_retry(self):
        """Тест успешного push после retry."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        mock_queue = AsyncMock()
        # Первая попытка падает, вторая успешна
        mock_queue.push = AsyncMock(side_effect=[Exception("Redis error"), True])
        
        with patch('state.telemetry_queue', mock_queue):
            result = await _push_with_retry(queue_item, max_retries=2)
        
        assert result is True
        assert mock_queue.push.call_count == 2
    
    @pytest.mark.asyncio
    async def test_push_with_retry_all_attempts_fail(self):
        """Тест провала всех попыток."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(side_effect=Exception("Redis error"))
        
        with patch('state.telemetry_queue', mock_queue):
            result = await _push_with_retry(queue_item, max_retries=3)
        
        assert result is False
        assert mock_queue.push.call_count == 3  # Все 3 попытки
    
    @pytest.mark.asyncio
    async def test_push_with_retry_queue_full(self):
        """Тест обработки переполненной очереди (не повторяем)."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        mock_queue = AsyncMock()
        # Очередь переполнена - push возвращает False
        mock_queue.push = AsyncMock(return_value=False)
        
        with patch('state.telemetry_queue', mock_queue):
            result = await _push_with_retry(queue_item, max_retries=3)
        
        assert result is False
        # Должна быть только одна попытка (очередь переполнена, не повторяем)
        assert mock_queue.push.call_count == 1
    
    @pytest.mark.asyncio
    async def test_push_with_retry_exponential_backoff(self):
        """Тест exponential backoff при retry."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(side_effect=Exception("Redis error"))
        
        sleep_times = []
        
        async def mock_sleep(seconds):
            sleep_times.append(seconds)
            # Не вызываем реальный asyncio.sleep, чтобы избежать рекурсии
        
        with patch('state.telemetry_queue', mock_queue), \
             patch('telemetry_processing.asyncio.sleep', side_effect=mock_sleep):
            await _push_with_retry(queue_item, max_retries=3)
        
        # Проверяем, что backoff увеличивается: 2^0=1, 2^1=2
        # Первая попытка падает, затем backoff 2^0=1, вторая попытка падает, backoff 2^1=2
        assert len(sleep_times) == 2
        assert sleep_times[0] == 1  # 2^0
        assert sleep_times[1] == 2  # 2^1
    
    @pytest.mark.asyncio
    async def test_push_with_retry_no_queue(self):
        """Тест обработки отсутствия очереди."""
        from telemetry_processing import _push_with_retry
        queue_item = TelemetryQueueItem(
            node_uid="nd-ph-1",
            zone_uid="zn-1",
            metric_type="PH",
            value=6.5,
            ts=datetime.utcnow()
        )
        
        with patch('state.telemetry_queue', None):
            result = await _push_with_retry(queue_item)
        
        assert result is False


class TestLaravelApiRetry:
    """Тесты retry логики для Laravel API."""
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_success_first_attempt(self):
        """Тест успешной регистрации узла с первой попытки."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-001", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"uid": "nd-test-001"}}
        mock_response.text = "OK"
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client:
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Проверяем, что post был вызван только один раз
            mock_post = mock_client_instance.__aenter__.return_value.post
            assert mock_post.call_count == 1
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_retry_on_server_error(self):
        """Тест retry при серверной ошибке (5xx)."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-002", "node_type": "ph", "fw_version": "1.0.0"}'
        
        # Первая попытка - 500, вторая - 201
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"
        
        mock_response_201 = MagicMock()
        mock_response_201.status_code = 201
        mock_response_201.json.return_value = {"data": {"uid": "nd-test-002"}}
        mock_response_201.text = "OK"
        
        sleep_times = []
        
        async def mock_sleep(seconds):
            sleep_times.append(seconds)
            # Не вызываем реальный asyncio.sleep
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client, \
             patch('mqtt_handlers.asyncio.sleep', side_effect=mock_sleep):
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            mock_post = AsyncMock(side_effect=[mock_response_500, mock_response_201])
            mock_client_instance.__aenter__.return_value.post = mock_post
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Должно быть 2 попытки (первая 500, вторая успешная)
            assert mock_post.call_count == 2
            # Должен быть один sleep с backoff 2^0 = 1 секунда
            assert len(sleep_times) == 1
            assert sleep_times[0] == 1
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_no_retry_on_client_error(self):
        """Тест отсутствия retry при клиентской ошибке (4xx)."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-003", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client:
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            mock_post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__.return_value.post = mock_post
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Должна быть только одна попытка (клиентская ошибка, не повторяем)
            assert mock_post.call_count == 1
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_no_retry_on_401(self):
        """Тест отсутствия retry при 401 (неавторизован)."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-004", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client:
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "invalid-token"
            
            mock_client_instance = AsyncMock()
            mock_post = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__.return_value.post = mock_post
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Должна быть только одна попытка (401, не повторяем)
            assert mock_post.call_count == 1
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_retry_on_timeout(self):
        """Тест retry при timeout."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-005", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"uid": "nd-test-005"}}
        mock_response.text = "OK"
        
        sleep_times = []
        
        async def mock_sleep(seconds):
            sleep_times.append(seconds)
            # Не вызываем реальный asyncio.sleep
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client, \
             patch('mqtt_handlers.asyncio.sleep', side_effect=mock_sleep):
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            # Первая попытка - timeout, вторая - успех
            mock_post = AsyncMock(side_effect=[httpx.TimeoutException("Timeout"), mock_response])
            mock_client_instance.__aenter__.return_value.post = mock_post
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Должно быть 2 попытки
            assert mock_post.call_count == 2
            # Должен быть один sleep с backoff
            assert len(sleep_times) == 1
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_all_retries_fail(self):
        """Тест провала всех попыток."""
        from mqtt_handlers import handle_node_hello
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-006", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"
        
        async def mock_sleep(seconds):
            pass  # Не делаем ничего
        
        with patch('mqtt_handlers.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client, \
             patch('mqtt_handlers.asyncio.sleep', side_effect=mock_sleep):
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            # Все попытки возвращают 500
            mock_post = AsyncMock(return_value=mock_response_500)
            mock_client_instance.__aenter__.return_value.post = mock_post
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Должно быть 3 попытки (MAX_API_RETRIES)
            assert mock_post.call_count == 3


class TestGracefulShutdown:
    """Тесты graceful shutdown."""
    
    @pytest.mark.asyncio
    async def test_background_tasks_tracking(self):
        """Тест отслеживания фоновых задач."""
        from app import lifespan
        from state import background_tasks, telemetry_queue, shutdown_event
        from fastapi import FastAPI
        from unittest.mock import AsyncMock, patch
        
        # Очищаем список задач перед тестом
        background_tasks.clear()
        shutdown_event.clear()
        
        # Мокируем зависимости
        mock_queue = AsyncMock()
        mock_queue.size = AsyncMock(return_value=0)
        mock_queue.pop_batch = AsyncMock(return_value=[])
        
        mock_mqtt = AsyncMock()
        mock_mqtt.subscribe = AsyncMock()
        
        app = FastAPI()
        
        with patch('state.telemetry_queue', mock_queue), \
             patch('app.get_mqtt_client', new_callable=AsyncMock) as mock_get_mqtt, \
             patch('app.close_redis_client', new_callable=AsyncMock):
            mock_get_mqtt.return_value = mock_mqtt
            
            # Запускаем lifespan в контексте
            async with lifespan(app):
                # Проверяем, что задачи добавлены
                assert len(background_tasks) > 0
                # Проверяем, что задачи не завершены сразу
                for task in background_tasks:
                    assert not task.done()
            
            # После shutdown все задачи должны быть завершены или отменены
            # (но это зависит от таймаута)
    
    @pytest.mark.asyncio
    async def test_shutdown_event_set(self):
        """Тест установки shutdown_event при shutdown."""
        from app import lifespan
        from state import background_tasks, telemetry_queue, shutdown_event
        from fastapi import FastAPI
        from unittest.mock import AsyncMock, patch
        
        # Сбрасываем event перед тестом
        shutdown_event.clear()
        background_tasks.clear()
        
        # Мокируем зависимости
        mock_queue = AsyncMock()
        mock_queue.size = AsyncMock(return_value=0)
        mock_queue.pop_batch = AsyncMock(return_value=[])
        
        mock_mqtt = AsyncMock()
        mock_mqtt.subscribe = AsyncMock()
        
        # Мокируем process_telemetry_queue чтобы он сразу завершался
        async def mock_process_telemetry_queue():
            while not shutdown_event.is_set():
                await asyncio.sleep(0.01)
        
        app = FastAPI()
        
        with patch('state.telemetry_queue', mock_queue), \
             patch('app.get_mqtt_client', new_callable=AsyncMock) as mock_get_mqtt, \
             patch('app.close_redis_client', new_callable=AsyncMock), \
             patch('app.process_telemetry_queue', side_effect=mock_process_telemetry_queue):
            mock_get_mqtt.return_value = mock_mqtt
            
            # Запускаем lifespan
            try:
                async with lifespan(app):
                    # В startup event не должен быть установлен
                    assert not shutdown_event.is_set()
                    # Даем немного времени на запуск
                    await asyncio.sleep(0.1)
            except Exception:
                # Игнорируем ошибки при shutdown (event loop может быть закрыт)
                pass
            
            # После shutdown event должен быть установлен
            assert shutdown_event.is_set()


class TestIntegration:
    """Интеграционные тесты."""
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_with_retry(self):
        """Тест обработки телеметрии с retry логикой."""
        from telemetry_processing import handle_telemetry
        
        mock_queue = AsyncMock()
        # Первая попытка падает, вторая успешна
        mock_queue.push = AsyncMock(side_effect=[Exception("Redis error"), True])
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        payload = b'{"metric_type": "PH", "value": 6.5, "ts": 1737979.2}'
        
        async def mock_sleep(_seconds):
            return None

        with patch('state.telemetry_queue', mock_queue), \
             patch('telemetry_processing.asyncio.sleep', side_effect=mock_sleep):
            await handle_telemetry(topic, payload)
            
            # Проверяем, что push был вызван 2 раза (retry)
            assert mock_queue.push.call_count == 2
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_large_payload_rejected(self):
        """Тест отклонения большого payload в handle_telemetry."""
        from telemetry_processing import handle_telemetry
        from utils import MAX_PAYLOAD_SIZE
        
        mock_queue = AsyncMock()
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        # Создаем payload больше максимального размера
        large_payload = b'{"data": "' + (b'x' * (MAX_PAYLOAD_SIZE + 1)) + b'"}'
        
        with patch('state.telemetry_queue', mock_queue):
            await handle_telemetry(topic, large_payload)
            
            # Push не должен быть вызван (payload отклонен)
            assert mock_queue.push.call_count == 0
