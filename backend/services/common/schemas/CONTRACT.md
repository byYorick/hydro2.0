# Единый контракт команд (Protocol/Contracts Agent)

## Обзор

Единый контракт команд обеспечивает согласованность форматов и статусов команд во всех сервисах системы. Это устраняет рассинхрон между различными компонентами и гарантирует, что любой сервис, читающий `command_response`, понимает единый формат.

## Архитектура

### Компоненты

1. **JSON схемы** (`schemas/command.json`, `schemas/command_response.json`)
   - Валидация формата команд и ответов
   - Документация структуры данных
   - Использование в тестах

2. **Python модели** (`schemas.py`)
   - `Command` - единый контракт команды
   - `CommandResponse` - единый контракт ответа
   - Legacy модели для обратной совместимости

3. **Laravel модель** (`app/Models/Command.php`)
   - Поддержка новых статусов
   - Валидация через CHECK constraint в БД
   - Методы для проверки состояния команды

4. **База данных**
   - State-machine статусов: `QUEUED/SENT/ACCEPTED/DONE/FAILED/TIMEOUT/SEND_FAILED`
   - Дополнительные поля: `error_code`, `error_message`, `result_code`, `duration_ms`

## Формат команды (Command)

### Структура

```json
{
  "cmd_id": "cmd-abc123",
  "cmd": "dose",
  "params": { "ml": 1.2 },
  "deadline_ms": 1737355112000,
  "attempt": 1,
  "ts": 1737355112000
}
```

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `cmd_id` | string | Да | Уникальный идентификатор команды (UUID или correlation_id) |
| `cmd` | string | Да | Тип команды (например: dose, run_pump, calibrate_ph) |
| `ts` | integer | Да | Unix timestamp создания команды в миллисекундах |
| `params` | object | Нет | Параметры команды (объект) |
| `deadline_ms` | integer | Нет | Дедлайн выполнения команды в миллисекундах |
| `attempt` | integer | Нет | Номер попытки выполнения (по умолчанию 1) |
| `correlation_id` | string | Нет | Альтернативное поле для cmd_id (обратная совместимость) |

### Примеры использования

#### Python

```python
from schemas import Command

# Создание команды
command = Command.create(
    cmd="dose",
    params={"ml": 1.2, "channel": "pump_nutrient"},
    deadline_ms=int(time.time() * 1000) + 30000  # 30 секунд дедлайн
)

# Конвертация в JSON
command_json = command.model_dump_json()
```

#### Laravel

```php
use App\Models\Command;

$command = Command::create([
    'cmd_id' => Str::uuid()->toString(),
    'cmd' => 'dose',
    'params' => ['ml' => 1.2],
    'status' => Command::STATUS_QUEUED,
]);
```

## Формат ответа (CommandResponse)

### Структура

```json
{
  "cmd_id": "cmd-abc123",
  "status": "DONE",
  "result_code": 0,
  "ts": 1737355113000,
  "duration_ms": 1000
}
```

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `cmd_id` | string | Да | Идентификатор команды, на которую приходит ответ |
| `status` | string | Да | Статус выполнения: `ACCEPTED` \| `DONE` \| `FAILED` |
| `ts` | integer | Да | Unix timestamp ответа в миллисекундах |
| `result_code` | integer | Нет | Код результата (0 = успех, >0 = код ошибки) |
| `error_code` | string | Нет | Символический код ошибки (например: TIMEOUT, INVALID_PARAMS) |
| `error_message` | string | Нет | Человекочитаемое сообщение об ошибке |
| `duration_ms` | integer | Нет | Длительность выполнения команды в миллисекундах |

### Статусы

- **ACCEPTED** - команда принята узлом и начала выполняться
- **DONE** - команда успешно выполнена
- **FAILED** - команда завершилась с ошибкой

### Примеры использования

#### Python

```python
from schemas import CommandResponse

# Успешное выполнение
response = CommandResponse.done(
    cmd_id="cmd-abc123",
    duration_ms=1000
)

# Ошибка выполнения
response = CommandResponse.failed(
    cmd_id="cmd-abc123",
    error_code="TIMEOUT",
    error_message="Command execution timeout",
    result_code=1
)
```

## State-machine статусов в БД

### Статусы

| Статус | Описание | Переходы |
|--------|----------|----------|
| `QUEUED` | Команда поставлена в очередь | → SENT, SEND_FAILED |
| `SENT` | Команда отправлена в MQTT | → ACCEPTED, TIMEOUT, SEND_FAILED |
| `ACCEPTED` | Команда принята узлом | → DONE, FAILED, TIMEOUT |
| `DONE` | Команда успешно выполнена | (конечное состояние) |
| `FAILED` | Команда завершилась с ошибкой | (конечное состояние) |
| `TIMEOUT` | Команда не получила ответа в срок | (конечное состояние) |
| `SEND_FAILED` | Ошибка при отправке команды | (конечное состояние) |

### Конечные состояния

Команда всегда завершается в одно из конечных состояний:
- `DONE` - успешное выполнение
- `FAILED` - ошибка выполнения
- `TIMEOUT` - таймаут
- `SEND_FAILED` - ошибка отправки

### Валидация в БД

PostgreSQL CHECK constraint гарантирует, что статус может быть только одним из допустимых значений:

```sql
ALTER TABLE commands 
ADD CONSTRAINT commands_status_check 
CHECK (status IN ('QUEUED', 'SENT', 'ACCEPTED', 'DONE', 'FAILED', 'TIMEOUT', 'SEND_FAILED'));
```

## DoD (Definition of Done)

✅ **100% команд имеют cmd_id** - все команды должны иметь уникальный идентификатор

✅ **Всегда завершаются в конечное состояние** - команда не может остаться в промежуточном статусе

✅ **Единый формат для всех сервисов** - любой сервис, читающий `command_response`, понимает единый формат

✅ **JSON схемы и валидация** - схемы в `backend/services/common/schemas/` для валидации

✅ **Тестовые fixtures** - fixtures в `schemas/fixtures.py` для тестирования

✅ **Документация** - полная документация контракта и примеры использования

## Миграция со старых форматов

### Старые статусы → Новые статусы

| Старый | Новый |
|--------|-------|
| `pending` | `QUEUED` |
| `sent` | `SENT` |
| `ack` | `DONE` |
| `failed` | `FAILED` |
| `timeout` | `TIMEOUT` |

### Обратная совместимость

Legacy модели (`CommandRequest`, `LegacyCommandResponse`) обеспечивают обратную совместимость со старым кодом. Постепенно все сервисы должны быть переведены на единый контракт.

## Тестирование

### Использование fixtures

```python
from schemas.fixtures import (
    create_command_fixture,
    create_command_response_fixture,
    FIXTURE_COMMAND_DOSE,
    FIXTURE_RESPONSE_DONE
)

# Создание тестовой команды
command_data = create_command_fixture(
    cmd="dose",
    params={"ml": 1.2}
)

# Создание тестового ответа
response_data = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="DONE",
    duration_ms=1000
)
```

### Валидация по JSON схеме

```python
import jsonschema
import json

with open('schemas/command.json') as f:
    schema = json.load(f)

jsonschema.validate(instance=command_data, schema=schema)
```

## См. также

- [JSON схемы](README.md)
- [Тестовые fixtures](fixtures.py)
- [Python модели](../schemas.py)
- [Laravel модель](../../laravel/app/Models/Command.php)
