"""
Контрактные тесты для проверки совместимости payload'ов.

Проверяет соответствие всех fixtures JSON схемам.
CI падает при несовместимом payload - это основная цель тестов.
"""
import json
from pathlib import Path
from typing import Dict, Any, List

import jsonschema
import pytest
from jsonschema import validate, ValidationError

from common.telemetry_contracts import TelemetrySample

# Пути к схемам и fixtures
SCHEMAS_DIR = Path(__file__).parent
FIXTURES_DIR = SCHEMAS_DIR / "fixtures"
LARAVEL_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "laravel" / "resources" / "schemas"

# JSON Schema файлы
COMMAND_SCHEMA = SCHEMAS_DIR / "command.schema.json"
COMMAND_RESPONSE_SCHEMA = SCHEMAS_DIR / "command_response.schema.json"
TELEMETRY_SCHEMA = SCHEMAS_DIR / "telemetry.schema.json"
TELEMETRY_SAMPLE_SCHEMA = LARAVEL_SCHEMA_DIR / "telemetry_sample.schema.json"
ERROR_ALERT_SCHEMA = SCHEMAS_DIR / "error_alert.schema.json"
ZONE_EVENTS_SCHEMA = SCHEMAS_DIR / "zone_events.schema.json"


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """Загружает JSON из файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_schema(schema_path: Path) -> Dict[str, Any]:
    """Загружает JSON-schema из файла."""
    return load_json_file(schema_path)


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Валидирует данные против JSON-schema. Вызывает AssertionError при несовместимости."""
    try:
        validate(instance=data, schema=schema)
    except ValidationError as e:
        path_str = '.'.join(str(p) for p in e.path) if e.path else '<root>'
        raise AssertionError(
            f"Schema validation failed at '{path_str}': {e.message}\n"
            f"Failed value: {e.instance}\n"
            f"Schema path: {list(e.schema_path)}"
        )


def get_fixture_files(pattern: str) -> List[Path]:
    """Возвращает список fixture файлов по паттерну."""
    return sorted(FIXTURES_DIR.glob(pattern))


class TestCommandContracts:
    """Контрактные тесты для command payload."""
    
    @pytest.fixture
    def command_schema(self):
        """Загружает схему command."""
        return load_schema(COMMAND_SCHEMA)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("command_*.json"))
    def test_command_fixture_validates(self, command_schema, fixture_file):
        """Проверяет, что все fixtures команд валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, command_schema)
    
    def test_command_minimal_payload(self, command_schema):
        """Тест минимального payload команды."""
        fixture = load_json_file(FIXTURES_DIR / "command_minimal.json")
        validate_against_schema(fixture, command_schema)
        
        # Проверяем обязательные поля
        assert "cmd_id" in fixture
        assert "cmd" in fixture
        assert "ts" in fixture
    
    def test_command_invalid_missing_required_fields(self, command_schema):
        """Тест, что схема отклоняет отсутствие обязательных полей."""
        # Отсутствует cmd_id
        invalid = {"cmd": "dose", "ts": 1234567890}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_schema)
        
        # Отсутствует cmd
        invalid = {"cmd_id": "cmd-123", "ts": 1234567890}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_schema)
        
        # Отсутствует ts
        invalid = {"cmd_id": "cmd-123", "cmd": "dose"}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_schema)
    
    def test_command_invalid_cmd_id_format(self, command_schema):
        """Тест, что схема отклоняет невалидный формат cmd_id."""
        invalid = {
            "cmd_id": "invalid cmd id with spaces!",
            "cmd": "dose",
            "ts": 1234567890
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_schema)


class TestCommandResponseContracts:
    """Контрактные тесты для command_response payload."""
    
    @pytest.fixture
    def command_response_schema(self):
        """Загружает схему command_response."""
        return load_schema(COMMAND_RESPONSE_SCHEMA)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("command_response_*.json"))
    def test_command_response_fixture_validates(self, command_response_schema, fixture_file):
        """Проверяет, что все fixtures ответов валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, command_response_schema)
    
    def test_command_response_invalid_status(self, command_response_schema):
        """Тест, что схема отклоняет невалидный статус."""
        invalid = {
            "cmd_id": "cmd-123",
            "status": "INVALID_STATUS",
            "ts": 1234567890
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_response_schema)
    
    def test_command_response_missing_required_fields(self, command_response_schema):
        """Тест, что схема отклоняет отсутствие обязательных полей."""
        # Отсутствует cmd_id
        invalid = {"status": "DONE", "ts": 1234567890}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_response_schema)
        
        # Отсутствует status
        invalid = {"cmd_id": "cmd-123", "ts": 1234567890}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_response_schema)
        
        # Отсутствует ts
        invalid = {"cmd_id": "cmd-123", "status": "DONE"}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, command_response_schema)


