# Protocol Contract Tests

Контрактные тесты для протокола обмена данными между компонентами системы.

## Цель

Обеспечить совместимость payload'ов между:
- Узлами (firmware) → History-logger
- History-logger → Laravel
- Laravel → Frontend клиенты

Любое изменение payload должно ломать CI, а не прод.

## JSON-Schema файлы

Все схемы находятся в `backend/services/common/schemas/`:

1. **telemetry.schema.json** - Payload телеметрии от узлов
2. **command.schema.json** - Payload команды к узлам
3. **command_response.schema.json** - Payload ответа на команду
4. **status.schema.json** - Payload статус-сообщений
5. **heartbeat.schema.json** - Payload heartbeat
6. **error.schema.json** / **error_alert.schema.json** - Payload ошибки/алерта

## Запуск тестов

### Локально

```bash
# Из корня проекта
make protocol-check

# Проверка паритета backend source <-> firmware mirror
./tools/check_runtime_schema_parity.sh

# Или напрямую
cd backend/services/common/schemas
bash run_protocol_check.sh

# Или через pytest
cd backend/services
PYTHONPATH=$(pwd):$(pwd)/history-logger:$(pwd)/common pytest services/common/schemas/test_protocol_contracts.py -v
```

### В CI

Добавьте в ваш CI pipeline:

```yaml
# Пример для GitHub Actions
protocol-check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - run: |
        pip install jsonschema pytest pydantic
        make protocol-check
```

## Структура тестов

Тесты проверяют:

1. **JSON-Schema валидация** - все payload'ы должны соответствовать JSON-schema
2. **Pydantic валидация** - payload'ы должны проходить валидацию через Pydantic модели
3. **Fixtures** - предопределенные payload'ы для различных сценариев
4. **Roundtrip тесты** - полный цикл создания команды → валидация → ответ

## Добавление новых тестов

1. Добавьте fixture в `fixtures_extended.py` или `fixtures.py`
2. Добавьте тест в `test_protocol_contracts.py`
3. Убедитесь, что тест проходит валидацию через JSON-schema и Pydantic

## Обновление схем

При изменении payload'ов:

1. Обновите схему только в `backend/services/common/schemas` (source of truth)
2. Синхронизируйте зеркало: `./tools/sync_runtime_schemas.sh`
3. Обновите Pydantic модель (если нужно)
4. Обновите fixtures
5. Запустите тесты: `make protocol-check`
6. Если тесты падают - исправьте payload'ы или схемы

## Примеры использования

### Валидация payload в коде

```python
from common.schemas import Command, CommandResponse
from pathlib import Path
import json
import jsonschema

# Загрузка схемы
schema_path = Path("backend/services/common/schemas/command.json")
with open(schema_path) as f:
    schema = json.load(f)

# Валидация через JSON-schema
payload = {"cmd_id": "cmd-123", "cmd": "dose", "params": {"ml": 1.2}, "ts": 1234567890, "sig": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
jsonschema.validate(instance=payload, schema=schema)

# Валидация через Pydantic
cmd = Command(**payload)
```

## Troubleshooting

### Импорт TelemetryPayloadModel не работает

Убедитесь, что PYTHONPATH настроен правильно:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend/services:$(pwd)/backend/services/history-logger"
```

### Тесты падают после изменения payload

1. Проверьте, что JSON-schema соответствует новому формату
2. Обновите fixtures если нужно
3. Убедитесь, что Pydantic модели обновлены
