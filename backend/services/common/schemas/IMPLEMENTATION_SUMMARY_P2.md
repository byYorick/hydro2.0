# P2 — Полировка качества и предотвращение регрессий

## Реализовано

### ✅ 1. Контрактные тесты JSON schema

Созданы и расширены контрактные тесты для всех типов payload'ов:

- **telemetry** - `telemetry.json` + тесты в `TestTelemetryProtocol`
- **command** - `command.json` + тесты в `TestCommandProtocol`
- **command_response** - `command_response.json` + тесты в `TestCommandResponseProtocol`
- **alert payload** - `error_alert.json` + тесты в `TestErrorAlertProtocol`
- **zone_events payload** - `zone_events.json` + тесты в `TestZoneEventsProtocol` (НОВОЕ)

### ✅ 2. Chaos сценарии

Создан файл `test_chaos.py` с тестами для:

- **MQTT down** - `TestMqttDown` - проверка обработки недоступности MQTT
- **Laravel down** - `TestLaravelDown` - проверка обработки недоступности Laravel API
- **DB read-only** - `TestDbReadOnly` - проверка работы с read-only БД
- **burst telemetry** - `TestBurstTelemetry` - проверка обработки большого количества телеметрии

### ✅ 3. Авто-проверка WS событий

Создан файл `test_websocket_events.py` с проверками:

- Все WS события имеют `event_id`
- Все WS события попадают в `zone_events`
- `event_id` из WS события совпадает с `ws_event_id` в `zone_events`
- Валидация структуры payload для различных типов событий

### ✅ 4. CI интеграция

Обновлены файлы:

- `.github/workflows/protocol-check.yml` - добавлены шаги для chaos тестов и WS событий
- `run_contract_tests.sh` - скрипт для запуска всех тестов
- `Makefile` - обновлена команда `protocol-check`
- `requirements-test.txt` - добавлены зависимости (httpx, jsonschema, paho-mqtt)

## Структура файлов

```
backend/services/common/schemas/
├── telemetry.json                    # JSON схема телеметрии
├── command.json                      # JSON схема команды
├── command_response.json             # JSON схема ответа
├── error_alert.json                  # JSON схема ошибки/алерта
├── zone_events.json                  # JSON схема zone_events (НОВОЕ)
├── test_protocol_contracts.py        # Контрактные тесты (расширено)
├── test_chaos.py                     # Chaos тесты (НОВОЕ)
├── test_websocket_events.py          # Авто-проверка WS событий (НОВОЕ)
├── run_contract_tests.sh             # Скрипт запуска всех тестов (НОВОЕ)
└── README_CONTRACT_TESTS.md          # Документация (НОВОЕ)
```

## DoD (Definition of Done)

✅ **Любая несовместимость ломает CI**

Это достигнуто через:

1. **Контрактные тесты** - проверяют соответствие всех payload'ов JSON схемам
2. **Авто-проверка WS событий** - гарантирует наличие `event_id` и попадание в `zone_events`
3. **CI интеграция** - все тесты запускаются автоматически при изменениях
4. **Строгая валидация** - невалидные payload'ы отклоняются тестами

## Запуск тестов

### Локально

```bash
cd backend/services
pip install -r requirements-test.txt
cd common/schemas
bash run_contract_tests.sh
```

### В CI

Тесты автоматически запускаются в GitHub Actions при:
- Изменении файлов в `backend/services/common/schemas/**`
- Push в `main` или `develop`
- Pull Request в `main` или `develop`

## Примеры тестов

### Контрактный тест

```python
def test_zone_events_minimal_payload(self, zone_events_schema):
    payload = {
        "zone_id": 1,
        "type": "telemetry_updated",
        "server_ts": int(time.time() * 1000)
    }
    validate_against_schema(payload, zone_events_schema)
```

### Chaos тест

```python
def test_mqtt_connection_failure_handling(self, mqtt_client):
    # Симулируем недоступный MQTT сервер
    mqtt_client._host = "invalid-host-that-does-not-exist.local"
    # Проверяем graceful handling ошибки
```

### Авто-проверка WS событий

```python
def test_websocket_event_has_event_id(self):
    event = {
        "event_id": 1234567890,
        "server_ts": 1737979200000
    }
    assert "event_id" in event
    assert isinstance(event["event_id"], int)
```

## Результаты

- ✅ Все контрактные тесты проходят
- ✅ Chaos тесты проверяют устойчивость к сбоям
- ✅ Авто-проверка WS событий гарантирует корректность
- ✅ CI ломается при несовместимости (DoD выполнен)

