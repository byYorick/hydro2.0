# Node Framework Component

Унифицированный базовый фреймворк для всех нод ESP32.

## Описание

Фреймворк устраняет дублирование кода между разными нодами (ph_node, ec_node, climate_node, pump_node) и предоставляет единый API для:

- Обработки NodeConfig
- Обработки команд
- Публикации телеметрии
- Управления состоянием ноды

## Структура

```
node_framework/
├── include/
│   ├── node_framework.h          # Основной API фреймворка
│   ├── node_config_handler.h     # Обработка NodeConfig
│   ├── node_command_handler.h    # Обработка команд
│   ├── node_telemetry_engine.h   # Движок телеметрии
│   └── node_state_manager.h      # Управление состоянием
├── node_framework.c
├── node_config_handler.c
├── node_command_handler.c
├── node_telemetry_engine.c
├── node_state_manager.c
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
```

## Статус

✅ Готово к использованию (100% готово)

**Реализовано:**
- ✅ Базовая структура компонента
- ✅ Все заголовочные файлы (5 файлов)
- ✅ `node_framework.c` - инициализация и управление состоянием
- ✅ `node_state_manager.c` - управление состоянием, safe_mode, счетчики ошибок
- ✅ `node_config_handler.c` - обработка NodeConfig с валидацией
- ✅ `node_command_handler.c` - обработка команд с роутингом и защитой от дубликатов
- ✅ `node_telemetry_engine.c` - батчинг телеметрии
- ✅ Интеграция с ph_node (полная)
  - Обработка NodeConfig через node_config_handler
  - Обработка команд через node_command_handler
  - Публикация телеметрии через node_telemetry_engine

**Завершено:**
- ✅ ph_node успешно скомпилирован с интеграцией node_framework
- ✅ Все компоненты протестированы на компиляцию

**Следующие шаги:**
- ✅ Применение node_framework ко всем нодам (ph_node, ec_node, climate_node, pump_node) - ЗАВЕРШЕНО
- ⏳ Тестирование на реальном железе
- ⏳ Оптимизация и доработка по результатам тестирования

## Зависимости

- `mqtt_manager` - для публикации сообщений
- `config_storage` - для работы с NodeConfig
- `cjson` - для работы с JSON
- `esp_timer` - для timestamp
- `freertos` - для задач и синхронизации

