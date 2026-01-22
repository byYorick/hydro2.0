# JSON Schemas для единого контракта команд

Этот каталог содержит JSON схемы для единого контракта команд в системе.

## Файлы

- `command.json` - Схема для команды (Command)
- `command_response.json` - Схема для ответа на команду (CommandResponse)
- `fixtures.py` - Тестовые fixtures для команд и ответов
- `CONTRACT.md` - Полная документация единого контракта
- `README.md` - Этот файл

## Использование

Эти схемы используются для:
1. Валидации команд и ответов в Python сервисах
2. Генерации документации
3. Тестирования (fixtures)
4. Обеспечения единообразия форматов между сервисами

## Формат команды (Command)

```json
{
  "cmd_id": "cmd-abc123",
  "cmd": "dose",
  "params": { "ml": 1.2 },
  "ts": 1737355112,
  "sig": "deadbeef"
}
```

**Обязательные поля:**
- `cmd_id` - уникальный идентификатор команды
- `cmd` - тип команды
- `params` - параметры команды (объект)
- `ts` - timestamp создания (секунды)
- `sig` - HMAC подпись

## Формат ответа (CommandResponse)

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

**Обязательные поля:**
- `cmd_id` - идентификатор команды
- `status` - статус (ACK|DONE|ERROR|INVALID|BUSY|NO_EFFECT)
- `ts` - timestamp ответа

**Опциональные поля:**
- `details` - дополнительные детали ответа

## Статусы в БД

State-machine статусов в базе данных:
- `QUEUED` - команда поставлена в очередь
- `SENT` - команда отправлена в MQTT
- `ACK` - команда принята узлом
- `DONE` - команда успешно выполнена
- `NO_EFFECT` - команда выполнена без эффекта
- `ERROR` - команда завершилась с ошибкой
- `INVALID` - команда отклонена из-за параметров/валидации
- `BUSY` - узел занят (временная недоступность)
- `TIMEOUT` - команда не получила ответа в срок
- `SEND_FAILED` - ошибка при отправке команды

## Валидация

Для валидации JSON по схемам можно использовать:

```python
import jsonschema
import json

with open('schemas/command.json') as f:
    schema = json.load(f)
    
jsonschema.validate(instance=command_data, schema=schema)
```
