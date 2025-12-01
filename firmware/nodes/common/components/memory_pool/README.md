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
char *json_str = memory_pool_alloc_string(512);
if (json_str) {
    // Использование буфера
    snprintf(json_str, 512, "{\"value\": %d}", value);
    
    // Освобождение буфера (возврат в пул)
    memory_pool_free_string(json_str);
}
```

### Получение метрик

```c
size_t free_heap, min_free_heap, alloc_count, free_count, pool_hits, pool_misses;
memory_pool_get_metrics(&free_heap, &min_free_heap, &alloc_count, &free_count, &pool_hits, &pool_misses);

ESP_LOGI(TAG, "JSON strings allocated: %zu", alloc_count);
ESP_LOGI(TAG, "Pool hits: %zu, misses: %zu", pool_hits, pool_misses);
ESP_LOGI(TAG, "Current heap free: %zu bytes", free_heap);
ESP_LOGI(TAG, "Min heap free: %zu bytes", min_free_heap);
```

Метрики также автоматически добавляются в heartbeat (min_heap_free, memory_pool_hit_rate).

## Конфигурация

- `buffer_size` - размер каждого буфера в пуле (по умолчанию 512 байт)
- `num_buffers` - количество буферов в пуле (по умолчанию 8)

Конфигурация по умолчанию:
```c
memory_pool_config_t default_config = {
    .buffer_size = 512,
    .num_buffers = 8
};
```

## Примечания

- Компонент использует mutex для потокобезопасности
- При переполнении пула используется обычный malloc/free
- Метрики обновляются автоматически при каждом выделении/освобождении
- Компонент автоматически инициализируется в `node_framework_init()`
- Используется в `node_telemetry_engine` для оптимизации JSON строк
- Метрики памяти автоматически добавляются в heartbeat

## Статус

✅ Готово к использованию (90% готово)

**Реализовано:**
- ✅ Пул памяти для JSON строк (переиспользование буферов)
- ✅ Метрики использования памяти
- ✅ Интеграция в node_framework
- ✅ Добавление метрик в heartbeat
- ✅ Все ноды успешно скомпилированы с новым компонентом


