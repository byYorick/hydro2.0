"""Tests for MqttClient error logging."""
import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from common.mqtt import MqttClient


def test_mqtt_client_logs_handler_errors(caplog):
    """Test that MqttClient logs errors from message handlers."""
    with caplog.at_level(logging.ERROR):
        # Создаём клиент
        with patch("common.mqtt.get_settings") as mock_settings:
            from common.env import Settings
            mock_settings.return_value = Settings(
                mqtt_host="localhost",
                mqtt_port=1883,
                mqtt_client_id="test-client",
                mqtt_clean_session=False,
                mqtt_user=None,
                mqtt_pass=None,
                mqtt_tls=False,
                mqtt_ca_file=None,
            )
            
            client = MqttClient()
            
            # Создаём обработчик, который выбрасывает исключение
            def failing_handler(topic: str, payload: bytes):
                raise ValueError("Test error in handler")
            
            # Получаем обёртку
            wrapped = client._wrap(failing_handler)
            
            # Создаём mock сообщение
            mock_msg = MagicMock()
            mock_msg.topic = "test/topic"
            mock_msg.payload = b'{"test": "data"}'
            
            # Вызываем обёртку
            wrapped(None, None, mock_msg)
            
            # Проверяем, что ошибка была залогирована
            assert len(caplog.records) > 0
            assert any("Error in MQTT message handler" in record.message for record in caplog.records)
            assert any("test/topic" in record.message for record in caplog.records)
            assert any("Test error in handler" in str(record.exc_info) for record in caplog.records if record.exc_info)


def test_mqtt_client_does_not_crash_on_handler_error():
    """Test that MqttClient doesn't crash when handler raises exception."""
    with patch("common.mqtt.get_settings") as mock_settings:
        from common.env import Settings
        mock_settings.return_value = Settings(
            mqtt_host="localhost",
            mqtt_port=1883,
            mqtt_client_id="test-client",
            mqtt_clean_session=False,
            mqtt_user=None,
            mqtt_pass=None,
            mqtt_tls=False,
            mqtt_ca_file=None,
        )
        
        client = MqttClient()
        
        # Создаём обработчик, который выбрасывает исключение
        def failing_handler(topic: str, payload: bytes):
            raise RuntimeError("Handler failed")
        
        wrapped = client._wrap(failing_handler)
        
        # Создаём mock сообщение
        mock_msg = MagicMock()
        mock_msg.topic = "test/topic"
        mock_msg.payload = b'{"test": "data"}'
        
        # Вызываем обёртку - не должно упасть
        try:
            wrapped(None, None, mock_msg)
        except Exception:
            pytest.fail("Handler error should be caught and logged, not propagated")


def test_mqtt_client_successful_handler_no_logging(caplog):
    """Test that successful handler doesn't produce error logs."""
    with caplog.at_level(logging.ERROR):
        with patch("common.mqtt.get_settings") as mock_settings:
            from common.env import Settings
            mock_settings.return_value = Settings(
                mqtt_host="localhost",
                mqtt_port=1883,
                mqtt_client_id="test-client",
                mqtt_clean_session=False,
                mqtt_user=None,
                mqtt_pass=None,
                mqtt_tls=False,
                mqtt_ca_file=None,
            )
            
            client = MqttClient()
            
            # Создаём успешный обработчик
            def successful_handler(topic: str, payload: bytes):
                pass  # Ничего не делает
            
            wrapped = client._wrap(successful_handler)
            
            # Создаём mock сообщение
            mock_msg = MagicMock()
            mock_msg.topic = "test/topic"
            mock_msg.payload = b'{"test": "data"}'
            
            # Вызываем обёртку
            wrapped(None, None, mock_msg)
            
            # Проверяем, что ошибок не было залогировано
            error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
            assert len(error_records) == 0


def _mqtt_settings_mock():
    from common.env import Settings
    return Settings(
        mqtt_host="mqtt",
        mqtt_port=1883,
        mqtt_client_id="test-client",
        mqtt_clean_session=False,
        mqtt_user=None,
        mqtt_pass=None,
        mqtt_tls=False,
        mqtt_ca_file=None,
    )


def test_mqtt_client_start_retries_transient_dns_then_connects():
    """Transient connect failures (DNS/broker restart) are retried before success."""
    with patch("common.mqtt.get_settings", return_value=_mqtt_settings_mock()):
        client = MqttClient()
        client._client = MagicMock()
        client._client._client_id = b"test-client"
        client._client._thread = None

        calls = {"n": 0}

        def connect_side_effect(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError(-3, "Temporary failure in name resolution")
            # Simulate successful on_connect before wait returns
            client._connected.set()

        client._client.connect.side_effect = connect_side_effect

        client.start()

        assert calls["n"] == 3
        assert client.is_connected()
        # loop_start только после успешного connect (первые 2 попытки упали на DNS)
        assert client._client.loop_start.call_count == 1
        assert client._client.connect.call_count == 3


def test_mqtt_client_start_raises_after_retries_exhausted():
    """All connect attempts fail → original error is re-raised."""
    with patch("common.mqtt.get_settings", return_value=_mqtt_settings_mock()):
        client = MqttClient()
        client._client = MagicMock()
        client._client._client_id = b"test-client"
        client._client._thread = None
        client._client.connect.side_effect = OSError(-3, "Temporary failure in name resolution")

        with patch.object(client._connected, "wait", return_value=False):
            with pytest.raises(OSError, match="Temporary failure"):
                client.start()

        assert client._client.connect.call_count == 6

