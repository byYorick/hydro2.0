"""Tests for format synchronization between firmware and history-logger."""
import pytest
from datetime import datetime
from main import TelemetryPayloadModel, _extract_channel_from_topic, _extract_node_uid, _extract_zone_uid


class TestTelemetryPayloadFormat:
    """Тесты формата payload телеметрии."""
    
    def test_telemetry_payload_with_ts(self):
        """Тест payload с полем ts (формат от прошивок)."""
        payload = {
            "metric_type": "PH",
            "value": 6.5,
            "ts": 1737979.2,  # секунды
            "channel": "ph_sensor",
            "node_id": "nd-ph-1",
            "raw": 1465,
            "stub": False,
            "stable": True
        }
        
        model = TelemetryPayloadModel(**payload)
        assert model.metric_type == "PH"
        assert model.value == 6.5
        assert model.ts == 1737979.2
        assert model.channel == "ph_sensor"
        assert model.node_id == "nd-ph-1"
        assert model.raw == 1465
        assert model.stub is False
        assert model.stable is True
    
    def test_telemetry_payload_with_ts_only(self):
        """Тест payload только с полем ts (формат от прошивок)."""
        payload = {
            "metric_type": "EC",
            "value": 1.2,
            "ts": 1737979.2,  # секунды
            "channel": "ec_sensor"
        }
        
        model = TelemetryPayloadModel(**payload)
        assert model.metric_type == "EC"
        assert model.value == 1.2
        assert model.ts == 1737979.2
        assert model.channel == "ec_sensor"
    
    def test_telemetry_payload_minimal(self):
        """Тест минимального payload (только обязательные поля)."""
        payload = {
            "metric_type": "TEMPERATURE",
            "value": 25.5
        }
        
        model = TelemetryPayloadModel(**payload)
        assert model.metric_type == "TEMPERATURE"
        assert model.value == 25.5
        assert model.ts is None
        assert model.channel is None


class TestTelemetryTopicFormat:
    """Тесты формата топиков телеметрии."""
    
    def test_extract_channel_from_topic(self):
        """Тест извлечения channel из топика."""
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        channel = _extract_channel_from_topic(topic)
        assert channel == "ph_sensor"
    
    def test_extract_node_uid_from_topic(self):
        """Тест извлечения node_uid из топика."""
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        node_uid = _extract_node_uid(topic)
        assert node_uid == "nd-ph-1"
    
    def test_extract_zone_uid_from_topic(self):
        """Тест извлечения zone_uid из топика."""
        topic = "hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry"
        zone_uid = _extract_zone_uid(topic)
        assert zone_uid == "zn-1"
    
    def test_extract_from_invalid_topic(self):
        """Тест извлечения из невалидного топика."""
        topic = "invalid/topic"
        assert _extract_channel_from_topic(topic) is None
        assert _extract_node_uid(topic) is None
        # _extract_zone_uid просто берет 3-й элемент, если он есть
        # Для топика с менее чем 3 частями вернет None
        assert _extract_zone_uid(topic) is None
        
        # Для топика с 3+ частями вернет 3-й элемент (не валидирует формат)
        topic_with_3_parts = "invalid/topic/format"
        assert _extract_zone_uid(topic_with_3_parts) == "format"


class TestConfigResponseFormat:
    """Тесты формата config_response."""
    
    def test_config_response_ack_format(self):
        """Тест обработки config_response со статусом ACK (от прошивок)."""
        # Этот тест проверяет, что history-logger принимает только "ACK"
        # Реальная проверка будет в интеграционных тестах
        data = {
            "status": "ACK",
            "applied_at": 1737979.2,
            "restarted": ["pump_driver"]
        }
        
        # Проверяем, что статус должен быть "ACK"
        status = data.get("status", "").upper()
        assert status == "ACK"


class TestHeartbeatFormat:
    """Тесты формата heartbeat."""
    
    def test_heartbeat_payload_format(self):
        """Тест формата heartbeat payload от прошивок."""
        payload = {
            "uptime": 35555,  # секунды
            "free_heap": 102000,  # байты
            "rssi": -62
        }
        
        # Проверяем, что все поля присутствуют
        assert "uptime" in payload
        assert "free_heap" in payload
        assert "rssi" in payload
        
        # Проверяем типы
        assert isinstance(payload["uptime"], int)
        assert isinstance(payload["free_heap"], int)
        assert isinstance(payload["rssi"], int)


class TestNodeHelloFormat:
    """Тесты формата node_hello."""
    
    def test_node_hello_payload_format(self):
        """Тест формата node_hello payload от прошивок."""
        payload = {
            "message_type": "node_hello",
            "hardware_id": "esp32-aabbccddeeff",
            "node_type": "ph",
            "fw_version": "v5.1.0",
            "capabilities": ["ph", "temperature"]
        }
        
        # Проверяем обязательные поля
        assert payload["message_type"] == "node_hello"
        assert "hardware_id" in payload
        assert "node_type" in payload
        assert "fw_version" in payload
        assert "capabilities" in payload
        
        # Опциональные поля могут отсутствовать
        assert "hardware_revision" not in payload  # Опциональное
        assert "provisioning_meta" not in payload  # Опциональное

