# Исправление падения ESP32 при обработке конфига

## Проблема
```
Guru Meditation Error: Core 0 panic'ed (LoadProhibited). Exception was unhandled.
Backtrace: vListInsert -> prvAddCurrentTaskToDelayedList -> vTaskPlaceOnEventList -> xQueueSemaphoreTake -> i2c_bus_write_bus -> ssd1306_update_display -> render_boot_screen -> oled_ui_refresh -> oled_ui_stop_init_steps -> climate_node_init_step_finalize
```

## Причина
Падение происходит при попытке использовать I2C мьютекс, который может быть:
1. Не инициализирован (NULL)
2. Использован в неправильном контексте (из MQTT callback)

## Исправления

### 1. Добавлена проверка мьютекса на NULL в I2C функциях
**Файл:** `firmware/nodes/common/components/i2c_bus/i2c_bus.c`

Добавлена проверка `if (bus->mutex == NULL)` перед использованием мьютекса в:
- `i2c_bus_read_bus()` - чтение данных
- `i2c_bus_write_bus()` - запись данных  
- `i2c_bus_scan_bus()` - сканирование шины

Это предотвращает падение при попытке использовать неинициализированный мьютекс.

### 2. Добавлен заголовочный файл esp_mac.h
**Файл:** `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`

Добавлен `#include "esp_mac.h"` для функции `esp_efuse_mac_get_default()`.

### 3. Улучшена обработка ошибок в oled_ui_stop_init_steps
**Файл:** `firmware/nodes/common/components/oled_ui/oled_ui.c`

Добавлена проверка результата `oled_ui_refresh()` и логирование ошибок.

## Результат
- Сборка прошла успешно
- Все проверки мьютекса добавлены
- Защита от использования неинициализированного мьютекса

## Рекомендации
1. Протестировать прошивку на реальном устройстве
2. Проверить, что мьютекс I2C инициализируется до первого использования
3. Убедиться, что `oled_ui_stop_init_steps()` не вызывается из MQTT callback

