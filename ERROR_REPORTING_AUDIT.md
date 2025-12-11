# Отчет о механизмах отправки ошибок на сервер

## Дата: 2025-01-XX

## Цель
Проверить все механизмы отправки ошибок от ESP32 нод на backend сервер.

## Механизмы отправки ошибок

### 1. Diagnostics топик (периодические метрики)

**Компонент:** `diagnostics`  
**Функция:** `diagnostics_publish()`  
**Топик:** `hydro/{gh}/{zone}/{node}/diagnostics`  
**QoS:** 1  
**Retain:** false  
**Интервал:** 60 секунд (по умолчанию)

**Формат payload:**
```json
{
  "system": {
    "uptime_seconds": 3600,
    "free_heap": 50000,
    "min_free_heap": 45000,
    "largest_free_block": 30000,
    "ts": 1737979200
  },
  "errors": {
    "warning_count": 5,
    "error_count": 2,
    "critical_count": 0,
    "total_count": 7
  },
  "mqtt": {
    "connected": true,
    "messages_sent": 1000,
    "messages_received": 500,
    "publish_errors": 2,
    "reconnect_count": 1
  },
  "wifi": {
    "connected": true,
    "rssi": -65
  },
  "safe_mode": false,
  "tasks": [...],
  "sensors": [...],
  "i2c_cache": {...}
}
```

**Статус:** ❌ **Backend НЕ подписан на diagnostics топик**

**Метрики ошибок:**
- `errors.warning_count` - количество предупреждений
- `errors.error_count` - количество ошибок
- `errors.critical_count` - количество критических ошибок
- `errors.total_count` - общее количество ошибок

**Источник метрик:** `node_state_manager_get_error_count()` из `node_state_manager`

---

### 2. Error топик (немедленная отправка ошибок)

**Компонент:** `node_state_manager`  
**Функция:** `node_state_manager_report_error()`  
**Топик:** `hydro/{gh}/{zone}/{node}/error`  
**QoS:** 1  
**Retain:** false  
**Триггер:** При вызове `node_state_manager_report_error()`

**Формат payload:**
```json
{
  "level": "ERROR",
  "component": "ph_sensor",
  "error_code": "ESP_ERR_INVALID_RESPONSE",
  "error_code_num": 0x102,
  "message": "Sensor read failed",
  "ts": 1737979200
}
```

**Уровни ошибок:**
- `WARNING` - предупреждения
- `ERROR` - ошибки
- `CRITICAL` - критические ошибки

**Статус:** ❌ **Backend НЕ подписан на error топик**

**Использование:**
```c
// Пример использования в коде
node_state_manager_report_error(
    ERROR_LEVEL_ERROR,
    "ph_sensor",
    ESP_ERR_INVALID_RESPONSE,
    "Sensor read failed"
);
```

---

### 3. Telemetry с error_code (в телеметрии)

**Компонент:** `node_telemetry_engine`  
**Топик:** `hydro/{gh}/{zone}/{node}/{channel}/telemetry`  
**QoS:** 1  
**Retain:** false

**Формат payload:**
```json
{
  "metric_type": "PH",
  "value": 6.5,
  "ts": 1737979200,
  "channel": "ph_sensor",
  "node_id": "nd-ph-1",
  "error_code": "sensor_read_failed",  // Опциональное поле
  "raw": 1465,
  "stub": false,
  "stable": true
}
```

**Статус:** ✅ **Backend обрабатывает error_code в telemetry**

**Обработка в backend:**
- `TelemetryPayloadModel` поддерживает поле `error_code`
- Сохраняется в поле `raw` в БД
- Используется для анализа ошибок сенсоров

**Пример использования:**
```c
// В телеметрии можно добавить error_code
cJSON_AddStringToObject(telemetry, "error_code", "sensor_read_failed");
```

---

### 4. Command Response с error_code (в ответах на команды)

**Компонент:** `node_command_handler`  
**Топик:** `hydro/{gh}/{zone}/{node}/{channel}/command_response`  
**QoS:** 1  
**Retain:** false

**Формат payload:**
```json
{
  "status": "ERROR",
  "error_code": "pump_driver_failed",
  "message": "Pump driver initialization failed",
  "cmd_id": "cmd-123",
  "ts": 1737979200
}
```

**Статус:** ✅ **Backend подписан на command_response**

**Обработка в backend:**
- `handle_command_response()` в history-logger
- Обновление статуса команды для уведомлений на фронт

**Пример использования:**
```c
// Создание ответа с ошибкой
node_command_handler_create_response(
    cmd_id,
    "ERROR",
    "pump_driver_failed",  // error_code
    "Pump driver initialization failed",
    NULL
);
```

---

### 5. Config Response с ошибками (в ответах на конфигурацию)

