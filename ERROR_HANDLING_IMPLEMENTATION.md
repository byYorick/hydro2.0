# Реализация обработки ошибок на сервере

## Дата: 2025-01-28

## Выполненные задачи

### 1. ✅ Создан общий компонент обработки ошибок

**Файл:** `backend/services/common/error_handler.py`

**Компонент:** `NodeErrorHandler`

**Функциональность:**
- Обработка diagnostics сообщений (периодические метрики ошибок)
- Обработка error сообщений (немедленные ошибки)
- Интеграция с Laravel API для создания Alerts
- Обновление метрик ошибок в БД (`error_count`, `warning_count`, `critical_count`)

**API:**
```python
error_handler = get_error_handler()
await error_handler.handle_diagnostics(node_uid, diagnostics_data)
await error_handler.handle_error(node_uid, error_data)
```

### 2. ✅ Добавлены обработчики в history-logger

**Файл:** `backend/services/history-logger/main.py`

**Добавлено:**
- `handle_diagnostics()` - обработчик diagnostics сообщений
- `handle_error()` - обработчик error сообщений
- Подписки на MQTT топики:
  - `hydro/+/+/+/diagnostics`
  - `hydro/+/+/+/error`
- Prometheus метрики:
  - `DIAGNOSTICS_RECEIVED` - счетчик diagnostics сообщений
  - `ERROR_RECEIVED` - счетчик error сообщений

### 3. ✅ Создана миграция для полей ошибок

**Файл:** `backend/laravel/database/migrations/2025_01_28_000001_add_error_metrics_to_nodes_table.php`

**Добавленные поля в таблицу `nodes`:**
- `error_count` (unsigned integer, default 0)
- `warning_count` (unsigned integer, default 0)
- `critical_count` (unsigned integer, default 0)

### 4. ✅ Создано руководство по использованию

**Файл:** `firmware/nodes/common/components/node_framework/ERROR_REPORTING_GUIDE.md`

**Содержание:**
- Обзор механизмов отправки ошибок
- Примеры использования `node_state_manager_report_error()`
- Описание уровней ошибок (WARNING, ERROR, CRITICAL)
- Рекомендации по интеграции в ноды

## Архитектура

### Поток данных ошибок

```
ESP32 Node
  ↓
node_state_manager_report_error()
  ↓
MQTT: hydro/{gh}/{zone}/{node}/error
  ↓
history-logger: handle_error()
  ↓
error_handler.handle_error()
  ↓
Laravel API: /api/alerts
  ↓
Database: nodes (error_count, warning_count, critical_count)
```

### Поток метрик ошибок

```
ESP32 Node
  ↓
diagnostics_publish() (каждые 60 секунд)
  ↓
MQTT: hydro/{gh}/{zone}/{node}/diagnostics
  ↓
history-logger: handle_diagnostics()
  ↓
error_handler.handle_diagnostics()
  ↓
Database: nodes (error_count, warning_count, critical_count)
```

## Использование в нодах

### Пример отправки ошибки

```c
#include "node_state_manager.h"

// Предупреждение
node_state_manager_report_error(
    ERROR_LEVEL_WARNING,
    "ph_sensor",
    ESP_ERR_INVALID_RESPONSE,
    "Sensor reading unstable"
);

// Ошибка
node_state_manager_report_error(
    ERROR_LEVEL_ERROR,
    "ph_sensor",
    ESP_ERR_INVALID_RESPONSE,
    "Sensor read failed"
);

// Критическая ошибка (автоматически переводит в safe_mode)
node_state_manager_report_error(
    ERROR_LEVEL_CRITICAL,
    "pump_driver",
    ESP_FAIL,
    "Pump driver initialization failed"
);
```

## Форматы сообщений

### Error сообщение

**Топик:** `hydro/{gh}/{zone}/{node}/error`

**Payload:**
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

### Diagnostics сообщение

**Топик:** `hydro/{gh}/{zone}/{node}/diagnostics`

**Payload (фрагмент):**
```json
{
  "errors": {
    "warning_count": 5,
    "error_count": 2,
    "critical_count": 0,
    "total_count": 7
  },
  ...
}
```

## Backend обработка

### NodeErrorHandler

**Методы:**
- `handle_diagnostics()` - обновляет метрики ошибок в БД
- `handle_error()` - создает Alert через Laravel API и обновляет счетчики

**Интеграция с Laravel:**
- Создание Alert через `/api/alerts`
- Обновление метрик в таблице `nodes`
- Использование `history_logger_api_token` для аутентификации

## Prometheus метрики

### Новые метрики

- `diagnostics_received_total{node_uid}` - количество полученных diagnostics сообщений
- `error_received_total{node_uid, level}` - количество полученных error сообщений

## Миграция БД

### Выполнение миграции

```bash
cd backend/laravel
php artisan migrate
```

### Откат миграции

```bash
php artisan migrate:rollback --step=1
```

## Тестирование

### Проверка работы обработчиков

1. **Отправка error сообщения:**
   - Нода отправляет ошибку через `node_state_manager_report_error()`
   - Проверить топик `hydro/+/+/+/error` в MQTT
   - Проверить создание Alert в Laravel
   - Проверить обновление `error_count` в БД

2. **Отправка diagnostics сообщения:**
   - Нода публикует diagnostics (каждые 60 секунд)
   - Проверить топик `hydro/+/+/+/diagnostics` в MQTT
   - Проверить обновление метрик в БД

3. **Prometheus метрики:**
   - Проверить `/metrics` endpoint в history-logger
   - Убедиться, что метрики `diagnostics_received_total` и `error_received_total` увеличиваются

## Следующие шаги

### Рекомендации по внедрению в ноды

1. **Заменить ESP_LOGE на node_state_manager_report_error:**
   - Для ошибок, которые должны быть отправлены на сервер
   - Использовать правильный уровень ошибки

2. **Добавить обработку ошибок в критических местах:**
   - Инициализация драйверов
   - Чтение сенсоров
   - Публикация MQTT
   - Обработка команд

3. **Зарегистрировать callback для safe_mode:**
   - Для нод с актуаторами (pump_node, relay_node, light_node)
   - Отключение актуаторов при переходе в safe_mode

## Файлы изменений

### Backend
- `backend/services/common/error_handler.py` (новый)
- `backend/services/history-logger/main.py` (обновлен)
- `backend/laravel/database/migrations/2025_01_28_000001_add_error_metrics_to_nodes_table.php` (новый)

### Firmware
- `firmware/nodes/common/components/node_framework/ERROR_REPORTING_GUIDE.md` (новый)

### Документация
- `ERROR_REPORTING_AUDIT.md` (обновлен)
- `ERROR_HANDLING_IMPLEMENTATION.md` (новый)

## Статус

✅ **Все задачи выполнены**

- Общий компонент обработки ошибок создан
- Обработчики добавлены в history-logger
- Миграция БД создана
- Руководство по использованию создано
- Документация обновлена

