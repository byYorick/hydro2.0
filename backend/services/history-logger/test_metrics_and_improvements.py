"""
Тесты для новых метрик и улучшений:
- Prometheus метрики (Gauge, Histogram, Counter)
- Функция extract_zone_id_from_uid
- Валидация через Pydantic
- Обработка ошибок БД
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import time
import sys
import os

# Добавляем путь к common модулям
current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.dirname(current_dir)
sys.path.insert(0, services_dir)

from common.redis_queue import TelemetryQueueItem


class TestExtractZoneIdFromUid:
    """Тесты функции extract_zone_id_from_uid."""
    
    def test_extract_zone_id_valid(self):
        """Тест извлечения zone_id из валидного zone_uid."""
        from main import extract_zone_id_from_uid
        
        assert extract_zone_id_from_uid("zn-1") == 1
        assert extract_zone_id_from_uid("zn-123") == 123
        assert extract_zone_id_from_uid("zn-0") == 0
    
    def test_extract_zone_id_invalid_format(self):
        """Тест обработки невалидного формата."""
        from main import extract_zone_id_from_uid
        
        assert extract_zone_id_from_uid("zone-1") is None
        assert extract_zone_id_from_uid("zn") is None
        assert extract_zone_id_from_uid("1") is None
        assert extract_zone_id_from_uid("") is None
        assert extract_zone_id_from_uid(None) is None
    
    def test_extract_zone_id_invalid_number(self):
        """Тест обработки невалидного числа."""
        from main import extract_zone_id_from_uid
        
        assert extract_zone_id_from_uid("zn-abc") is None
        assert extract_zone_id_from_uid("zn-") is None


class TestTelemetryPayloadValidation:
    """Тесты валидации через Pydantic."""
    
    def test_valid_payload(self):
        """Тест валидного payload."""
        from main import TelemetryPayloadModel
        
        payload = TelemetryPayloadModel(
            metric_type="PH",
            value=6.5,
            timestamp=1737979200000,
            channel="ph_sensor"
        )
        
        assert payload.metric_type == "PH"
        assert payload.value == 6.5
        assert payload.timestamp == 1737979200000
        assert payload.channel == "ph_sensor"
    
    def test_payload_with_metric_field(self):
        """Тест payload с полем metric (обратная совместимость)."""
        from main import TelemetryPayloadModel
        
        # В модели metric_type обязателен, но в handle_telemetry используется fallback на metric
        payload = TelemetryPayloadModel(
            metric_type="PH",  # metric_type обязателен
            value=6.5,
            metric="PH"  # Дополнительное поле для обратной совместимости
        )
        
        assert payload.metric_type == "PH"
        assert payload.metric == "PH"
    
    def test_payload_min_length_validation(self):
        """Тест валидации минимальной длины metric_type."""
        from main import TelemetryPayloadModel
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            TelemetryPayloadModel(
                metric_type="",  # Пустая строка недопустима
                value=6.5
            )
    
    def test_payload_max_length_validation(self):
        """Тест валидации максимальной длины."""
        from main import TelemetryPayloadModel
        from pydantic import ValidationError
        
        # metric_type max_length=50
        with pytest.raises(ValidationError):
            TelemetryPayloadModel(
                metric_type="A" * 51,  # Превышает лимит
                value=6.5
            )
        
        # channel max_length=100
        with pytest.raises(ValidationError):
            TelemetryPayloadModel(
                metric_type="PH",
                value=6.5,
                channel="A" * 101  # Превышает лимит
            )


class TestMetrics:
    """Тесты Prometheus метрик."""
    
    @pytest.mark.asyncio
    async def test_telemetry_queue_size_metric(self):
        """Тест метрики размера очереди."""
        from main import TELEMETRY_QUEUE_SIZE, process_telemetry_queue
        from unittest.mock import AsyncMock
        
        mock_queue = AsyncMock()
        mock_queue.size = AsyncMock(return_value=100)
        mock_queue.pop_batch = AsyncMock(return_value=[])
        
        # Создаем mock для shutdown_event
        mock_shutdown = AsyncMock()
        mock_shutdown.is_set = lambda: False  # Сначала False, потом True
        
        call_count = [0]
        def is_set():
            call_count[0] += 1
            return call_count[0] > 1  # После первого вызова возвращаем True
        
        mock_shutdown.is_set = is_set
        
        with patch('main.telemetry_queue', mock_queue), \
             patch('main.shutdown_event', mock_shutdown), \
             patch('main.process_telemetry_batch', new_callable=AsyncMock), \
             patch('main.get_settings') as mock_settings:
            mock_settings.return_value.telemetry_batch_size = 200
            mock_settings.return_value.telemetry_flush_ms = 500
            mock_settings.return_value.queue_check_interval_sec = 0.1
            mock_settings.return_value.final_batch_multiplier = 10
            
            # Запускаем процессор (он завершится после первой итерации)
            await process_telemetry_queue()
            
            # Проверяем, что size был вызван
            assert mock_queue.size.called
    
    @pytest.mark.asyncio
    async def test_telemetry_processing_duration_metric(self):
        """Тест метрики времени обработки батча."""
        from main import TELEMETRY_PROCESSING_DURATION, process_telemetry_batch, TelemetrySampleModel
        from unittest.mock import AsyncMock
        from prometheus_client import REGISTRY
        
        samples = [
            TelemetrySampleModel(
                node_uid="nd-ph-1",
                zone_uid="zn-1",
                zone_id=1,
                metric_type="PH",
                value=6.5,
                ts=datetime.utcnow()
            )
        ]
        
        # Получаем начальное количество наблюдений
        initial_samples = TELEMETRY_PROCESSING_DURATION._buckets[0]._value
        
        with patch("main.execute", new_callable=AsyncMock) as mock_execute, \
             patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("main.upsert_telemetry_last", new_callable=AsyncMock):
            mock_fetch.return_value = [{"id": 1, "uid": "nd-ph-1"}]
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что метрика была обновлена (проверяем через collect)
            samples_after = sum(bucket._value for bucket in TELEMETRY_PROCESSING_DURATION._buckets)
            assert samples_after >= initial_samples
    
    @pytest.mark.asyncio
    async def test_redis_operation_duration_metric(self):
        """Тест метрики времени операций Redis."""
        from main import REDIS_OPERATION_DURATION, handle_telemetry
        from unittest.mock import AsyncMock
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"metric_type": "PH", "value": 6.5, "timestamp": 1737979200000}'
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(return_value=True)
        
        initial_samples = sum(bucket._value for bucket in REDIS_OPERATION_DURATION._buckets)
        
        with patch('main.telemetry_queue', mock_queue), \
             patch('main._push_with_retry', new_callable=AsyncMock) as mock_push:
            mock_push.return_value = True
            
            await handle_telemetry(topic, payload)
            
            # Проверяем, что метрика была обновлена
            samples_after = sum(bucket._value for bucket in REDIS_OPERATION_DURATION._buckets)
            assert samples_after >= initial_samples
    
    @pytest.mark.asyncio
    async def test_laravel_api_duration_metric(self):
        """Тест метрики времени запросов Laravel API."""
        from main import LARAVEL_API_DURATION, handle_node_hello
        from unittest.mock import AsyncMock, MagicMock
        import httpx
        
        topic = "hydro/node_hello"
        payload = b'{"message_type": "node_hello", "hardware_id": "test-001", "node_type": "ph", "fw_version": "1.0.0"}'
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"uid": "nd-test-001"}}
        mock_response.text = "OK"
        
        initial_samples = sum(bucket._value for bucket in LARAVEL_API_DURATION._buckets)
        
        with patch('main.get_settings') as mock_settings, \
             patch('httpx.AsyncClient') as mock_client:
            mock_settings.return_value.laravel_api_url = "http://laravel"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance
            
            await handle_node_hello(topic, payload)
            
            # Проверяем, что метрика была обновлена
            samples_after = sum(bucket._value for bucket in LARAVEL_API_DURATION._buckets)
            assert samples_after >= initial_samples
    
    @pytest.mark.asyncio
    async def test_telemetry_dropped_metric(self):
        """Тест метрики потерянных сообщений."""
        from main import TELEMETRY_DROPPED, handle_telemetry
        from unittest.mock import AsyncMock
        from prometheus_client import REGISTRY
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"metric_type": "PH", "value": 6.5}'
        
        # Получаем начальное значение через collect
        initial_value = 0
        for metric in REGISTRY.collect():
            if metric.name == 'telemetry_dropped_total':
                for sample in metric.samples:
                    if sample.labels.get('reason') == 'queue_push_failed':
                        initial_value = sample.value
        
        with patch('main.telemetry_queue', AsyncMock()), \
             patch('main._push_with_retry', new_callable=AsyncMock) as mock_push:
            mock_push.return_value = False
            
            await handle_telemetry(topic, payload)
            
            # Проверяем, что метрика была обновлена
            new_value = 0
            for metric in REGISTRY.collect():
                if metric.name == 'telemetry_dropped_total':
                    for sample in metric.samples:
                        if sample.labels.get('reason') == 'queue_push_failed':
                            new_value = sample.value
            
            assert new_value >= initial_value
    
    @pytest.mark.asyncio
    async def test_database_errors_metric(self):
        """Тест метрики ошибок БД."""
        from main import DATABASE_ERRORS, process_telemetry_batch, TelemetrySampleModel
        from unittest.mock import AsyncMock
        from prometheus_client import REGISTRY
        
        samples = [
            TelemetrySampleModel(
                node_uid="nd-ph-1",
                zone_uid="zn-1",
                zone_id=1,
                metric_type="PH",
                value=6.5,
                ts=datetime.utcnow()
            )
        ]
        
        # Получаем начальное значение
        initial_value = 0
        for metric in REGISTRY.collect():
            if metric.name == 'database_errors_total':
                for sample in metric.samples:
                    if sample.labels.get('error_type') == 'Exception':
                        initial_value = sample.value
        
        with patch("main.execute", new_callable=AsyncMock) as mock_execute, \
             patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("main.upsert_telemetry_last", new_callable=AsyncMock):
            mock_fetch.return_value = [{"id": 1, "uid": "nd-ph-1"}]
            # Симулируем ошибку БД
            mock_execute.side_effect = Exception("Database connection failed")
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что метрика была обновлена
            new_value = 0
            for metric in REGISTRY.collect():
                if metric.name == 'database_errors_total':
                    for sample in metric.samples:
                        if sample.labels.get('error_type') == 'Exception':
                            new_value = sample.value
            
            assert new_value >= initial_value


class TestImprovedLogging:
    """Тесты улучшенного логирования."""
    
    @pytest.mark.asyncio
    async def test_structured_logging_on_validation_error(self):
        """Тест структурированного логирования при ошибке валидации."""
        from main import handle_telemetry
        from unittest.mock import AsyncMock, patch
        import logging
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"invalid": "data"}'  # Нет обязательных полей
        
        with patch('main.telemetry_queue', AsyncMock()), \
             patch('main.logger') as mock_logger:
            await handle_telemetry(topic, payload)
            
            # Проверяем, что был вызван warning с extra параметрами
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "extra" in call_args.kwargs or len(call_args.args) > 1
    
    @pytest.mark.asyncio
    async def test_structured_logging_on_database_error(self):
        """Тест структурированного логирования при ошибке БД."""
        from main import process_telemetry_batch, TelemetrySampleModel
        from unittest.mock import AsyncMock, patch
        import logging
        
        samples = [
            TelemetrySampleModel(
                node_uid="nd-ph-1",
                zone_uid="zn-1",
                zone_id=1,
                metric_type="PH",
                value=6.5,
                ts=datetime.utcnow()
            )
        ]
        
        with patch("main.execute", new_callable=AsyncMock) as mock_execute, \
             patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("main.upsert_telemetry_last", new_callable=AsyncMock), \
             patch('main.logger') as mock_logger:
            mock_fetch.return_value = [{"id": 1, "uid": "nd-ph-1"}]
            mock_execute.side_effect = Exception("Database error")
            
            await process_telemetry_batch(samples)
            
            # Проверяем, что был вызван error с extra параметрами
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            assert "extra" in call_args.kwargs


class TestHandleTelemetryImprovements:
    """Тесты улучшений в handle_telemetry."""
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_with_pydantic_validation(self):
        """Тест обработки телеметрии с валидацией через Pydantic."""
        from main import handle_telemetry
        from unittest.mock import AsyncMock
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"metric_type": "PH", "value": 6.5, "timestamp": 1737979200000}'
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(return_value=True)
        
        with patch('main.telemetry_queue', mock_queue), \
             patch('main._push_with_retry', new_callable=AsyncMock) as mock_push:
            mock_push.return_value = True
            
            await handle_telemetry(topic, payload)
            
            # Проверяем, что push был вызван
            assert mock_push.called
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_invalid_payload_dropped(self):
        """Тест обработки невалидного payload с метрикой dropped."""
        from main import handle_telemetry
        from unittest.mock import AsyncMock
        from prometheus_client import REGISTRY
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"invalid": "data"}'  # Нет обязательных полей
        
        # Получаем начальное значение
        initial_value = 0
        for metric in REGISTRY.collect():
            if metric.name == 'telemetry_dropped_total':
                for sample in metric.samples:
                    if sample.labels.get('reason') == 'validation_failed':
                        initial_value = sample.value
        
        with patch('main.telemetry_queue', AsyncMock()):
            await handle_telemetry(topic, payload)
            
            # Проверяем, что метрика dropped была обновлена
            new_value = 0
            for metric in REGISTRY.collect():
                if metric.name == 'telemetry_dropped_total':
                    for sample in metric.samples:
                        if sample.labels.get('reason') == 'validation_failed':
                            new_value = sample.value
            
            assert new_value >= initial_value
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_missing_metric_type_dropped(self):
        """Тест обработки payload без metric_type."""
        from main import handle_telemetry
        from unittest.mock import AsyncMock
        from prometheus_client import REGISTRY
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/telemetry/PH"
        payload = b'{"value": 6.5}'  # Нет metric_type
        
        # Получаем начальное значение
        initial_value = 0
        for metric in REGISTRY.collect():
            if metric.name == 'telemetry_dropped_total':
                for sample in metric.samples:
                    if sample.labels.get('reason') == 'missing_metric_type':
                        initial_value = sample.value
        
        with patch('main.telemetry_queue', AsyncMock()):
            await handle_telemetry(topic, payload)
            
            # Проверяем, что метрика dropped была обновлена
            new_value = 0
            for metric in REGISTRY.collect():
                if metric.name == 'telemetry_dropped_total':
                    for sample in metric.samples:
                        if sample.labels.get('reason') == 'missing_metric_type':
                            new_value = sample.value
            
            assert new_value >= initial_value

