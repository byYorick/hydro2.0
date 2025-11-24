# Node Framework Component

Унифицированный базовый фреймворк для всех нод ESP32.

## Описание

Фреймворк устраняет дублирование кода между разными нодами (ph_node, ec_node, climate_node, pump_node) и предоставляет единый API для:

- Обработки NodeConfig
- Обработки команд
- Публикации телеметрии
- Управления состоянием ноды (включая Safe Mode)
- Унифицированного управления watchdog
- Оптимизации использования памяти (через memory_pool)

## Структура

```
node_framework/
├── include/
│   ├── node_framework.h          # Основной API фреймворка
│   ├── node_config_handler.h     # Обработка NodeConfig
│   ├── node_command_handler.h    # Обработка команд
│   ├── node_telemetry_engine.h   # Движок телеметрии
│   ├── node_state_manager.h      # Управление состоянием
│   └── node_watchdog.h           # Унифицированный watchdog
├── node_framework.c
├── node_config_handler.c
├── node_command_handler.c
├── node_telemetry_engine.c
├── node_state_manager.c
├── node_watchdog.c
├── CMakeLists.txt
└── README.md
```

## Использование

### Инициализация

```c
#include "node_framework.h"

node_framework_config_t config = {
    .node_type = "ph",
    .default_node_id = "nd-ph-1",
    .default_gh_uid = "gh-1",
    .default_zone_uid = "zn-1",
    .channel_init_cb = ph_node_init_channels,
    .command_handler_cb = NULL,  // Регистрация через API
    .telemetry_cb = ph_node_publish_telemetry,
    .user_ctx = NULL
};

esp_err_t err = node_framework_init(&config);
```

### Регистрация обработчиков команд

```c
#include "node_command_handler.h"

// Регистрация обработчика команды
node_command_handler_register("run_pump", handle_run_pump, NULL);
node_command_handler_register("calibrate", handle_calibrate, NULL);
```

### Публикация телеметрии

```c
#include "node_telemetry_engine.h"

// Публикация телеметрии сенсора
node_telemetry_publish_sensor("ph_sensor", METRIC_TYPE_PH, 6.5, "pH", 1465, false, true);

// Публикация телеметрии актуатора
node_telemetry_publish_actuator("pump_acid", METRIC_TYPE_PUMP_STATE, "ON", 0);
```

### Управление состоянием

```c
#include "node_state_manager.h"

// Переход в безопасный режим
node_state_manager_enter_safe_mode("Critical error in sensor");

// Регистрация ошибки (новая версия с уровнями)
node_state_manager_report_error(ERROR_LEVEL_ERROR, "ph_sensor", ESP_FAIL, "Sensor read failed");

// Критическая ошибка (автоматически переводит в safe_mode)
node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "pump_driver", ESP_FAIL, "Pump driver initialization failed");

// Регистрация callback для отключения актуаторов в safe_mode
node_state_manager_register_safe_mode_callback(ph_node_disable_actuators_in_safe_mode, NULL);
```

### Управление Watchdog

```c
#include "node_watchdog.h"

// Watchdog автоматически инициализируется в node_framework_init()
// В задачах FreeRTOS:

void task_sensors(void *pvParameters) {
    // Добавляем задачу в watchdog
    node_watchdog_add_task();
    
    while (1) {
        // ... работа задачи ...
        
        // Сбрасываем watchdog в цикле
        node_watchdog_reset();
        
        vTaskDelay(...);
    }
}
```

## Статус

✅ Готово к использованию (100% готово)

**Реализовано:**
- ✅ Базовая структура компонента
- ✅ Все заголовочные файлы (6 файлов)
- ✅ `node_framework.c` - инициализация и управление состоянием
- ✅ `node_state_manager.c` - управление состоянием, safe_mode, счетчики ошибок, уровни ошибок (WARNING/ERROR/CRITICAL)
- ✅ `node_config_handler.c` - обработка NodeConfig с валидацией
- ✅ `node_command_handler.c` - обработка команд с роутингом и защитой от дубликатов
- ✅ `node_telemetry_engine.c` - батчинг телеметрии с оптимизацией памяти
- ✅ `node_watchdog.c` - унифицированный watchdog для всех задач
- ✅ Интеграция с memory_pool для оптимизации использования памяти
- ✅ Интеграция со всеми нодами (ph_node, ec_node, climate_node, pump_node)
  - Обработка NodeConfig через node_config_handler
  - Обработка команд через node_command_handler
  - Публикация телеметрии через node_telemetry_engine
  - Управление watchdog через node_watchdog
  - Регистрация callback для safe_mode

**Завершено:**
- ✅ Все четыре ноды (ph_node, ec_node, climate_node, pump_node) успешно скомпилированы с интеграцией node_framework
- ✅ Все компоненты протестированы на компиляцию
- ✅ Watchdog интегрирован во все задачи всех нод
- ✅ Memory pool интегрирован для оптимизации JSON строк
- ✅ Safe Mode реализован с callback для отключения актуаторов
- ✅ Улучшенная обработка ошибок с уровнями и отправкой через MQTT

**Следующие шаги:**
- ⏳ Тестирование на реальном железе
- ⏳ Оптимизация и доработка по результатам тестирования
- ⏳ Добавление обработки срабатывания watchdog (переход в safe_mode при следующей загрузке) - опционально

## Зависимости

- `mqtt_manager` - для публикации сообщений
- `config_storage` - для работы с NodeConfig
- `config_apply` - для применения конфигурации
- `json` (ESP-IDF 5.5) / `cjson` - для работы с JSON
- `esp_timer` - для timestamp
- `freertos` - для задач и синхронизации
- `memory_pool` - для оптимизации использования памяти

