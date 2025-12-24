# Contract Fixtures

JSON fixtures для тестирования контрактов протокола.

## Структура

Каждый fixture соответствует одному payload типу и валидируется против соответствующей JSON схемы:

- `command_*.json` - команды (валидируются против `command.schema.json`)
- `command_response_*.json` - ответы на команды (валидируются против `command_response.schema.json`)
- `telemetry_*.json` - телеметрия (валидируются против `telemetry.schema.json`)
- `error_*.json` - ошибки (валидируются против `error_alert.schema.json`)
- `alert_*.json` - алерты (валидируются против `error_alert.schema.json`)
- `zone_event_*.json` - события зон (валидируются против `zone_events.schema.json`)

## Использование

Fixtures используются автоматически в `test_contracts.py`:

```python
# Все fixtures команд валидируются автоматически
pytest common/schemas/test_contracts.py::TestCommandContracts -v
```

## Добавление новых fixtures

1. Создайте новый JSON файл в этой директории
2. Убедитесь, что он соответствует схеме (запустите тесты)
3. Тесты автоматически обнаружат новый fixture через `get_fixture_files()`

## Формат

Все fixtures должны быть валидным JSON и соответствовать соответствующим схемам из родительской директории (`*.schema.json`).

