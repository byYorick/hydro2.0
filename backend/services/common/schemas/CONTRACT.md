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

3. **Laravel модель** (`app/Models/Command.php`)
   - Поддержка новых статусов
   - Валидация через CHECK constraint в БД
   - Методы для проверки состояния команды

4. **База данных**
   - State-machine статусов: `QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED`

## Формат команды (Command)

### Структура

```json
{
  "cmd_id": "cmd-abc123",
  "cmd": "dose",
  "params": { "ml": 1.2 },
  "ts": 1737355112,
  "sig": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `cmd_id` | string | Да | Уникальный идентификатор команды (UUID) |
| `cmd` | string | Да | Тип команды (dose, run_pump, set_relay, set_pwm, test_sensor, restart) |
| `params` | object | Да | Параметры команды (объект) |
| `ts` | integer | Да | Unix timestamp создания команды в секундах |
| `sig` | string | Да | HMAC-SHA256 подпись команды (hex, 64 символа) |

### Примеры использования

#### Python

```python
from schemas import Command

# Создание команды
command = Command.create(
    cmd="dose",
    params={"ml": 1.2},
    sig="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
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
  "ts": 1737355113000,
  "details": {
    "duration_ms": 1000
  }
}
```

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `cmd_id` | string | Да | Идентификатор команды, на которую приходит ответ |
| `status` | string | Да | Статус выполнения: `ACK` \| `DONE` \| `ERROR` \| `INVALID` \| `BUSY` \| `NO_EFFECT` |
| `ts` | integer | Да | Unix timestamp ответа в миллисекундах |
| `details` | object | Нет | Дополнительные детали ответа |

### Статусы

- **ACK** - команда принята узлом и начала выполняться
- **DONE** - команда успешно выполнена
- **ERROR** - команда завершилась с ошибкой
- **INVALID** - команда отклонена из-за параметров/валидации
- **BUSY** - узел занят (временная недоступность)
- **NO_EFFECT** - команда не изменила состояние

### Примеры использования

#### Python

```python
from schemas import CommandResponse

# Успешное выполнение
response = CommandResponse.done(
    cmd_id="cmd-abc123",
    details={"duration_ms": 1000}
)

# Ошибка выполнения
response = CommandResponse.error(
    cmd_id="cmd-abc123",
    details={"error_code": "TIMEOUT", "error_message": "Command execution timeout"}
)
```

## State-machine статусов в БД

### Статусы

| Статус | Описание | Переходы |
|--------|----------|----------|
| `QUEUED` | Команда поставлена в очередь | → SENT, SEND_FAILED |
| `SENT` | Команда отправлена в MQTT | → ACK, TIMEOUT, SEND_FAILED |
| `ACK` | Команда принята узлом | → DONE, NO_EFFECT, ERROR, INVALID, BUSY, TIMEOUT |
| `DONE` | Команда успешно выполнена | (конечное состояние) |
| `NO_EFFECT` | Команда выполнена без эффекта | (конечное состояние) |
| `ERROR` | Команда завершилась с ошибкой | (конечное состояние) |
| `INVALID` | Команда отклонена из-за параметров/валидации | (конечное состояние) |
| `BUSY` | Узел занят (временная недоступность) | (конечное состояние) |
| `TIMEOUT` | Команда не получила ответа в срок | (конечное состояние) |
| `SEND_FAILED` | Ошибка при отправке команды | (конечное состояние) |

### Конечные состояния

Команда всегда завершается в одно из конечных состояний:
- `DONE` - успешное выполнение
- `NO_EFFECT` - выполнение без эффекта
- `ERROR` - ошибка выполнения
- `INVALID` - ошибка валидации
- `BUSY` - узел занят
- `TIMEOUT` - таймаут
- `SEND_FAILED` - ошибка отправки

### Валидация в БД

PostgreSQL CHECK constraint гарантирует, что статус может быть только одним из допустимых значений:

```sql
ALTER TABLE commands
ADD CONSTRAINT commands_status_check
CHECK (status IN ('QUEUED', 'SENT', 'ACK', 'DONE', 'NO_EFFECT', 'ERROR', 'INVALID', 'BUSY', 'TIMEOUT', 'SEND_FAILED'));
```

## DoD (Definition of Done)

✅ **100% команд имеют cmd_id** - все команды должны иметь уникальный идентификатор

✅ **Всегда завершаются в конечное состояние** - команда не может остаться в промежуточном статусе

✅ **Единый формат для всех сервисов** - любой сервис, читающий `command_response`, понимает единый формат

✅ **JSON схемы и валидация** - схемы в `backend/services/common/schemas/` для валидации

✅ **Тестовые fixtures** - fixtures в `schemas/fixtures.py` для тестирования

✅ **Документация** - полная документация контракта и примеры использования

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
- [Laravel модель](../../../laravel/app/Models/Command.php)
