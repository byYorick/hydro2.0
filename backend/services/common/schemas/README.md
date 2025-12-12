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
  "deadline_ms": 1737355112000,
  "attempt": 1,
  "ts": 1737355112000
}
```

**Обязательные поля:**
- `cmd_id` - уникальный идентификатор команды
- `cmd` - тип команды
- `ts` - timestamp создания

**Опциональные поля:**
- `correlation_id` - альтернативное поле для cmd_id (обратная совместимость)
- `params` - параметры команды (объект)
- `deadline_ms` - дедлайн выполнения
- `attempt` - номер попытки (по умолчанию 1)

## Формат ответа (CommandResponse)

```json
{
  "cmd_id": "cmd-abc123",
  "status": "DONE",
  "result_code": 0,
  "ts": 1737355113000,
  "duration_ms": 1000
}
```

**Обязательные поля:**
- `cmd_id` - идентификатор команды
- `status` - статус (ACCEPTED|DONE|FAILED)
- `ts` - timestamp ответа

**Опциональные поля:**
- `result_code` - код результата (0 = успех)
- `error_code` - символический код ошибки
- `error_message` - сообщение об ошибке
- `duration_ms` - длительность выполнения

## Статусы в БД

State-machine статусов в базе данных:
- `QUEUED` - команда поставлена в очередь
- `SENT` - команда отправлена в MQTT
- `ACCEPTED` - команда принята узлом
- `DONE` - команда успешно выполнена
- `FAILED` - команда завершилась с ошибкой
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
