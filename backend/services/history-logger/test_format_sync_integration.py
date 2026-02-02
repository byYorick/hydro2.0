"""
Интеграционные тесты для проверки синхронизации форматов между прошивками и history-logger.
Проверяет полный цикл обработки сообщений от прошивок.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import json


class TestTelemetryFormatSync:
    """Тесты синхронизации формата телеметрии."""
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_with_firmware_format(self):
        """Тест обработки телеметрии в формате от прошивок."""
        from telemetry_processing import handle_telemetry
        from models import TelemetryPayloadModel
        
        # Формат от прошивок ESP32
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        payload_data = {
            "metric_type": "PH",
            "value": 6.5,
            "ts": 1737979.2,  # секунды (esp_timer_get_time() / 1000000)
            "channel": "ph_sensor",
            "node_id": "nd-ph-1",
            "raw": 1465,
            "stub": False,
            "stable": True
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(return_value=True)
        
        with patch('state.telemetry_queue', mock_queue), \
             patch('telemetry_processing.TELEM_RECEIVED') as mock_telem_received, \
             patch('telemetry_processing.TELEMETRY_DROPPED') as mock_dropped:
            
            await handle_telemetry(topic, payload)
            
            # Проверяем, что сообщение было обработано
            mock_telem_received.inc.assert_called_once()
            
            # Проверяем, что элемент был добавлен в очередь
            mock_queue.push.assert_called_once()
            call_args = mock_queue.push.call_args[0][0]
            
            # Проверяем извлеченные данные
            assert call_args.node_uid == "nd-ph-1"
            assert call_args.zone_uid == "zn-1"
            assert call_args.metric_type == "PH"
            assert call_args.value == 6.5
            assert call_args.channel == "ph_sensor"
            assert isinstance(call_args.ts, datetime)
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_extracts_channel_from_topic(self):
        """Тест извлечения channel из топика."""
        from telemetry_processing import handle_telemetry
        from utils import _extract_channel_from_topic
        
        # Проверяем функцию извлечения channel
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        channel = _extract_channel_from_topic(topic)
        assert channel == "ph_sensor"
        
        # Проверяем, что channel используется при отсутствии в payload
        payload_data = {
            "metric_type": "PH",
            "value": 6.5,
            "ts": 1737979.2
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        mock_queue = AsyncMock()
        mock_queue.push = AsyncMock(return_value=True)
        
        with patch('state.telemetry_queue', mock_queue):
            await handle_telemetry(topic, payload)
            
            call_args = mock_queue.push.call_args[0][0]
            # channel должен быть извлечен из топика
            assert call_args.channel == "ph_sensor"
    
    @pytest.mark.asyncio
    async def test_handle_telemetry_rejects_old_format(self):
        """Тест отклонения старого формата (timestamp вместо ts)."""
        from telemetry_processing import handle_telemetry
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        # Старый формат с timestamp (должен быть отклонен)
        payload_data = {
            "metric_type": "PH",
            "value": 6.5,
            "timestamp": 1737979200000  # миллисекунды (старый формат)
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        mock_queue = AsyncMock()
        
        with patch('state.telemetry_queue', mock_queue), \
             patch('telemetry_processing.TELEMETRY_DROPPED') as mock_dropped:
            
            await handle_telemetry(topic, payload)
            
            # Сообщение должно быть отклонено (validation failed)
            # Проверяем, что очередь не была вызвана
            mock_queue.push.assert_not_called()
            # Проверяем, что метрика dropped была увеличена
            assert mock_dropped.labels.called


class TestConfigReportFormatSync:
    """Тесты синхронизации формата config_report."""
    
    @pytest.mark.asyncio
    async def test_handle_config_report_stores_config(self):
        """Тест обработки config_report от прошивок."""
        from mqtt_handlers import handle_config_report
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/config_report"
        payload_data = {
            "node_id": "nd-ph-1",
            "version": 1,
            "channels": [
                {"name": "ph_sensor", "type": "SENSOR", "metric": "PH"}
            ],
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        with patch('mqtt_handlers.fetch', new_callable=AsyncMock) as mock_fetch, \
             patch('mqtt_handlers.execute', new_callable=AsyncMock) as mock_execute, \
             patch('mqtt_handlers.sync_node_channels_from_payload', new_callable=AsyncMock) as mock_sync, \
             patch('mqtt_handlers._complete_binding_after_config_report', new_callable=AsyncMock) as mock_complete, \
             patch('mqtt_handlers.CONFIG_REPORT_RECEIVED') as mock_received, \
             patch('mqtt_handlers.CONFIG_REPORT_PROCESSED') as mock_processed:
            
            mock_fetch.return_value = [
                {
                    "id": 1,
                    "uid": "nd-ph-1",
                    "lifecycle_state": "REGISTERED_BACKEND",
                    "zone_id": None,
                    "pending_zone_id": 1,
                }
            ]
            
            await handle_config_report(topic, payload)
            
            mock_received.inc.assert_called_once()
            mock_execute.assert_called_once()
            mock_sync.assert_called_once()
            mock_complete.assert_called_once()
            mock_processed.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_config_report_buffers_when_node_missing(self):
        """Тест буферизации config_report, если узел еще не зарегистрирован."""
        from mqtt_handlers import handle_config_report

        topic = "hydro/gh-temp/zn-temp/esp32-aabbccddeeff/config_report"
        payload_data = {
            "node_id": "esp32-aabbccddeeff",
            "version": 1,
            "channels": [
                {"name": "ph_sensor", "type": "SENSOR", "metric": "PH"}
            ],
        }
        payload = json.dumps(payload_data).encode('utf-8')

        with patch('mqtt_handlers.fetch', new_callable=AsyncMock) as mock_fetch, \
             patch('mqtt_handlers._store_pending_config_report', new_callable=AsyncMock) as mock_store:

            mock_fetch.return_value = []

            await handle_config_report(topic, payload)

            mock_store.assert_awaited_once_with("esp32-aabbccddeeff", topic, payload)

    @pytest.mark.asyncio
    async def test_process_pending_config_report_after_registration(self):
        """Тест обработки буферизованного config_report после регистрации."""
        from mqtt_handlers import (
            _process_pending_config_report_after_registration,
            _PENDING_CONFIG_REPORTS,
        )

        hardware_id = "esp32-aabbccddeeff"
        topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config_report"
        payload = b'{"node_id":"esp32-aabbccddeeff","version":1}'

        _PENDING_CONFIG_REPORTS.clear()
        _PENDING_CONFIG_REPORTS[hardware_id] = {
            "topic": topic,
            "payload": payload,
            "ts": datetime.now().timestamp(),
        }

        with patch('mqtt_handlers.handle_config_report', new_callable=AsyncMock) as mock_handle:
            await _process_pending_config_report_after_registration(hardware_id)

            mock_handle.assert_awaited_once_with(topic, payload)
            assert hardware_id not in _PENDING_CONFIG_REPORTS

    @pytest.mark.asyncio
    async def test_handle_config_report_temp_topic_maps_hardware_id(self):
        """Тест обработки config_report из temp топика с hardware_id."""
        from mqtt_handlers import handle_config_report

        topic = "hydro/gh-temp/zn-temp/esp32-aabbccddeeff/config_report"
        payload_data = {
            "node_id": "esp32-aabbccddeeff",
            "version": 3,
            "channels": [
                {"name": "ph_sensor", "type": "SENSOR", "metric": "PH"}
            ],
        }
        payload = json.dumps(payload_data).encode('utf-8')

        with patch('mqtt_handlers.fetch', new_callable=AsyncMock) as mock_fetch, \
             patch('mqtt_handlers.execute', new_callable=AsyncMock) as mock_execute, \
             patch('mqtt_handlers.sync_node_channels_from_payload', new_callable=AsyncMock) as mock_sync, \
             patch('mqtt_handlers._complete_binding_after_config_report', new_callable=AsyncMock) as mock_complete, \
             patch('mqtt_handlers.CONFIG_REPORT_RECEIVED') as mock_received, \
             patch('mqtt_handlers.CONFIG_REPORT_PROCESSED') as mock_processed:

            mock_fetch.return_value = [
                {
                    "id": 7,
                    "uid": "nd-ph-esp32aa-1",
                    "lifecycle_state": "REGISTERED_BACKEND",
                    "zone_id": None,
                    "pending_zone_id": 1,
                }
            ]

            await handle_config_report(topic, payload)

            mock_received.inc.assert_called_once()
            mock_execute.assert_called_once()
            updated_payload = mock_execute.call_args[0][1]
            assert updated_payload["node_id"] == "nd-ph-esp32aa-1"
            mock_sync.assert_called_once()
            mock_complete.assert_called_once()
            mock_processed.inc.assert_called_once()


class TestHeartbeatFormatSync:
    """Тесты синхронизации формата heartbeat."""
    
    @pytest.mark.asyncio
    async def test_handle_heartbeat_with_firmware_format(self):
        """Тест обработки heartbeat в формате от прошивок."""
        from mqtt_handlers import handle_heartbeat
        
        topic = "hydro/gh-1/zn-1/nd-ph-1/heartbeat"
        payload_data = {
            "uptime": 35555,  # секунды
            "free_heap": 102000,  # байты
            "rssi": -62
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        with patch('mqtt_handlers.execute', new_callable=AsyncMock) as mock_execute, \
             patch('mqtt_handlers.HEARTBEAT_RECEIVED') as mock_received:
            
            await handle_heartbeat(topic, payload)
            
            # Проверяем, что сообщение было обработано
            mock_received.labels.assert_called_once()
            # Проверяем, что был выполнен SQL запрос
            assert mock_execute.called


class TestNodeHelloFormatSync:
    """Тесты синхронизации формата node_hello."""
    
    @pytest.mark.asyncio
    async def test_handle_node_hello_with_firmware_format(self):
        """Тест обработки node_hello в формате от прошивок."""
        from mqtt_handlers import handle_node_hello
        
        topic = "hydro/node_hello"
        payload_data = {
            "message_type": "node_hello",
            "hardware_id": "esp32-aabbccddeeff",
            "node_type": "ph",
            "fw_version": "v5.1.0",
            "capabilities": ["ph", "temperature"]
        }
        payload = json.dumps(payload_data).encode('utf-8')
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "OK"
        
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post, \
             patch('mqtt_handlers.NODE_HELLO_RECEIVED') as mock_received, \
             patch('mqtt_handlers.get_settings') as mock_settings:
            
            mock_post.return_value = mock_response
            mock_settings.return_value.laravel_api_url = "http://localhost/api"
            mock_settings.return_value.laravel_api_token = "test-token"
            
            await handle_node_hello(topic, payload)
            
            # Проверяем, что сообщение было обработано
            mock_received.inc.assert_called_once()
            # Проверяем, что был вызван Laravel API
            assert mock_post.called


class TestTopicFormatSync:
    """Тесты синхронизации формата топиков."""
    
    def test_telemetry_topic_format(self):
        """Тест формата топика телеметрии."""
        from utils import _extract_channel_from_topic, _extract_node_uid, _extract_zone_uid
        
        # Правильный формат: hydro/{gh}/{zone}/{node}/{channel}/telemetry
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        
        assert _extract_zone_uid(topic) == "zn-1"
        assert _extract_node_uid(topic) == "nd-ph-1"
        assert _extract_channel_from_topic(topic) == "ph_sensor"
    
    def test_heartbeat_topic_format(self):
        """Тест формата топика heartbeat."""
        from utils import _extract_node_uid, _extract_zone_uid
        
        # Формат: hydro/{gh}/{zone}/{node}/heartbeat
        topic = "hydro/gh-1/zn-1/nd-ph-1/heartbeat"
        
        assert _extract_zone_uid(topic) == "zn-1"
        assert _extract_node_uid(topic) == "nd-ph-1"
    
    def test_config_report_topic_format(self):
        """Тест формата топика config_report."""
        from utils import _extract_node_uid, _extract_zone_uid
        
        # Формат: hydro/{gh}/{zone}/{node}/config_report
        topic = "hydro/gh-1/zn-1/nd-ph-1/config_report"
        
        assert _extract_zone_uid(topic) == "zn-1"
        assert _extract_node_uid(topic) == "nd-ph-1"


class TestPayloadValidation:
    """Тесты валидации payload от прошивок."""
    
    def test_telemetry_payload_required_fields(self):
        """Тест обязательных полей в payload телеметрии."""
        from models import TelemetryPayloadModel
        from pydantic import ValidationError
        
        # Валидный payload (только обязательные поля)
        payload = TelemetryPayloadModel(
            metric_type="PH",
            value=6.5
        )
        assert payload.metric_type == "PH"
        assert payload.value == 6.5
        
        # Отсутствие metric_type должно вызвать ошибку
        with pytest.raises(ValidationError):
            TelemetryPayloadModel(value=6.5)
        
        # Отсутствие value должно вызвать ошибку
        with pytest.raises(ValidationError):
            TelemetryPayloadModel(metric_type="PH")
    
    def test_telemetry_payload_optional_fields(self):
        """Тест опциональных полей в payload телеметрии."""
        from models import TelemetryPayloadModel
        
        # Полный payload со всеми опциональными полями
        payload = TelemetryPayloadModel(
            metric_type="PH",
            value=6.5,
            ts=1737979.2,
            channel="ph_sensor",
            node_id="nd-ph-1",
            raw=1465,
            stub=False,
            stable=True
        )
        
        assert payload.ts == 1737979.2
        assert payload.channel == "ph_sensor"
        assert payload.node_id == "nd-ph-1"
        assert payload.raw == 1465
        assert payload.stub is False
        assert payload.stable is True
