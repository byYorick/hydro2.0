# Memory Pool Component

Компонент для оптимизации использования памяти в ESP32 нодах.

## Описание

Компонент предоставляет:
- Пул памяти для JSON строк (переиспользование буферов)
- Метрики использования памяти
- Защиту от переполнения буферов
- Мониторинг свободной памяти heap

## Использование

### Инициализация

```c
#include "memory_pool.h"

// Инициализация с конфигурацией по умолчанию
esp_err_t err = memory_pool_init(NULL);

// Или с кастомной конфигурацией
memory_pool_config_t config = {
    .json_string_pool_size = 16,
    .json_string_max_len = 1024,
    .enable_metrics = true
};
err = memory_pool_init(&config);
```

### Выделение JSON строк

```c
// Выделение буфера для JSON строки
char *json_str = memory_pool_alloc_json_string(512);
if (json_str) {
    // Использование буфера
    snprintf(json_str, 512, "{\"value\": %d}", value);
    
    // Освобождение буфера (возврат в пул)
    memory_pool_free_json_string(json_str);
}
```

### Получение метрик

```c
memory_pool_metrics_t metrics;
if (memory_pool_get_metrics(&metrics) == ESP_OK) {
    ESP_LOGI(TAG, "JSON strings allocated: %lu", metrics.json_strings_allocated);
    ESP_LOGI(TAG, "Pool hits: %lu, misses: %lu", metrics.pool_hits, metrics.pool_misses);
    ESP_LOGI(TAG, "Current heap free: %zu bytes", metrics.current_heap_free);
    ESP_LOGI(TAG, "Min heap free: %zu bytes", metrics.min_heap_free);
}
```

## Конфигурация

- `json_string_pool_size` - количество буферов в пуле (по умолчанию 8)
- `json_string_max_len` - максимальная длина JSON строки (по умолчанию 512)
- `enable_metrics` - включить сбор метрик (по умолчанию true)

## Примечания

- Компонент использует mutex для потокобезопасности
- При переполнении пула используется обычный malloc/free
- Метрики обновляются автоматически при каждом выделении/освобождении

