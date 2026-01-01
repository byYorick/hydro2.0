# Logging Component

Система логирования для узлов ESP32 с поддержкой MQTT и NVS.

## Описание

Компонент предоставляет расширенную систему логирования:
- Уровни логирования (ERROR, WARN, INFO, DEBUG, VERBOSE)
- Отправка логов через MQTT (опционально)
- Ротация логов в NVS (ограниченный буфер)
- Форматирование с временными метками
- Интеграция с ESP_LOG для единообразного логирования

## Использование

### Инициализация

```c
#include "logging.h"

// Инициализация с конфигурацией
logging_config_t config = {
    .level = LOG_LEVEL_INFO,
    .enable_mqtt = true,
    .enable_nvs = true,
    .nvs_buffer_size = 2048,
    .max_log_length = 256
};

esp_err_t err = logging_init(&config);
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to initialize logging");
    return err;
}
```

### Логирование

```c
// Использование макросов
LOG_ERROR(TAG, "Error occurred: %d", error_code);
LOG_WARN(TAG, "Warning: %s", warning_message);
LOG_INFO(TAG, "Info: %s", info_message);
LOG_DEBUG(TAG, "Debug: %d", debug_value);

// Или напрямую
logging_log(LOG_LEVEL_INFO, TAG, "Message: %s", message);
```

### Отправка логов через MQTT

```c
void mqtt_log_callback(log_level_t level, const char *tag, const char *message, void *user_ctx) {
    // Отправка лога через MQTT
    char topic[128];
    snprintf(topic, sizeof(topic), "hydro/%s/logs", node_uid);
    
    cJSON *log_json = cJSON_CreateObject();
    cJSON_AddStringToObject(log_json, "level", log_level_to_string(level));
    cJSON_AddStringToObject(log_json, "tag", tag);
    cJSON_AddStringToObject(log_json, "message", message);
    cJSON_AddNumberToObject(log_json, "timestamp", esp_timer_get_time() / 1000000);
    
    char *json_str = cJSON_PrintUnformatted(log_json);
    mqtt_client_publish(topic, json_str, 0, 0);
    free(json_str);
    cJSON_Delete(log_json);
}

// Регистрация callback
logging_register_mqtt_callback(mqtt_log_callback, NULL);
```

### Получение логов из NVS

```c
char buffer[4096];
size_t log_count = 0;

esp_err_t err = logging_get_nvs_logs(buffer, sizeof(buffer), &log_count);
if (err == ESP_OK) {
    ESP_LOGI(TAG, "Retrieved %zu logs from NVS", log_count);
    // Использование buffer...
}
```

## Уровни логирования

- `LOG_LEVEL_ERROR` - Критические ошибки
- `LOG_LEVEL_WARN` - Предупреждения
- `LOG_LEVEL_INFO` - Информационные сообщения
- `LOG_LEVEL_DEBUG` - Отладочная информация
- `LOG_LEVEL_VERBOSE` - Подробная информация

## Требования

- ESP-IDF 5.x
- nvs_flash компонент

## Документация

- Стандарты кодирования: `../../../../../doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`

