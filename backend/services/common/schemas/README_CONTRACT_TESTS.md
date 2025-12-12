# Контрактные тесты и Chaos Suite

## Описание

Набор тестов для проверки совместимости протокола обмена данными и устойчивости системы к сбоям.

## Структура тестов

### 1. Контрактные тесты (test_protocol_contracts.py)

Проверяют JSON схемы для всех типов payload'ов:

- **telemetry** - телеметрия от узлов
- **command** - команды к узлам
- **command_response** - ответы на команды
- **alert** - алерты и ошибки
- **zone_events** - события зон (Zone Event Ledger)

Каждый тест проверяет:
- Валидность минимального payload (только обязательные поля)
- Валидность полного payload (все поля)
- Отклонение невалидных payload'ов
- Отсутствие обязательных полей

### 2. Chaos тесты (test_chaos.py)

Проверяют поведение системы при сбоях:

- **MQTT down** - недоступность MQTT брокера
- **Laravel down** - недоступность Laravel API
- **DB read-only** - база данных в режиме только чтения
- **Burst telemetry** - обработка большого количества телеметрии

### 3. Авто-проверка WS событий (test_websocket_events.py)

Проверяет, что:

- Все WebSocket события имеют `event_id`
- Все WS события попадают в `zone_events`
- `event_id` из WS события совпадает с `ws_event_id` в `zone_events`

## Запуск тестов

### Локально

```bash
cd backend/services
pip install -r requirements-test.txt

# Все контрактные тесты
pytest common/schemas/test_protocol_contracts.py -v

# Chaos тесты
pytest common/schemas/test_chaos.py -v

# Авто-проверка WS событий
pytest common/schemas/test_websocket_events.py -v

# Все тесты через скрипт
cd common/schemas
bash run_contract_tests.sh
```

### В CI

Тесты автоматически запускаются в GitHub Actions при:
- Изменении файлов в `backend/services/common/schemas/**`
- Изменении файлов в `backend/services/history-logger/**`
- Изменении файлов в `backend/laravel/app/Http/Controllers/**`
- Push в `main` или `develop` ветки
- Pull Request в `main` или `develop` ветки

## JSON схемы

Все схемы находятся в `backend/services/common/schemas/`:

- `telemetry.json` - схема телеметрии
- `command.json` - схема команды
- `command_response.json` - схема ответа на команду
- `error_alert.json` - схема ошибки/алерта
- `zone_events.json` - схема события зоны

## Требования

- Python 3.8+
- pytest
- jsonschema
- pydantic
- httpx (для chaos тестов)

## DoD (Definition of Done)

✅ Любая несовместимость ломает CI

Это означает, что:
1. Все контрактные тесты должны проходить
2. Любое изменение схемы должно быть отражено в тестах
3. Любое нарушение контракта должно приводить к падению CI
4. Chaos тесты проверяют устойчивость системы к сбоям

## Примеры использования

### Проверка валидности payload

```python
from common.schemas.test_protocol_contracts import load_schema, validate_against_schema

telemetry_schema = load_schema("telemetry.json")
payload = {"metric_type": "PH", "value": 6.5}
validate_against_schema(payload, telemetry_schema)
```

### Проверка WS события

```python
# WS событие должно иметь event_id
assert "event_id" in ws_event
assert isinstance(ws_event["event_id"], int)

# zone_events должен содержать ws_event_id
assert "ws_event_id" in zone_event["payload_json"]
assert zone_event["payload_json"]["ws_event_id"] == ws_event["event_id"]
```

## Отладка

Если тесты падают:

1. Проверьте JSON схемы на валидность
2. Проверьте, что payload соответствует схеме
3. Проверьте логи CI для деталей ошибки
4. Убедитесь, что все зависимости установлены

## Расширение тестов

При добавлении нового типа payload:

1. Создайте JSON схему в `schemas/`
2. Добавьте тесты в `test_protocol_contracts.py`
3. Добавьте fixtures в `fixtures_extended.py` (если нужно)
4. Обновите CI workflow (если нужно)