class TestTelemetryContracts:
    """Контрактные тесты для telemetry payload."""
    
    @pytest.fixture
    def telemetry_schema(self):
        """Загружает схему telemetry."""
        return load_schema(TELEMETRY_SCHEMA)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("telemetry_*.json"))
    def test_telemetry_fixture_validates(self, telemetry_schema, fixture_file):
        """Проверяет, что все fixtures телеметрии валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, telemetry_schema)
    
    def test_telemetry_minimal_payload(self, telemetry_schema):
        """Тест минимального payload телеметрии."""
        fixture = load_json_file(FIXTURES_DIR / "telemetry_minimal.json")
        validate_against_schema(fixture, telemetry_schema)
        
        # Проверяем обязательные поля
        assert "metric_type" in fixture
        assert "value" in fixture
    
    def test_telemetry_missing_required_fields(self, telemetry_schema):
        """Тест, что схема отклоняет отсутствие обязательных полей."""
        # Отсутствует metric_type
        invalid = {"value": 6.5}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, telemetry_schema)
        
        # Отсутствует value
        invalid = {"metric_type": "PH"}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, telemetry_schema)
    
    def test_telemetry_invalid_metric_type(self, telemetry_schema):
        """Тест, что схема отклоняет пустой metric_type."""
        invalid = {
            "metric_type": "",
            "value": 6.5
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, telemetry_schema)


class TestTelemetrySampleContracts:
    """Contract tests for canonical telemetry samples."""

    @pytest.fixture
    def telemetry_sample_schema(self):
        """Load telemetry sample schema from Laravel resources."""
        return load_schema(TELEMETRY_SAMPLE_SCHEMA)

    def test_telemetry_sample_validates_schema_and_pydantic(self, telemetry_sample_schema):
        fixture = load_json_file(FIXTURES_DIR / "telemetry_sample_canonical.json")
        validate_against_schema(fixture, telemetry_sample_schema)
        TelemetrySample.model_validate(fixture)


class TestErrorAlertContracts:
    """Контрактные тесты для error/alert payload."""
    
    @pytest.fixture
    def error_alert_schema(self):
        """Загружает схему error_alert."""
        return load_schema(ERROR_ALERT_SCHEMA)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("error_*.json"))
    def test_error_fixture_validates(self, error_alert_schema, fixture_file):
        """Проверяет, что все fixtures ошибок валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, error_alert_schema)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("alert_*.json"))
    def test_alert_fixture_validates(self, error_alert_schema, fixture_file):
        """Проверяет, что все fixtures алертов валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, error_alert_schema)
    
    def test_error_minimal_payload(self, error_alert_schema):
        """Тест минимального payload ошибки."""
        fixture = load_json_file(FIXTURES_DIR / "error_minimal.json")
        validate_against_schema(fixture, error_alert_schema)
        
        # Проверяем обязательные поля
        assert "level" in fixture
        assert "component" in fixture
    
    def test_error_missing_required_fields(self, error_alert_schema):
        """Тест, что схема отклоняет отсутствие обязательных полей."""
        # Отсутствует level
        invalid = {"component": "sensor"}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, error_alert_schema)
        
        # Отсутствует component
        invalid = {"level": "ERROR"}
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, error_alert_schema)
    
    def test_error_invalid_level(self, error_alert_schema):
        """Тест, что схема отклоняет невалидный уровень ошибки."""
        invalid = {
            "level": "INVALID_LEVEL",
            "component": "sensor"
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, error_alert_schema)


class TestZoneEventsContracts:
    """Контрактные тесты для zone_events payload."""
    
    @pytest.fixture
    def zone_events_schema(self):
        """Загружает схему zone_events."""
        return load_schema(ZONE_EVENTS_SCHEMA)
    
    @pytest.mark.parametrize("fixture_file", get_fixture_files("zone_event_*.json"))
    def test_zone_event_fixture_validates(self, zone_events_schema, fixture_file):
        """Проверяет, что все fixtures событий зон валидны согласно схеме."""
        fixture = load_json_file(fixture_file)
        validate_against_schema(fixture, zone_events_schema)
    
    def test_zone_event_minimal_payload(self, zone_events_schema):
        """Тест минимального payload события зоны."""
        fixture = load_json_file(FIXTURES_DIR / "zone_event_minimal.json")
        validate_against_schema(fixture, zone_events_schema)
        
        # Проверяем обязательные поля
        assert "zone_id" in fixture
        assert "type" in fixture
        assert "server_ts" in fixture
    
    def test_zone_event_missing_required_fields(self, zone_events_schema):
        """Тест, что схема отклоняет отсутствие обязательных полей."""
        import time
        
        # Отсутствует zone_id
        invalid = {
            "type": "telemetry_updated",
            "server_ts": int(time.time() * 1000)
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, zone_events_schema)
        
        # Отсутствует type
        invalid = {
            "zone_id": 1,
            "server_ts": int(time.time() * 1000)
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, zone_events_schema)
        
        # Отсутствует server_ts
        invalid = {
            "zone_id": 1,
            "type": "telemetry_updated"
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, zone_events_schema)
    
    def test_zone_event_invalid_zone_id(self, zone_events_schema):
        """Тест, что схема отклоняет невалидный zone_id (должен быть >= 1)."""
        import time
        invalid = {
            "zone_id": 0,
            "type": "telemetry_updated",
            "server_ts": int(time.time() * 1000)
        }
        with pytest.raises(AssertionError):
            validate_against_schema(invalid, zone_events_schema)


class TestContractCompatibility:
    """Тесты совместимости контрактов между компонентами."""
    
    def test_all_fixtures_validate_against_schemas(self):
        """Интеграционный тест: все fixtures должны валидироваться против своих схем."""
        schema_fixture_mapping = {
            COMMAND_SCHEMA: get_fixture_files("command_*.json"),
            COMMAND_RESPONSE_SCHEMA: get_fixture_files("command_response_*.json"),
            TELEMETRY_SCHEMA: get_fixture_files("telemetry_*.json"),
            ERROR_ALERT_SCHEMA: get_fixture_files("error_*.json") + get_fixture_files("alert_*.json"),
            ZONE_EVENTS_SCHEMA: get_fixture_files("zone_event_*.json"),
        }
        
        for schema_path, fixture_files in schema_fixture_mapping.items():
            schema = load_schema(schema_path)
            for fixture_file in fixture_files:
                fixture = load_json_file(fixture_file)
                try:
                    validate_against_schema(fixture, schema)
                except AssertionError as e:
                    pytest.fail(
                        f"Fixture {fixture_file.name} failed validation against "
                        f"schema {schema_path.name}: {e}"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
