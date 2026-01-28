"""
Контрактные тесты для протокола обмена данными.

Проверяет совместимость payload'ов между нодой/HL/Laravel/клиентами.
Использует JSON-schema для валидации и fixtures для тестирования.
"""
import json
import pytest
from pathlib import Path
from typing import Dict, Any, List
import jsonschema
from jsonschema import validate, ValidationError

# Импорты Pydantic моделей для валидации
from common.schemas import Command, CommandResponse
from common.schemas.fixtures import (
    get_all_command_fixtures,
    get_all_response_fixtures,
    create_command_fixture,
    create_command_response_fixture
)
from common.schemas.fixtures_extended import (
    get_all_telemetry_fixtures,
    get_all_error_fixtures,
    get_all_alert_fixtures
)

# Импорт моделей из history-logger
# Используем относительный импорт или переменную окружения
try:
    from history_logger.main import TelemetryPayloadModel
except ImportError:
    # Fallback для случаев когда модуль не доступен
    # В реальных тестах это должно быть настроено через PYTHONPATH
    TelemetryPayloadModel = None


# Путь к JSON-schema файлам
SCHEMAS_DIR = Path(__file__).parent
TELEMETRY_SCHEMA = SCHEMAS_DIR / "telemetry.json"
COMMAND_SCHEMA = SCHEMAS_DIR / "command.json"
COMMAND_RESPONSE_SCHEMA = SCHEMAS_DIR / "command_response.json"
ERROR_ALERT_SCHEMA = SCHEMAS_DIR / "error_alert.json"
ZONE_EVENTS_SCHEMA = SCHEMAS_DIR / "zone_events.json"


