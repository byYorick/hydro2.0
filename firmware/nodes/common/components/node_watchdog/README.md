# Node Watchdog Component

Унифицированный компонент для управления watchdog таймерами в ESP32 нодах.

## Описание

Компонент предоставляет единый API для управления watchdog таймерами всех задач FreeRTOS, заменяя прямые вызовы `esp_task_wdt_*` на унифицированный интерфейс.

## Использование

### Инициализация

Watchdog автоматически инициализируется в `node_framework_init()`. Ручная инициализация не требуется.

```c
// В node_framework_init():
node_watchdog_config_t wdt_config = {
    .timeout_ms = 10000,      // 10 секунд
    .trigger_panic = false,   // Переход в safe_mode вместо panic
    .idle_core_mask = 0       // Не мониторим idle задачи
};
node_watchdog_init(&wdt_config);
```

### Добавление задачи в watchdog

```c
#include "node_watchdog.h"

void task_sensors(void *pvParameters) {
    // Добавляем задачу в watchdog
    esp_err_t err = node_watchdog_add_task();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add task to watchdog: %s", esp_err_to_name(err));
    }
    
    while (1) {
        // ... работа задачи ...
        
        // Сбрасываем watchdog в цикле
        node_watchdog_reset();
        
        vTaskDelay(...);
    }
}
```

### Получение времени выполнения задачи

```c
uint32_t runtime_ms;
if (node_watchdog_get_task_runtime(xTaskGetCurrentTaskHandle(), &runtime_ms) == ESP_OK) {
    ESP_LOGI(TAG, "Task runtime: %lu ms", runtime_ms);
}
```

## API

### `node_watchdog_init()`
Инициализирует watchdog с заданной конфигурацией.

### `node_watchdog_deinit()`
Деинициализирует watchdog (вызывается автоматически в `node_framework_deinit()`).

### `node_watchdog_add_task()`
Добавляет текущую задачу в мониторинг watchdog.

### `node_watchdog_reset()`
Сбрасывает watchdog таймер для текущей задачи.

### `node_watchdog_get_task_runtime()`
Получает время выполнения задачи (в миллисекундах).

### `node_watchdog_is_initialized()`
Проверяет, инициализирован ли watchdog.

## Конфигурация

- `timeout_ms` - таймаут watchdog в миллисекундах (по умолчанию 10000)
- `trigger_panic` - вызывать ли panic при срабатывании (по умолчанию false, переход в safe_mode)
- `idle_core_mask` - маска ядер для мониторинга idle задач (по умолчанию 0)

## Интеграция

Компонент интегрирован во все ноды:
- ✅ `ph_node` - все задачи используют `node_watchdog_*`
- ✅ `ec_node` - все задачи используют `node_watchdog_*`
- ✅ `climate_node` - все задачи используют `node_watchdog_*`
- ✅ `pump_node` - все задачи используют `node_watchdog_*`
- ✅ `heartbeat_task` - использует `node_watchdog_*`

## Статус

✅ Готово к использованию (95% готово)

**Реализовано:**
- ✅ Унифицированный API для управления watchdog
- ✅ Автоматическая инициализация в node_framework
- ✅ Интеграция во все ноды и heartbeat_task
- ✅ Все ноды успешно скомпилированы

**Осталось:**
- ⏳ Обработка срабатывания watchdog (переход в safe_mode при следующей загрузке) - опционально

## Зависимости

- `esp_task_wdt` - ESP-IDF компонент для watchdog
- `freertos` - для работы с задачами
- `esp_timer` - для измерения времени выполнения задач

