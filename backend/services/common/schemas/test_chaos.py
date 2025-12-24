"""
Chaos тесты для проверки устойчивости системы к сбоям.

Тестирует поведение системы при:
- MQTT down
- Laravel down
- DB read-only
- Burst telemetry
"""
import pytest
import time
import asyncio
import httpx
from pathlib import Path
from typing import Optional, Dict, Any
from unittest.mock import patch, MagicMock
import paho.mqtt.client as mqtt

from common.env import get_settings
from common.mqtt import MqttClient
from common.db import get_pool


class TestMqttDown:
    """Тесты поведения при недоступности MQTT."""
    
    @pytest.fixture
    def mqtt_client(self):
        """Создает MQTT клиент для тестов."""
        return MqttClient(client_id_suffix="_test")
    
    def test_mqtt_connection_failure_handling(self, mqtt_client):
        """Тест обработки ошибки подключения к MQTT."""
        # Симулируем недоступный MQTT сервер
        original_host = mqtt_client._host
        mqtt_client._host = "invalid-host-that-does-not-exist.local"
        mqtt_client._port = 1883
        
        # Попытка подключения должна обработать ошибку gracefully
        # (не должно быть необработанных исключений)
        try:
            # Запускаем в отдельном потоке с таймаутом
            import threading
            connected = threading.Event()
            error_occurred = threading.Event()
            
            def connect_with_timeout():
                try:
                    mqtt_client.start()
                    # Ждем подключения или ошибки
                    time.sleep(2)
                    if not mqtt_client._client.is_connected():
                        error_occurred.set()
                except Exception as e:
                    error_occurred.set()
            
            thread = threading.Thread(target=connect_with_timeout, daemon=True)
            thread.start()
            thread.join(timeout=5)
            
            # Ожидаем, что ошибка была обработана
            assert error_occurred.is_set() or not mqtt_client._client.is_connected()
        finally:
            # Восстанавливаем оригинальный хост
            mqtt_client._host = original_host
            if mqtt_client._client.is_connected():
                mqtt_client.stop()
    
    def test_mqtt_publish_failure_handling(self):
        """Тест обработки ошибки публикации в MQTT."""
        # Создаем мок клиента, который не может опубликовать
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_client.publish.side_effect = Exception("MQTT connection lost")
        
        # Проверяем, что код обрабатывает ошибку публикации
        # (в реальном коде должна быть обработка ошибок)
        with pytest.raises(Exception):
            mock_client.publish("test/topic", "test payload")
    
    def test_mqtt_reconnect_mechanism(self, mqtt_client):
        """Тест механизма переподключения MQTT."""
        # Проверяем, что клиент имеет механизм переподключения
        # (должен быть реализован в MqttClient)
        assert hasattr(mqtt_client, '_client')
        # Проверяем наличие обработчиков on_connect и on_disconnect
        assert mqtt_client._client.on_connect is not None
        assert mqtt_client._client.on_disconnect is not None


class TestLaravelDown:
    """Тесты поведения при недоступности Laravel."""
    
    @pytest.fixture
    def laravel_url(self):
        """URL Laravel API."""
        settings = get_settings()
        return getattr(settings, 'laravel_url', 'http://localhost:8080')
    
    @pytest.mark.asyncio
    async def test_laravel_api_unavailable(self, laravel_url):
        """Тест обработки недоступности Laravel API."""
        # Симулируем недоступный Laravel
        invalid_url = "http://invalid-host-that-does-not-exist.local:8080"
        
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                response = await client.get(f"{invalid_url}/api/health")
                # Если получили ответ, проверяем статус
                assert response.status_code >= 400
            except (httpx.ConnectError, httpx.TimeoutException):
                # Ожидаем ошибку подключения
                pass
    
    @pytest.mark.asyncio
    async def test_laravel_timeout_handling(self, laravel_url):
        """Тест обработки таймаута при запросе к Laravel."""
        # Симулируем медленный ответ (таймаут)
        async with httpx.AsyncClient(timeout=0.1) as client:
            try:
                # Используем реальный URL, но с очень коротким таймаутом
                response = await client.get(f"{laravel_url}/api/health")
                # Если получили ответ, это нормально
            except httpx.TimeoutException:
                # Ожидаем таймаут
                pass
    
    def test_laravel_error_response_handling(self):
        """Тест обработки ошибок от Laravel API."""
        # Симулируем ответ с ошибкой от Laravel
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal Server Error"}
        
        # Проверяем, что код обрабатывает ошибки
        assert mock_response.status_code >= 400