**Компонент:** `node_config_handler`  
**Топик:** `hydro/{gh}/{zone}/{node}/config_response`  
**QoS:** 1  
**Retain:** false

**Формат payload:**
```json
{
  "status": "ERROR",
  "message": "Invalid JSON",
  "cmd_id": "config-123",
  "config_version": 1,
  "ts": 1737979200
}
```

**Статус:** ✅ **Backend подписан на config_response**

**Обработка в backend:**
- `handle_config_response()` в history-logger
- Обработка ошибок установки конфигурации

---

### 6. Logging компонент (логи через MQTT)

**Компонент:** `logging`  
**Функция:** `logging_send_to_mqtt()`  
**Статус:** ⚠️ **Компонент существует, но не используется активно**

**Описание:**
- Компонент может отправлять логи через MQTT
- Требует регистрации callback через `logging_register_mqtt_callback()`
- Не используется по умолчанию в нодах

---

## Текущее состояние

### ✅ Работает:
1. **Telemetry с error_code** - ошибки передаются в телеметрии
2. **Command Response** - ошибки в ответах на команды обрабатываются
3. **Config Response** - ошибки в ответах на конфигурацию обрабатываются

### ❌ Не работает:
1. **Diagnostics топик** - backend не подписан, метрики ошибок не обрабатываются
2. **Error топик** - backend не подписан, немедленные ошибки не обрабатываются

---

## Рекомендации

### 1. Добавить подписку на diagnostics топик

**В `backend/services/history-logger/main.py`:**
```python
await mqtt.subscribe("hydro/+/+/+/diagnostics", handle_diagnostics)
```

**Обработчик:**
```python
async def handle_diagnostics(topic: str, payload: bytes):
    """Обработчик diagnostics сообщений от узлов."""
    data = _parse_json(payload)
    if not data:
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        return
    
    # Обновляем метрики ошибок в БД
    errors = data.get("errors", {})
    if errors:
        await execute(
            """
            UPDATE nodes 
            SET 
                error_count = $2,
                warning_count = $3,
                critical_count = $4,
                updated_at = NOW()
            WHERE uid = $1
            """,
            node_uid,
            errors.get("error_count", 0),
            errors.get("warning_count", 0),
            errors.get("critical_count", 0)
        )
```

### 2. Добавить подписку на error топик

**В `backend/services/history-logger/main.py`:**
```python
await mqtt.subscribe("hydro/+/+/+/error", handle_error)
```

**Обработчик:**
```python
async def handle_error(topic: str, payload: bytes):
    """Обработчик error сообщений от узлов."""
    data = _parse_json(payload)
    if not data:
        return
    
    node_uid = _extract_node_uid(topic)
    if not node_uid:
        return
    
    # Создаем Alert через Laravel API
    error_data = {
        "node_uid": node_uid,
        "level": data.get("level"),
        "component": data.get("component"),
        "error_code": data.get("error_code"),
        "message": data.get("message"),
        "ts": data.get("ts")
    }
    
    # Вызов Laravel API для создания Alert
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{laravel_url}/api/alerts",
            json=error_data,
            headers={"Authorization": f"Bearer {ingest_token}"}
        )
```

### 3. Добавить поля ошибок в таблицу nodes

**Миграция:**
```sql
ALTER TABLE nodes 
ADD COLUMN error_count INTEGER DEFAULT 0,
ADD COLUMN warning_count INTEGER DEFAULT 0,
ADD COLUMN critical_count INTEGER DEFAULT 0;
```

---

## Итоговая таблица механизмов

| Механизм | Топик | Backend подписка | Обработка | Статус |
|----------|-------|------------------|-----------|--------|
| Diagnostics | `hydro/+/+/+/diagnostics` | ❌ Нет | ❌ Нет | ❌ Не работает |
| Error | `hydro/+/+/+/error` | ❌ Нет | ❌ Нет | ❌ Не работает |
| Telemetry error_code | `hydro/+/+/+/+/telemetry` | ✅ Да | ✅ Да | ✅ Работает |
| Command Response | `hydro/+/+/+/+/command_response` | ✅ Да | ✅ Да | ✅ Работает |
| Config Response | `hydro/+/+/+/config_response` | ✅ Да | ✅ Да | ✅ Работает |
| Logging | N/A | ⚠️ Опционально | ⚠️ Опционально | ⚠️ Не используется |

---

## Выводы

1. **Текущее состояние:** Ошибки отправляются только через телеметрию и ответы на команды/конфигурацию
2. **Проблема:** Специализированные топики для ошибок (diagnostics, error) не обрабатываются backend
3. **Рекомендация:** Добавить подписки на diagnostics и error топики для полной обработки ошибок