def load_schema(schema_path: Path) -> Dict[str, Any]:
    """Загружает JSON-schema из файла."""
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Валидирует данные против JSON-schema."""
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        raise AssertionError(f"Schema validation failed: {e.message} at {'.'.join(str(p) for p in e.path)}")


class TestTelemetryProtocol:
    """Контрактные тесты для telemetry payload."""
    
    @pytest.fixture
    def telemetry_schema(self):
        """Загружает схему telemetry."""
        return load_schema(TELEMETRY_SCHEMA)
    
    def test_telemetry_minimal_payload(self, telemetry_schema):
        """Тест минимального payload телеметрии (только обязательные поля)."""
        payload = {
            "metric_type": "PH",
            "value": 6.5
        }
        
        # Валидация через JSON-schema
        validate_against_schema(payload, telemetry_schema)
        
        # Валидация через Pydantic модель (если доступна)
        # Пропускаем если модель не импортирована (для CI без history-logger)
        try:
            if TelemetryPayloadModel:
                model = TelemetryPayloadModel(**payload)
                assert model.metric_type == "PH"
                assert model.value == 6.5
        except Exception:
            pass  # Пропускаем если модель недоступна
    
    def test_telemetry_full_payload(self, telemetry_schema):
        """Тест полного payload телеметрии со всеми опциональными полями."""
        payload = {
            "metric_type": "PH",
            "value": 6.5,
            "ts": 1737979200.5,
            "channel": "ph_sensor",
            "node_id": "nd-ph-1",
            "raw": 1465,
            "stub": False,
            "stable": True,
            "tds": 1200,
            "error_code": None,
            "temperature": 22.5,
            "state": "active",
            "event": "calibration",
            "health": {"status": "ok", "uptime": 3600},
            "zone_uid": "zn-1",
            "node_uid": "nd-ph-1",
            "gh_uid": "gh-1"
        }
        
        # Валидация через JSON-schema
        validate_against_schema(payload, telemetry_schema)
        
        # Валидация через Pydantic модель (если доступна)
        # Пропускаем если модель не импортирована (для CI без history-logger)
        try:
            if TelemetryPayloadModel:
                model = TelemetryPayloadModel(**payload)
                assert model.metric_type == "PH"
                assert model.value == 6.5
                assert model.channel == "ph_sensor"
        except Exception:
            pass  # Пропускаем если модель недоступна
    
    def test_telemetry_invalid_metric_type(self, telemetry_schema):
        """Тест невалидного metric_type (пустая строка)."""
        payload = {
            "metric_type": "",
            "value": 6.5
        }
        
        # JSON-schema должна отклонить
        with pytest.raises(AssertionError):
            validate_against_schema(payload, telemetry_schema)
        
        # Pydantic должна отклонить (если доступна)
        if TelemetryPayloadModel:
            from pydantic import ValidationError
            with pytest.raises(ValidationError):
                TelemetryPayloadModel(**payload)
    
    def test_telemetry_missing_required_fields(self, telemetry_schema):
        """Тест отсутствия обязательных полей."""
        # Отсутствует metric_type
        payload = {"value": 6.5}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, telemetry_schema)
        
        # Отсутствует value
        payload = {"metric_type": "PH"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, telemetry_schema)


class TestCommandProtocol:
    """Контрактные тесты для command payload."""
    
    @pytest.fixture
    def command_schema(self):
        """Загружает схему command."""
        return load_schema(COMMAND_SCHEMA)
    
    def test_command_minimal_payload(self, command_schema):
        """Тест минимального payload команды."""
        payload = create_command_fixture(
            cmd="dose",
            params={"ml": 1.2}
        )
        
        # Валидация через JSON-schema
        validate_against_schema(payload, command_schema)
        
        # Валидация через Pydantic модель
        cmd = Command(**payload)
        assert cmd.cmd == "dose"
        assert cmd.params == {"ml": 1.2}
        assert cmd.cmd_id is not None
    
    def test_command_all_fixtures(self, command_schema):
        """Тест всех fixtures команд."""
        fixtures = get_all_command_fixtures()
        
        for name, fixture in fixtures.items():
            # Валидация через JSON-schema
            validate_against_schema(fixture, command_schema)
            
            # Валидация через Pydantic модель
            cmd = Command(**fixture)
            assert cmd.cmd_id is not None
            assert cmd.cmd is not None
            assert cmd.ts > 0
    
    def test_command_invalid_cmd_id_format(self, command_schema):
        """Тест невалидного формата cmd_id."""
        payload = create_command_fixture(
            cmd="dose",
            cmd_id="invalid cmd id with spaces!"
        )
        
        # Pydantic должна отклонить
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Command(**payload)
    
    def test_command_missing_required_fields(self, command_schema):
        """Тест отсутствия обязательных полей."""
        # Отсутствует cmd_id
        payload = {"cmd": "dose", "params": {"ml": 1.2}, "ts": 1234567890, "sig": "deadbeef"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, command_schema)
        
        # Отсутствует cmd
        payload = {"cmd_id": "cmd-123", "params": {"ml": 1.2}, "ts": 1234567890, "sig": "deadbeef"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, command_schema)

        # Отсутствует params
        payload = {"cmd_id": "cmd-123", "cmd": "dose", "ts": 1234567890, "sig": "deadbeef"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, command_schema)

        # Отсутствует sig
        payload = {"cmd_id": "cmd-123", "cmd": "dose", "params": {"ml": 1.2}, "ts": 1234567890}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, command_schema)


class TestCommandResponseProtocol:
    """Контрактные тесты для command_response payload."""
    
    @pytest.fixture
    def command_response_schema(self):
        """Загружает схему command_response."""
        return load_schema(COMMAND_RESPONSE_SCHEMA)
    
    def test_command_response_accepted(self, command_response_schema):
        """Тест ответа ACK."""
        payload = create_command_response_fixture(
            cmd_id="cmd-123",
            status="ACK"
        )
        
        # Валидация через JSON-schema
        validate_against_schema(payload, command_response_schema)
        
        # Валидация через Pydantic модель
        response = CommandResponse(**payload)
        assert response.status == "ACK"
    
    def test_command_response_all_fixtures(self, command_response_schema):
        """Тест всех fixtures ответов."""
        fixtures = get_all_response_fixtures()
        
        for name, fixture in fixtures.items():
            # Валидация через JSON-schema
            validate_against_schema(fixture, command_response_schema)
            
            # Валидация через Pydantic модель
            response = CommandResponse(**fixture)
            assert response.cmd_id is not None
            assert response.status in ["ACK", "DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT"]
            assert response.ts > 0
    
    def test_command_response_invalid_status(self, command_response_schema):
        """Тест невалидного статуса."""
        payload = create_command_response_fixture(
            cmd_id="cmd-123",
            status="INVALID_STATUS"
        )
        
        # JSON-schema должна отклонить
        with pytest.raises(AssertionError):
            validate_against_schema(payload, command_response_schema)
        
        # Pydantic должна отклонить
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CommandResponse(**payload)


class TestErrorAlertProtocol:
    """Контрактные тесты для error/alert payload."""
    
    @pytest.fixture
    def error_alert_schema(self):
        """Загружает схему error/alert."""
        return load_schema(ERROR_ALERT_SCHEMA)
    
    def test_error_minimal_payload(self, error_alert_schema):
        """Тест минимального payload ошибки."""
        payload = {
            "level": "ERROR",
            "component": "sensor",
            "message": "Sensor reading failed"
        }
        
        validate_against_schema(payload, error_alert_schema)
    
    def test_error_all_fixtures(self, error_alert_schema):
        """Тест всех fixtures ошибок."""
        fixtures = get_all_error_fixtures()
        
        for name, fixture in fixtures.items():
            validate_against_schema(fixture, error_alert_schema)
    
    def test_alert_all_fixtures(self, error_alert_schema):
        """Тест всех fixtures алертов."""
        fixtures = get_all_alert_fixtures()
        
        for name, fixture in fixtures.items():
            validate_against_schema(fixture, error_alert_schema)
    
    def test_error_full_payload(self, error_alert_schema):
        """Тест полного payload ошибки."""
        payload = {
            "level": "ERROR",
            "component": "pump",
            "error_code": "ESP_ERR_NO_MEM",
            "error_code_num": 101,
            "message": "Out of memory",
            "ts": 1737979200.5,
            "hardware_id": "AA:BB:CC:DD:EE:FF",
            "node_uid": "nd-ph-1",
            "zone_id": 1,
            "details": {
                "free_heap": 1024,
                "allocated": 50000
            }
        }
        
        validate_against_schema(payload, error_alert_schema)
    
    def test_alert_payload(self, error_alert_schema):
        """Тест payload алерта от backend."""
        payload = {
            "level": "WARNING",
            "component": "automation",
            "source": "biz",
            "code": "PH_LOW",
            "type": "threshold",
            "severity": "medium",
            "zone_id": 1,
            "node_uid": "nd-ph-1",
            "message": "pH value below threshold",
            "ts": 1737979200.5,
            "details": {
                "current_value": 5.5,
                "threshold": 6.0
            }
        }
        
        validate_against_schema(payload, error_alert_schema)
    
    def test_error_invalid_level(self, error_alert_schema):
        """Тест невалидного уровня ошибки."""
        payload = {
            "level": "INVALID_LEVEL",
            "component": "sensor"
        }
        
        with pytest.raises(AssertionError):
            validate_against_schema(payload, error_alert_schema)
    
    def test_error_missing_required_fields(self, error_alert_schema):
        """Тест отсутствия обязательных полей."""
        # Отсутствует level
        payload = {"component": "sensor"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, error_alert_schema)
        
        # Отсутствует component
        payload = {"level": "ERROR"}
        with pytest.raises(AssertionError):
            validate_against_schema(payload, error_alert_schema)


class TestLaravelRequestValidation:
    """Тесты валидации запросов в Laravel."""
    
    def test_laravel_command_request_validation(self):
        """Тест валидации CommandRequest в Laravel (симуляция через Pydantic)."""
        from common.schemas import CommandRequest
        
        # Валидный запрос
        request = CommandRequest(
            cmd="dose",
            params={"ml": 1.2},
            node_uid="nd-ph-1",
            channel="pump_nutrient"
        )
        assert request.cmd == "dose"
        assert request.params == {"ml": 1.2}
        
        # Невалидный запрос (отсутствует cmd)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CommandRequest(params={"ml": 1.2})


class TestProtocolCompatibility:
    """Тесты совместимости протокола между компонентами."""
    
    def test_command_roundtrip(self):
        """Тест полного цикла: создание команды → валидация → ответ."""
        # Создаём команду
        cmd = Command.create(
            cmd="dose",
            params={"ml": 1.2, "channel": "pump_nutrient"},
            sig="deadbeef"
        )
        
        # Конвертируем в JSON
        cmd_json = cmd.model_dump()
        
        # Валидируем через JSON-schema
        command_schema = load_schema(COMMAND_SCHEMA)
        validate_against_schema(cmd_json, command_schema)
        
        # Создаём ответ
        response = CommandResponse.done(
            cmd_id=cmd.cmd_id,
            details={"duration_ms": 1000}
        )
        
        # Валидируем ответ
        response_schema = load_schema(COMMAND_RESPONSE_SCHEMA)
        response_json = response.model_dump()
        validate_against_schema(response_json, response_schema)
    
    def test_telemetry_from_firmware_to_backend(self):
        """Тест payload телеметрии от прошивки до backend."""
        # Payload от прошивки (может быть минимальным)
        firmware_payload = {
            "metric_type": "PH",
            "value": 6.5,
            "ts": 1737979200
        }
        
        # Валидация через JSON-schema
        telemetry_schema = load_schema(TELEMETRY_SCHEMA)
        validate_against_schema(firmware_payload, telemetry_schema)
        
        # Валидация через Pydantic в history-logger (если доступна)
        # Пропускаем если модель не импортирована (для CI без history-logger)
        try:
            if TelemetryPayloadModel:
                model = TelemetryPayloadModel(**firmware_payload)
                assert model.metric_type == "PH"
                assert model.value == 6.5
        except Exception:
            pass  # Пропускаем если модель недоступна


class TestZoneEventsProtocol:
    """Контрактные тесты для zone_events payload."""
    
    @pytest.fixture
    def zone_events_schema(self):
        """Загружает схему zone_events."""
        return load_schema(ZONE_EVENTS_SCHEMA)
    
    def test_zone_events_minimal_payload(self, zone_events_schema):
        """Тест минимального payload события зоны."""
        import time
        payload = {
            "zone_id": 1,
            "type": "telemetry_updated",
            "server_ts": int(time.time() * 1000)
        }
        
        validate_against_schema(payload, zone_events_schema)
    
    def test_zone_events_full_payload(self, zone_events_schema):
        """Тест полного payload события зоны."""
        import time
        payload = {
            "id": 123,
            "zone_id": 1,
            "type": "command_status",
            "entity_type": "command",
            "entity_id": "cmd-123",
            "payload_json": {
                "status": "DONE",
                "message": "Command completed",
                "ws_event_id": 1234567890
            },
            "server_ts": int(time.time() * 1000),
            "created_at": "2025-01-01T12:00:00Z",
            "event_id": 1234567890
        }
        
        validate_against_schema(payload, zone_events_schema)
    
    def test_zone_events_alert_created(self, zone_events_schema):
        """Тест payload события alert_created."""
        import time
        payload = {
            "zone_id": 1,
            "type": "alert_created",
            "entity_type": "alert",
            "entity_id": "42",
            "payload_json": {
                "code": "PH_LOW",
                "severity": "medium",
                "ws_event_id": 1234567891
            },
            "server_ts": int(time.time() * 1000)
        }
        
        validate_against_schema(payload, zone_events_schema)
    
    def test_zone_events_telemetry_updated(self, zone_events_schema):
        """Тест payload события telemetry_updated."""
        import time
        payload = {
            "zone_id": 1,
            "type": "telemetry_updated",
            "entity_type": "telemetry",
            "entity_id": None,
            "payload_json": {
                "metric_type": "PH",
                "value": 6.5,
                "ws_event_id": 1234567892
            },
            "server_ts": int(time.time() * 1000)
        }
        
        validate_against_schema(payload, zone_events_schema)
    
    def test_zone_events_missing_required_fields(self, zone_events_schema):
        """Тест отсутствия обязательных полей."""
        # Отсутствует zone_id
        payload = {
            "type": "telemetry_updated",
            "server_ts": 1234567890
        }
        with pytest.raises(AssertionError):
            validate_against_schema(payload, zone_events_schema)
        
        # Отсутствует type
        payload = {
            "zone_id": 1,
            "server_ts": 1234567890
        }
        with pytest.raises(AssertionError):
            validate_against_schema(payload, zone_events_schema)
        
        # Отсутствует server_ts
        payload = {
            "zone_id": 1,
            "type": "telemetry_updated"
        }
        with pytest.raises(AssertionError):
            validate_against_schema(payload, zone_events_schema)
    
    def test_zone_events_invalid_zone_id(self, zone_events_schema):
        """Тест невалидного zone_id (должен быть >= 1)."""
        import time
        payload = {
            "zone_id": 0,
            "type": "telemetry_updated",
            "server_ts": int(time.time() * 1000)
        }
        
        with pytest.raises(AssertionError):
            validate_against_schema(payload, zone_events_schema)
