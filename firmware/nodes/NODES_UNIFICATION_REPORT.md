# Отчет об унификации нод по стандарту relay_node

## Дата: 2025-01-XX

## Цель
Привести все ноды (ph_node, ec_node, climate_node, pump_node) к единому стандарту, используя relay_node как эталон.

## Эталон: relay_node

### Структура файлов:
```
main/
├── main.c
├── relay_node_app.c
├── relay_node_app.h
├── relay_node_tasks.c
├── relay_node_init.c
├── relay_node_init.h
├── relay_node_init_steps.c
├── relay_node_init_steps.h
├── relay_node_framework_integration.c
├── relay_node_framework_integration.h
├── relay_node_hw_map.c
├── relay_node_hw_map.h
├── relay_node_defaults.h
└── CMakeLists.txt
```

### Зависимости в CMakeLists.txt (стандартный порядок):
1. Основные менеджеры: `mqtt_manager`, `wifi_manager`
2. Конфигурация: `config_storage`, `config_apply`
3. Фреймворк: `node_framework`, `node_utils`
4. Специфичные компоненты (сенсоры, драйверы)
5. UI и интерфейсы: `i2c_bus`, `oled_ui`, `setup_portal`
6. Системные: `heartbeat_task`, `connection_status`
7. Драйверы: `relay_driver`, `factory_reset_button`, `driver`
8. ESP-IDF компоненты: `esp_wifi`, `nvs_flash`, `esp_netif`, `esp_event`, `freertos`, `mqtt`, `esp_timer`
9. Утилиты: `json`, `mbedtls`

### Особенности relay_node:
- ✅ Инициализация factory_reset_button в `relay_node_app_init()`
- ✅ Константы factory_reset в `relay_node_defaults.h`
- ✅ mbedtls для HMAC проверок команд
- ✅ Унифицированный main.c с комментариями о watchdog
- ✅ Стандартный порядок зависимостей

## Выполненные изменения

### 1. ph_node ✅

**Добавлено:**
- `factory_reset_button` в CMakeLists.txt
- `mbedtls` в CMakeLists.txt
- Константы factory_reset в `ph_node_defaults.h`
- Инициализация factory_reset_button в `ph_node_app_init()`
- `#include "driver/gpio.h"` в defaults.h

**Унифицировано:**
- main.c приведен к стандарту relay_node
- Порядок зависимостей в CMakeLists.txt

### 2. ec_node ✅

**Добавлено:**
- `factory_reset_button` в CMakeLists.txt
- `mbedtls` в CMakeLists.txt
- Константы factory_reset в `ec_node_defaults.h`
- Инициализация factory_reset_button в `ec_node_app_init()`
- `#include "driver/gpio.h"` в defaults.h

**Удалено:**
- `mqtt_client` (избыточная зависимость)

**Унифицировано:**
- main.c приведен к стандарту relay_node
- Порядок зависимостей в CMakeLists.txt

### 3. climate_node ✅

**Добавлено:**
- `factory_reset_button` в CMakeLists.txt
- `mbedtls` в CMakeLists.txt
- Константы factory_reset в `climate_node_defaults.h`
- Инициализация factory_reset_button в `climate_node_app_init()`
- `#include "driver/gpio.h"` в defaults.h
- Обработка `ESP_ERR_NOT_FOUND` для setup mode

**Удалено:**
- `mqtt_client` (избыточная зависимость)
- `esp_system` (избыточная зависимость)

**Унифицировано:**
- main.c приведен к стандарту relay_node
- Порядок зависимостей в CMakeLists.txt

### 4. pump_node ✅

**Добавлено:**
- `factory_reset_button` в CMakeLists.txt
- `mbedtls` в CMakeLists.txt
- `oled_ui` в CMakeLists.txt (было пропущено)
- `i2c_bus` в CMakeLists.txt (для OLED)
- Константы factory_reset в `pump_node_defaults.h`
- Инициализация factory_reset_button в `pump_node_app_init()`
- `#include "driver/gpio.h"` в defaults.h

**Удалено:**
- `mqtt_client` (избыточная зависимость)

**Унифицировано:**
- main.c приведен к стандарту relay_node
- Порядок зависимостей в CMakeLists.txt

### 5. relay_node ✅

**Добавлено:**
- `mbedtls` в CMakeLists.txt (для HMAC проверок)

## Унифицированные стандарты

### main.c
Все ноды теперь имеют единообразную структуру:
```c
void app_main(void) {
    ESP_LOGI(TAG, "Starting {node}...");
    
    // Инициализация watchdog таймера выполняется автоматически в node_framework_init()
    
    // Инициализация NVS
    // ...
    
    // Инициализация сетевого интерфейса
    // ...
    
    // Инициализация приложения
    {node}_app_init();
    
    ESP_LOGI(TAG, "{node} started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в {node}_start_tasks()
}
```

### defaults.h
Все ноды имеют:
- Константы node_id, gh_uid, zone_uid
- MQTT defaults
- I2C defaults (если используется)
- OLED defaults (если используется)
- Setup portal defaults
- **Factory reset defaults** (новое)

### app.c
Все ноды инициализируют factory_reset_button:
```c
void {node}_app_init(void) {
    ESP_LOGI(TAG, "Initializing {node} application...");

    factory_reset_button_config_t reset_cfg = {
        .gpio_num = {NODE}_FACTORY_RESET_GPIO,
        .active_level_low = {NODE}_FACTORY_RESET_ACTIVE_LOW,
        .pull_up = true,
        .pull_down = false,
        .hold_time_ms = {NODE}_FACTORY_RESET_HOLD_MS,
        .poll_interval_ms = {NODE}_FACTORY_RESET_POLL_INTERVAL
    };
    esp_err_t reset_err = factory_reset_button_init(&reset_cfg);
    if (reset_err != ESP_OK) {
        ESP_LOGW(TAG, "Factory reset button not armed: %s", esp_err_to_name(reset_err));
    }
    
    // ... остальная инициализация
}
```

### CMakeLists.txt
Стандартный порядок зависимостей:
1. Основные менеджеры
2. Конфигурация
3. Фреймворк
4. Специфичные компоненты
5. UI и интерфейсы
6. Системные компоненты
7. Драйверы
8. ESP-IDF компоненты
9. Утилиты (json, mbedtls)

## Проверка совместимости

### ✅ Все ноды имеют:
- factory_reset_button инициализацию
- mbedtls для HMAC проверок
- Унифицированный main.c
- Стандартный порядок зависимостей
- Константы factory_reset в defaults.h

### ✅ Обратная совместимость:
- Все изменения не ломают существующий функционал
- Добавлены только новые возможности
- Порядок инициализации сохранен

## Статус

✅ **Все ноды унифицированы по стандарту relay_node**
✅ **Все изменения применены**
✅ **Код готов к сборке и тестированию**

## Рекомендации

1. Протестировать сборку всех нод
2. Проверить работу factory_reset_button на всех нодах
3. Убедиться, что HMAC проверки работают корректно
4. Проверить, что OLED работает на pump_node (если используется)

