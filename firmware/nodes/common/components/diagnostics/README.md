# Diagnostics Component

Компонент для централизованного сбора метрик и диагностики системы.

## Описание

Компонент предоставляет:
- Централизованный сбор метрик системы
- Публикация диагностики через MQTT
- API для запроса диагностики через команды
- Метрики: память, uptime, ошибки, MQTT, сенсоры, задачи

## Использование

### Инициализация

```c
#include "diagnostics.h"

// Инициализация с конфигурацией по умолчанию
esp_err_t err = diagnostics_init(NULL);

// Или с кастомной конфигурацией
diagnostics_config_t config = {
    .publish_interval_ms = 60000,  // 60 секунд
    .enable_auto_publish = true,
    .enable_metrics = true
};
err = diagnostics_init(&config);
```

### Получение снимка диагностики

```c
diagnostics_snapshot_t snapshot;
if (diagnostics_get_snapshot(&snapshot) == ESP_OK) {
    ESP_LOGI(TAG, "Uptime: %llu seconds", snapshot.uptime_seconds);
    ESP_LOGI(TAG, "Free heap: %zu bytes", snapshot.memory.free_heap);
    ESP_LOGI(TAG, "Error count: %u", snapshot.errors.total_count);
}
```

### Публикация диагностики

```c
// Публикация вручную
diagnostics_publish();

// Автоматическая публикация включена через enable_auto_publish
```

### Обновление метрик

```c
// Обновление метрик MQTT (вызывается из mqtt_manager)
diagnostics_update_mqtt_metrics(true, false, false);  // message_sent

// Обновление метрик сенсора
diagnostics_update_sensor_metrics("ph_sensor", true);  // read_success
```

## Метрики

Компонент собирает следующие метрики:

### Системные метрики
- `uptime_seconds` - время работы в секундах
- `free_heap` - свободная память heap (байты)
- `min_free_heap` - минимальная свободная память heap (байты)
- `largest_free_block` - самый большой свободный блок (байты)

### Метрики ошибок
- `warning_count` - количество предупреждений
- `error_count` - количество ошибок
- `critical_count` - количество критических ошибок
- `total_count` - общее количество ошибок

### Метрики MQTT
- `connected` - статус подключения
- `messages_sent` - количество отправленных сообщений
- `messages_received` - количество полученных сообщений
- `publish_errors` - количество ошибок публикации
- `reconnect_count` - количество переподключений

### Метрики Wi-Fi
- `connected` - статус подключения
- `rssi` - уровень сигнала Wi-Fi

### Метрики задач
- `name` - имя задачи
- `stack_high_water_mark` - минимальный свободный стек (байты)
- `runtime_ms` - время выполнения задачи (миллисекунды)
- `core_id` - ID ядра (0 или 1)

### Метрики сенсоров
- `name` - имя сенсора
- `read_count` - количество успешных чтений
- `error_count` - количество ошибок чтения
- `last_read_time_ms` - время последнего чтения (миллисекунды)
- `initialized` - статус инициализации

### Метрики кэша I2C
- `hits` - попадания в кэш
- `misses` - промахи кэша
- `evictions` - вытеснения из кэша
- `current_entries` - текущее количество записей

## Формат публикации

Диагностика публикуется в топик:
```
hydro/{gh}/{zone}/{node}/diagnostics
```

Формат JSON:
```json
{
  "system": {
    "uptime_seconds": 3600,
    "free_heap": 50000,
    "min_free_heap": 45000,
    "largest_free_block": 30000
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
  "i2c_cache": {...},
  "ts": 1737979200
}
```

## Интеграция

Компонент интегрируется с:
- `node_framework` - для состояния и ошибок
- `mqtt_manager` - для статистики MQTT
- `wifi_manager` - для статуса Wi-Fi
- `memory_pool` - для метрик памяти
- `i2c_cache` - для метрик кэша
- `node_watchdog` - для метрик задач

## Зависимости

- `node_framework` - для состояния и ошибок
- `mqtt_manager` - для публикации
- `wifi_manager` - для статуса Wi-Fi
- `memory_pool` - для метрик памяти
- `i2c_cache` - для метрик кэша
- `freertos` - для метрик задач
- `esp_timer` - для uptime
- `esp_system` - для метрик памяти
- `esp_wifi` - для статуса Wi-Fi
- `json` - для формирования JSON

