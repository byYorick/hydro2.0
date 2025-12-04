# Исправление падения ESP32 при обработке конфига (v2)

## Проблема
```
Guru Meditation Error: Core 0 panic'ed (LoadProhibited). Exception was unhandled.
Backtrace: vListInsert -> prvAddCurrentTaskToDelayedList -> vTaskPlaceOnEventList -> xQueueSemaphoreTake -> i2c_master_transmit -> i2c_bus_write_bus -> ssd1306_update_display -> render_boot_screen -> oled_ui_refresh -> oled_ui_stop_init_steps -> climate_node_init_step_finalize
```

## Причина
Падение происходит при попытке использовать I2C мьютекс или bus_handle, которые могут быть:
1. Не инициализированы (NULL)
2. Использованы в неправильном контексте (race condition между основным потоком и MQTT callback)

## Исправления

### 1. Добавлена проверка мьютекса на NULL в I2C функциях
**Файл:** `firmware/nodes/common/components/i2c_bus/i2c_bus.c`

Добавлена проверка `if (bus->mutex == NULL)` перед использованием мьютекса в:
- `i2c_bus_read_bus()` - чтение данных
- `i2c_bus_write_bus()` - запись данных  
- `i2c_bus_scan_bus()` - сканирование шины

### 2. Добавлена проверка bus_handle на NULL
**Файл:** `firmware/nodes/common/components/i2c_bus/i2c_bus.c`

Добавлена проверка `if (bus->bus_handle == NULL)` перед использованием bus_handle в:
- `i2c_bus_read_bus()` - чтение данных
- `i2c_bus_write_bus()` - запись данных
- `i2c_bus_scan_bus()` - сканирование шины

### 3. Добавлена проверка render_mutex на NULL в OLED функциях
**Файл:** `firmware/nodes/common/components/oled_ui/oled_ui.c`

Добавлена проверка `if (s_ui.render_mutex == NULL)` в:
- `render_boot_screen()` - отрисовка экрана загрузки
- `oled_ui_refresh()` - обновление OLED дисплея

### 4. Улучшена обработка ошибок в oled_ui_stop_init_steps
**Файл:** `firmware/nodes/common/components/oled_ui/oled_ui.c`

Добавлена проверка результата `oled_ui_refresh()` и логирование ошибок.

### 5. Улучшена обработка ошибок в climate_node_init_step_finalize
**Файл:** `firmware/nodes/climate_node/main/climate_node_init_steps.c`

Добавлена проверка результата `oled_ui_stop_init_steps()` и логирование ошибок.

## Результат
- Сборка прошла успешно
- Все проверки мьютекса и bus_handle добавлены
- Защита от использования неинициализированных указателей

## Рекомендации
1. Протестировать прошивку на реальном устройстве
2. Проверить, что мьютекс I2C и bus_handle инициализируются до первого использования
3. Убедиться, что `oled_ui_stop_init_steps()` не вызывается из MQTT callback одновременно с основным потоком
4. Рассмотреть возможность отложить вызов `oled_ui_stop_init_steps()` до завершения обработки конфига

