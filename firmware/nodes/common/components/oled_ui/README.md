# OLED UI Component

Драйвер OLED дисплея для локального UI узлов ESP32 (SSD1306/SSD1309, 128x64).

## Описание

Компонент реализует локальный UI на OLED дисплее согласно спецификации:
- Драйвер для SSD1306/SSD1309 через I²C
- Система экранов (screens) с переключением
- Отображение статуса ноды (Wi-Fi, MQTT, значения сенсоров, ошибки)
- Интеграция с NodeConfig
- Отдельная FreeRTOS задача для обновления дисплея

## Использование

### Инициализация

```c
#include "oled_ui.h"

// Инициализация с конфигурацией
oled_ui_config_t config = {
    .i2c_address = 0x3C,
    .update_interval_ms = 500,
    .enable_task = true
};

esp_err_t err = oled_ui_init(OLED_UI_NODE_TYPE_PH, "nd-ph-1", &config);
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to initialize OLED UI");
    return err;
}
```

### Обновление модели данных

```c
oled_ui_model_t model = {0};
model.connections.wifi_connected = true;
model.connections.mqtt_connected = true;
model.ph_value = 6.5;
model.temperature_water = 22.3;
model.alert = false;
model.paused = false;

oled_ui_update_model(&model);
```

### Управление состоянием

```c
// Установка состояния
oled_ui_set_state(OLED_UI_STATE_NORMAL);

// Переключение экранов (в режиме NORMAL)
oled_ui_next_screen();
oled_ui_prev_screen();

// Обработка событий ввода
oled_ui_handle_encoder(1);  // Вращение вперед
oled_ui_handle_button();    // Нажатие кнопки
```

## Состояния UI

- `OLED_UI_STATE_BOOT` - загрузка узла
- `OLED_UI_STATE_WIFI_SETUP` - настройка Wi-Fi
- `OLED_UI_STATE_NORMAL` - нормальная работа
- `OLED_UI_STATE_ALERT` - критическая ошибка
- `OLED_UI_STATE_CALIBRATION` - калибровка датчиков
- `OLED_UI_STATE_SERVICE` - сервисное меню

## Экраны в режиме NORMAL

1. **Основной экран** - текущие значения сенсоров
2. **Экран каналов** - список каналов и их состояний
3. **Экран зоны** - информация о зоне/рецепте

## Требования

- ESP-IDF 5.x
- FreeRTOS
- i2c_bus компонент

## Документация

- Спецификация UI: `doc_ai/02_HARDWARE_FIRMWARE/NODE_OLED_UI_SPEC.md`
- Стандарты кодирования: `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`