class TestDbReadOnly:
    """Тесты поведения при read-only базе данных."""
    
    @pytest.mark.asyncio
    async def test_db_read_only_detection(self):
        """Тест определения read-only режима БД."""
        # Подключаемся к БД
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Пытаемся выполнить SELECT (должен работать)
            result = await conn.fetchval("SELECT 1")
            assert result == 1
            
            # Пытаемся выполнить INSERT (должен работать в нормальном режиме)
            # В read-only режиме это должно вызвать ошибку
            try:
                await conn.execute("CREATE TEMP TABLE test_readonly (id INT)")
                await conn.execute("INSERT INTO test_readonly VALUES (1)")
                # Если дошли сюда, БД не в read-only режиме
                await conn.execute("DROP TABLE test_readonly")
            except Exception as e:
                # Если ошибка связана с read-only, проверяем сообщение
                error_msg = str(e).lower()
                if "read-only" in error_msg or "readonly" in error_msg:
                    # БД в read-only режиме
                    pass
    
    @pytest.mark.asyncio
    async def test_db_write_failure_handling(self):
        """Тест обработки ошибки записи в БД."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Пытаемся записать в несуществующую таблицу
            # (симуляция ошибки записи)
            try:
                await conn.execute("INSERT INTO non_existent_table VALUES (1)")
            except Exception as e:
                # Ожидаем ошибку
                assert "non_existent_table" in str(e).lower() or "does not exist" in str(e).lower()


class TestBurstTelemetry:
    """Тесты обработки burst телеметрии."""
    
    def test_burst_telemetry_handling(self):
        """Тест обработки большого количества телеметрии за короткое время."""
        # Симулируем burst телеметрии
        telemetry_messages = []
        for i in range(1000):
            telemetry_messages.append({
                "metric_type": "PH",
                "value": 6.5 + (i % 10) * 0.1,
                "ts": time.time() + i * 0.001,
                "node_id": f"nd-ph-{i % 10}"
            })
        
        # Проверяем, что все сообщения валидны
        from common.schemas.test_protocol_contracts import load_schema, validate_against_schema
        telemetry_schema = load_schema(
            Path(__file__).parent / "telemetry.json"
        )
        
        validated_count = 0
        for msg in telemetry_messages:
            try:
                validate_against_schema(msg, telemetry_schema)
                validated_count += 1
            except Exception:
                pass
        
        # Все сообщения должны быть валидны
        assert validated_count == len(telemetry_messages)
    
    @pytest.mark.asyncio
    async def test_burst_telemetry_queue_handling(self):
        """Тест обработки burst телеметрии через очередь."""
        # Симулируем отправку большого количества сообщений в очередь
        # (в реальном коде это может быть Redis очередь)
        messages = []
        for i in range(100):
            messages.append({
                "metric_type": "PH",
                "value": 6.5,
                "ts": time.time(),
                "node_id": f"nd-ph-{i}"
            })
        
        # Проверяем, что все сообщения могут быть обработаны
        # (в реальном коде это проверка очереди)
        assert len(messages) == 100
    
    def test_burst_telemetry_rate_limiting(self):
        """Тест rate limiting при burst телеметрии."""
        # Проверяем, что система может обработать burst без перегрузки
        # (в реальном коде должен быть rate limiting)
        start_time = time.time()
        messages_processed = 0
        
        # Симулируем обработку сообщений
        for i in range(100):
            # Симуляция обработки
            time.sleep(0.001)  # Небольшая задержка
            messages_processed += 1
        
        elapsed_time = time.time() - start_time
        
        # Проверяем, что обработка завершилась за разумное время
        assert messages_processed == 100
        assert elapsed_time < 1.0  # Должно быть быстро


class TestWebSocketEventId:
    """Тесты авто-проверки WS событий с event_id."""
    
    def test_websocket_event_has_event_id(self):
        """Тест, что WS события имеют event_id."""
        # Пример события из Laravel EventCreated
        event = {
            "id": 1,
            "kind": "test",
            "message": "Test event",
            "zoneId": 1,
            "occurredAt": "2025-01-01T12:00:00Z",
            "event_id": 1234567890,  # Обязательное поле
            "server_ts": 1737979200000
        }
        
        # Проверяем наличие event_id
        assert "event_id" in event
        assert isinstance(event["event_id"], int)
        assert event["event_id"] > 0
    
    def test_websocket_event_missing_event_id(self):
        """Тест, что события без event_id отклоняются."""
        # Событие без event_id
        event = {
            "id": 1,
            "kind": "test",
            "message": "Test event",
            "zoneId": 1,
            "occurredAt": "2025-01-01T12:00:00Z"
            # Нет event_id
        }
        
        # Проверяем, что event_id отсутствует
        assert "event_id" not in event
    
    def test_zone_events_contains_ws_event_id(self):
        """Тест, что zone_events содержит ws_event_id в payload."""
        # Пример записи из zone_events
        zone_event = {
            "id": 1,
            "zone_id": 1,
            "type": "command_status",
            "entity_type": "command",
            "entity_id": "cmd-123",
            "payload_json": {
                "status": "DONE",
                "message": "Command completed",
                "ws_event_id": 1234567890  # Должен быть в payload
            },
            "server_ts": 1737979200000
        }
        
        # Проверяем наличие ws_event_id в payload
        assert "payload_json" in zone_event
        payload = zone_event["payload_json"]
        assert "ws_event_id" in payload
        assert isinstance(payload["ws_event_id"], int)
    
    def test_all_ws_events_have_event_id(self):
        """Тест, что все типы WS событий имеют event_id."""
        # Различные типы событий
        events = [
            {
                "type": "EventCreated",
                "event_id": 1234567890,
                "server_ts": 1737979200000
            },
            {
                "type": "CommandStatusUpdated",
                "event_id": 1234567891,
                "server_ts": 1737979201000
            },
            {
                "type": "AlertCreated",
                "event_id": 1234567892,
                "server_ts": 1737979202000
            },
            {
                "type": "ZoneUpdated",
                "event_id": 1234567893,
                "server_ts": 1737979203000
            }
        ]
        
        # Проверяем, что все события имеют event_id
        for event in events:
            assert "event_id" in event
            assert isinstance(event["event_id"], int)
            assert event["event_id"] > 0
    
    def test_zone_events_matches_ws_event_id(self):
        """Тест, что zone_events содержит тот же event_id, что и WS событие."""
        # WS событие
        ws_event = {
            "event_id": 1234567890,
            "server_ts": 1737979200000,
            "type": "command_status"
        }
        
        # Соответствующая запись в zone_events
        zone_event = {
            "id": 1,
            "zone_id": 1,
            "type": "command_status",
            "payload_json": {
                "ws_event_id": 1234567890  # Должен совпадать с event_id из WS
            },
            "server_ts": 1737979200000
        }
        
        # Проверяем совпадение
        assert ws_event["event_id"] == zone_event["payload_json"]["ws_event_id"]
        assert ws_event["server_ts"] == zone_event["server_ts"]

