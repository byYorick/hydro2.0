# Защита переходов статусов команд от гонок (Race Conditions)

## Проблема P0

Функции обновления статусов команд должны защищать от гонок (race conditions), чтобы не откатывать статус назад.

### Пример проблемы

Если `ACK` или `DONE` прилетели быстрее, чем `mark_command_sent()` записался в БД, то без проверки статуса команда может откатиться назад:
- Команда: `QUEUED` → `ACK` (быстро)
- Затем: `mark_command_sent()` пытается установить `SENT`
- Без проверки: команда откатывается `ACK` → `SENT` ❌

## Решение

Все функции обновления статусов проверяют текущий статус перед обновлением.

## State-machine переходов

### Допустимые переходы

```
QUEUED → SENT → ACK → DONE
                 ↓
              NO_EFFECT
                 ↓
              ERROR
                 ↓
              INVALID
                 ↓
              BUSY
```

Примечание: терминальные статусы могут приходить без ACK, поэтому обновления разрешены из `QUEUED/SENT/ACK`.
ACK является опциональным, а DONE/NO_EFFECT/ERROR/INVALID/BUSY могут приходить напрямую.

### Защищенные функции

#### `mark_command_sent(cmd_id)`

**Защита:** `WHERE status = 'QUEUED'`

**Логика:**
- Обновляет только из `QUEUED`
- Не обновляет если команда уже в `SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY`

**Использование:**
```python
# Обычная отправка
await mark_command_sent(cmd_id)
```

#### `mark_command_ack(cmd_id)`

**Защита:** `WHERE status IN ('QUEUED','SENT')`

**Логика:**
- Обновляет только из начальных статусов
- Не обновляет если команда уже в `ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY`

#### `mark_command_done(cmd_id, duration_ms, result_code)`

**Защита:** `WHERE status IN ('QUEUED','SENT','ACK')`

**Логика:**
- Обновляет только из промежуточных статусов
- Не обновляет если команда уже в конечном состоянии (`DONE/NO_EFFECT/ERROR/INVALID/BUSY`)

#### `mark_command_no_effect(cmd_id, duration_ms)`

**Защита:** `WHERE status IN ('QUEUED','SENT','ACK')`

**Логика:**
- Обновляет только из промежуточных статусов
- Не обновляет если команда уже в конечном состоянии

#### `mark_command_failed(cmd_id, error_code, error_message, result_code)`

**Статус:** `ERROR`

**Защита:** `WHERE status IN ('QUEUED','SENT','ACK')`

**Логика:**
- Обновляет только из промежуточных статусов
- Не обновляет если команда уже в конечном состоянии

#### `mark_command_invalid(cmd_id, error_code, error_message, result_code)`

**Статус:** `INVALID`

**Защита:** `WHERE status IN ('QUEUED','SENT','ACK')`

#### `mark_command_busy(cmd_id, error_code, error_message, result_code)`

**Статус:** `BUSY`

**Защита:** `WHERE status IN ('QUEUED','SENT','ACK')`

## Правила защиты

1. **Всегда проверяем текущий статус** перед обновлением
2. **Не обновляем конечные состояния** (`DONE`, `NO_EFFECT`, `ERROR`, `INVALID`, `BUSY`)
3. **Разрешаем только допустимые переходы** согласно state-machine
4. **Используем `IN (...)` для множественных допустимых статусов**

## Примеры правильного использования

### ✅ Правильно

```python
# Команда создана со статусом QUEUED
cmd_id = new_command_id()

# Отправка - обновит только если QUEUED
await mark_command_sent(cmd_id)

# Узел принял - обновит только если QUEUED или SENT
await mark_command_ack(cmd_id)

# Команда выполнена - обновит только если QUEUED/SENT/ACK
await mark_command_done(cmd_id, duration_ms=1000)
```

### ❌ Неправильно (устаревший код)

```python
# БЕЗ ЗАЩИТЫ - может откатить статус назад
UPDATE commands SET status='SENT' WHERE cmd_id=$1
```

## Тестирование

Для проверки защиты от гонок можно использовать:

```python
# Симуляция гонки: команда уже в ACK
await execute("UPDATE commands SET status='ACK' WHERE cmd_id=$1", cmd_id)

# Попытка откатить назад - не должна сработать
await mark_command_sent(cmd_id)

# Проверка: статус должен остаться ACK
rows = await fetch("SELECT status FROM commands WHERE cmd_id=$1", cmd_id)
assert rows[0]["status"] == "ACK"  # Не должен быть SENT
```
