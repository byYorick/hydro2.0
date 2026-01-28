# Руководство по отправке ошибок на сервер

## Обзор

Все ноды ESP32 должны использовать `node_state_manager` для отправки ошибок на backend сервер. Это обеспечивает:
- Централизованную обработку ошибок
- Автоматическое создание Alerts в Laravel
- Отслеживание метрик ошибок в БД
- Немедленную отправку критических ошибок

## Механизмы отправки ошибок

### 1. Немедленная отправка ошибок (Error топик)

Используйте `node_state_manager_report_error()` для отправки ошибок немедленно:

```c
#include "node_state_manager.h"

// Предупреждение (не критично)
node_state_manager_report_error(
    ERROR_LEVEL_WARNING,
    "ph_sensor",
    ESP_ERR_INVALID_RESPONSE,
    "Sensor reading unstable, retrying"
);

// Ошибка (требует внимания)
node_state_manager_report_error(
    ERROR_LEVEL_ERROR,
    "ph_sensor",
    ESP_ERR_INVALID_RESPONSE,
    "Sensor read failed after 3 retries"
);

// Критическая ошибка (автоматически переводит в safe_mode)
node_state_manager_report_error(
    ERROR_LEVEL_CRITICAL,
    "pump_driver",
    ESP_FAIL,
    "Pump driver initialization failed"
);
```

**Что происходит:**
- Ошибка публикуется в топик `hydro/{gh}/{zone}/{node}/error`
- Backend получает сообщение и создает Alert через Laravel API
- Обновляется счетчик ошибок в БД (`error_count`, `warning_count`, `critical_count`)
- Критические ошибки автоматически переводят ноду в `safe_mode`

### 2. Периодические метрики ошибок (Diagnostics топик)

Метрики ошибок автоматически включаются в diagnostics сообщения, которые публикуются каждые 60 секунд. Компонент `diagnostics` собирает метрики из `node_state_manager`.

**Не требуется дополнительного кода** - метрики собираются автоматически.

## Примеры использования в нодах

### Пример 1: Ошибка чтения сенсора

```c
// В ph_node_tasks.c или ec_node_tasks.c
esp_err_t err = trema_ph_read(&ph_reading);
if (err != ESP_OK) {
    // Регистрируем ошибку
    node_state_manager_report_error(
        ERROR_LEVEL_ERROR,
        "ph_sensor",
        err,
        "Failed to read pH sensor"
    );
    
    // Продолжаем работу (не критично)
    ESP_LOGW(TAG, "pH sensor read failed, using last known value");
    return;
}
```

### Пример 2: Критическая ошибка инициализации

```c
// В pump_node_init.c
esp_err_t err = pump_driver_init();
if (err != ESP_OK) {
    // Критическая ошибка - нода перейдет в safe_mode
    node_state_manager_report_error(
        ERROR_LEVEL_CRITICAL,
        "pump_driver",
        err,
        "Pump driver initialization failed, entering safe mode"
    );
    
    // node_state_manager автоматически переведет в safe_mode
    return err;
}
```

### Пример 3: Предупреждение о нестабильности

```c
// В climate_node_tasks.c
sht3x_reading_t reading = {0};
esp_err_t err = sht3x_read(&reading);
if (err == ESP_OK && reading.valid) {
    // Проверяем стабильность
    if (fabs(reading.temperature - last_temperature) > 5.0) {
        node_state_manager_report_error(
            ERROR_LEVEL_WARNING,
            "sht3x",
            ESP_ERR_INVALID_STATE,
            "Temperature reading unstable, large deviation detected"
        );
    }
    last_temperature = reading.temperature;
}
```

### Пример 4: Ошибка MQTT публикации

```c
// В любом месте, где публикуется телеметрия
esp_err_t err = mqtt_manager_publish_telemetry(json_str);
if (err != ESP_OK) {
    node_state_manager_report_error(
        ERROR_LEVEL_ERROR,
        "mqtt_manager",
        err,
        "Failed to publish telemetry"
    );
}
```

## Уровни ошибок

### ERROR_LEVEL_WARNING
- **Использование:** Предупреждения, нестабильность, временные проблемы
- **Действие:** Ошибка отправляется на сервер, но нода продолжает работу
- **Примеры:** Нестабильные показания сенсора, временная потеря связи

### ERROR_LEVEL_ERROR
- **Использование:** Ошибки, требующие внимания
- **Действие:** Ошибка отправляется на сервер, нода переходит в состояние ERROR
- **Примеры:** Неудачное чтение сенсора, ошибка публикации MQTT

### ERROR_LEVEL_CRITICAL
- **Использование:** Критические ошибки, угрожающие безопасности
- **Действие:** Ошибка отправляется на сервер, нода автоматически переходит в `safe_mode`
- **Примеры:** Ошибка инициализации драйвера насоса, перегрев, перегрузка по току

## Интеграция с нодами

### Проверка использования в существующих нодах

Все ноды должны использовать `node_state_manager_report_error()` вместо простого `ESP_LOGE()` для ошибок, которые должны быть отправлены на сервер.

**Заменить:**
```c
ESP_LOGE(TAG, "Sensor read failed: %s", esp_err_to_name(err));
```

**На:**
```c
node_state_manager_report_error(
    ERROR_LEVEL_ERROR,
    "sensor",
    err,
    "Sensor read failed"
);
```

### Регистрация callback для safe_mode

Для нод с актуаторами (pump_node, relay_node, light_node) необходимо зарегистрировать callback для отключения актуаторов в safe_mode:

```c
// В pump_node_app.c или relay_node_app.c
static esp_err_t disable_actuators_in_safe_mode(void *user_ctx) {
    // Отключаем все насосы/реле
    pump_driver_stop_all();
    return ESP_OK;
}

// В pump_node_app_init()
node_state_manager_register_safe_mode_callback(
    disable_actuators_in_safe_mode,
    NULL
);
```

## Формат сообщений

### Error топик (`hydro/{gh}/{zone}/{node}/error`)

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

### Diagnostics топик (`hydro/{gh}/{zone}/{node}/diagnostics`)

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

Backend автоматически:
1. Получает error сообщения через `handle_error()` в history-logger
2. Создает Alert через Laravel API
3. Обновляет метрики ошибок в таблице `nodes`
4. Получает diagnostics сообщения через `handle_diagnostics()` в history-logger
5. Обновляет счетчики ошибок в БД

## Рекомендации

1. **Используйте правильный уровень:** Не используйте CRITICAL для обычных ошибок
2. **Указывайте компонент:** Всегда указывайте компонент, где произошла ошибка
3. **Добавляйте контекст:** В сообщении указывайте детали ошибки
4. **Не дублируйте:** Не отправляйте одну и ту же ошибку многократно
5. **Используйте ESP_LOGE для локального логирования:** `node_state_manager_report_error()` уже логирует через ESP_LOG

## Проверка работы

После внедрения проверьте:
1. Ошибки появляются в топике `hydro/+/+/+/error`
2. Alerts создаются в Laravel
3. Метрики обновляются в таблице `nodes`
4. Diagnostics сообщения содержат метрики ошибок

