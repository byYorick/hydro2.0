# Сводка по внедрению отправки ошибок в ноды

## Дата: 2025-01-28

## Выполнено

### ✅ ph_node
- **ph_node_init.c**: Добавлена отправка ошибок во всех критических местах инициализации
  - Config Storage (CRITICAL)
  - WiFi Manager (CRITICAL)
  - WiFi подключение (WARNING)
  - I2C Bus (ERROR)
  - pH Sensor (WARNING)
  - Pump Driver (ERROR)
  - MQTT Manager (CRITICAL)
  - Node Framework (CRITICAL)
  - Init Finalize (ERROR)
  - node_hello публикация (ERROR)
  
- **ph_node_framework_integration.c**: Добавлена отправка ошибок
  - Ошибки чтения pH сенсора (ERROR)
  - Ошибки публикации телеметрии (ERROR)
  - Ошибки калибровки (ERROR)
  - Сенсор не инициализирован (WARNING)

## Осталось сделать

### ⏳ ec_node
- Добавить `#include "node_state_manager.h"` в `ec_node_init.c`
- Добавить отправку ошибок в критических местах (аналогично ph_node)
- Добавить отправку ошибок в `ec_node_framework_integration.c` для ошибок чтения EC сенсора

### ⏳ pump_node
- Добавить `#include "node_state_manager.h"` в `pump_node_init.c`
- Добавить отправку ошибок в критических местах
- Добавить отправку ошибок в `pump_node_framework_integration.c` для ошибок работы насосов

### ⏳ climate_node
- Добавить `#include "node_state_manager.h"` в `climate_node_init.c`
- Добавить отправку ошибок в критических местах
- Добавить отправку ошибок в tasks для ошибок чтения SHT3x и CCS811

### ⏳ relay_node
- Добавить `#include "node_state_manager.h"` в `relay_node_init.c`
- Добавить отправку ошибок в критических местах
- Добавить отправку ошибок в `relay_node_framework_integration.c` для ошибок работы реле

### ⏳ light_node
- Добавить `#include "node_state_manager.h"` в `light_node_init.c`
- Добавить отправку ошибок в критических местах
- Добавить отправку ошибок в tasks для ошибок чтения светового сенсора

## Паттерн внедрения

### 1. Инициализация компонентов (init файлы)

```c
#include "node_state_manager.h"

// Критические ошибки (блокируют работу)
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Step X failed: %s", esp_err_to_name(err));
    node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "component_name", err, "Component initialization failed");
    return err;
}

// Некритические ошибки (можно продолжить)
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Step X failed: %s", esp_err_to_name(err));
    node_state_manager_report_error(ERROR_LEVEL_ERROR, "component_name", err, "Component initialization failed");
    // Continue
}
```

### 2. Ошибки чтения сенсоров (framework_integration или tasks)

```c
if (!read_success || isnan(value)) {
    ESP_LOGW(TAG, "Failed to read sensor value");
    node_state_manager_report_error(ERROR_LEVEL_ERROR, "sensor_name", ESP_ERR_INVALID_RESPONSE, "Failed to read sensor value");
    // Use stub value
}
```

### 3. Ошибки публикации MQTT

```c
if (err != ESP_OK) {
    ESP_LOGW(TAG, "Failed to publish: %s", esp_err_to_name(err));
    node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish telemetry");
}
```

### 4. Ошибки работы актуаторов

```c
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Actuator operation failed: %s", esp_err_to_name(err));
    node_state_manager_report_error(ERROR_LEVEL_ERROR, "actuator_name", err, "Actuator operation failed");
}
```

## Уровни ошибок

- **ERROR_LEVEL_CRITICAL**: Блокирует работу ноды, требует немедленного внимания
  - Инициализация критических компонентов (config_storage, wifi_manager, mqtt_manager, node_framework)
  - Ошибки драйверов актуаторов (pump_driver, relay_driver)
  
- **ERROR_LEVEL_ERROR**: Ошибка, требующая внимания, но нода может продолжать работу
  - Ошибки чтения сенсоров
  - Ошибки публикации MQTT
  - Ошибки инициализации некритических компонентов (I2C, OLED)
  
- **ERROR_LEVEL_WARNING**: Предупреждение, не критично
  - Сенсор не инициализирован (может быть временно)
  - WiFi подключение не удалось (будет повторная попытка)

## Результат

После внедрения всех изменений:
- ✅ Ноды не падают при ошибках
- ✅ Все ошибки отправляются на сервер через MQTT
- ✅ Backend создает Alerts для критических ошибок
- ✅ Метрики ошибок обновляются в БД
- ✅ Ноды переходят в safe_mode при критических ошибках





