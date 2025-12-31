# SQL Security Guidelines

Этот документ описывает правила безопасности при работе с SQL запросами в Python сервисах.

## 1. Общие принципы

### ✅ ВСЕГДА используйте параметризованные запросы

**Правильно:**
```python
rows = await fetch(
    "SELECT * FROM zones WHERE id = $1",
    zone_id
)
```

**Неправильно:**
```python
# ❌ ОПАСНО: SQL Injection уязвимость
rows = await fetch(f"SELECT * FROM zones WHERE id = {zone_id}")
```

### ✅ Используйте asyncpg параметры ($1, $2, ...)

Все значения должны передаваться через параметры, а не встраиваться в строку запроса.

```python
await execute(
    "INSERT INTO telemetry_samples (sensor_id, ts, value) VALUES ($1, $2, $3)",
    sensor_id, timestamp, value
)
```

## 2. Динамическое построение запросов

### ✅ Whitelist для имен полей и таблиц

Если необходимо динамически строить запросы (например, UPDATE с переменным набором полей), используйте whitelist:

```python
# Whitelist разрешенных полей
ALLOWED_FIELDS = {
    'uptime_seconds': 'uptime',
    'free_heap_bytes': ('free_heap', 'free_heap_bytes'),
    'rssi': 'rssi',
}

# Строим список обновлений только из разрешенных полей
updates = []
params = [node_uid]
param_index = 1

if uptime is not None:
    updates.append(f"uptime_seconds=${param_index + 1}")  # Имя поля жестко задано
    params.append(int(uptime))  # Значение через параметр
    param_index += 1

query = f"UPDATE nodes SET {', '.join(updates)} WHERE uid=$1"
await execute(query, *params)
```

### ❌ НИКОГДА не используйте пользовательский ввод для имен полей/таблиц

```python
# ❌ ОПАСНО
field_name = user_input  # Может содержать SQL injection
query = f"UPDATE nodes SET {field_name} = $1 WHERE id = $2"
```

## 3. Проверка типов данных

### ✅ Валидируйте и приводите типы перед запросом

```python
try:
    zone_id_int = int(zone_id)
except (ValueError, TypeError):
    logger.error(f"Invalid zone_id: {zone_id}")
    return

rows = await fetch("SELECT * FROM zones WHERE id = $1", zone_id_int)
```

## 4. Работа с JSON полями

### ✅ Используйте параметризованные запросы для JSON

```python
details_json = json.dumps(details) if details else None
await execute(
    "INSERT INTO zone_events (zone_id, type, details) VALUES ($1, $2, $3)",
    zone_id, event_type, details_json
)
```

### ✅ Используйте JSON операторы PostgreSQL безопасно

```python
# Поиск в JSON поле
rows = await fetch(
    """
    SELECT * FROM zone_events
    WHERE details->>'correction_type' LIKE $1
    """,
    pattern  # pattern передается как параметр
)
```

## 5. Массивы и списки

### ✅ Используйте ANY() для массивов

```python
rows = await fetch(
    "SELECT * FROM nodes WHERE uid = ANY($1::text[])",
    node_uids  # Список передается как параметр
)
```

## 6. Примеры безопасных паттернов

### Пример 1: Batch INSERT

```python
values_list = []
params_list = []
param_index = 1

for sample in samples:
    values_list.append(
        f"(${param_index}, ${param_index + 1}, ${param_index + 2})"
    )
    params_list.extend([sample.sensor_id, sample.ts, sample.value])
    param_index += 3

query = f"""
    INSERT INTO telemetry_samples (sensor_id, ts, value)
    VALUES {', '.join(values_list)}
"""
await execute(query, *params_list)
```

### Пример 2: Динамический UPDATE с whitelist

```python
ALLOWED_UPDATE_FIELDS = ['status', 'last_seen_at']

updates = []
params = []
param_index = 1

if 'status' in data:
    updates.append(f"status=${param_index}")
    params.append(data['status'])
    param_index += 1

if updates:
    query = f"UPDATE nodes SET {', '.join(updates)} WHERE id = ${param_index}"
    params.append(node_id)
    await execute(query, *params)
```

## 7. Аудит безопасности

### Проверочный список

- [ ] Все значения передаются через параметры ($1, $2, ...)
- [ ] Нет f-строк или конкатенации строк для SQL запросов
- [ ] Имена полей и таблиц берутся из whitelist, а не из пользовательского ввода
- [ ] Типы данных валидируются перед запросом
- [ ] JSON данные сериализуются через `json.dumps()` перед передачей
- [ ] Массивы передаются через `ANY($1::type[])`

## 8. Инструменты для проверки

### Статический анализ

Используйте `grep` для поиска потенциально опасных паттернов:

```bash
# Поиск f-строк в SQL запросах
grep -r "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE" backend/services

# Поиск конкатенации строк
grep -r "%.*SELECT\|%d.*SELECT\|+.*SELECT" backend/services
```

### Тестирование

Создавайте unit-тесты, которые проверяют безопасность запросов:

```python
async def test_sql_injection_protection():
    """Проверка защиты от SQL injection."""
    malicious_input = "1'; DROP TABLE zones; --"
    
    # Запрос должен обработать это безопасно
    rows = await fetch("SELECT * FROM zones WHERE id = $1", malicious_input)
    # Не должно произойти DROP TABLE
```

## 9. Ресурсы

- [OWASP SQL Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/current/)
- [PostgreSQL Parameterized Queries](https://www.postgresql.org/docs/current/sql-prepare.html)

---

**Важно:** Если вы нашли потенциальную уязвимость SQL injection, немедленно сообщите об этом и исправьте её, используя параметризованные запросы.
