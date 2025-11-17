# pH Sensor Component

Драйвер pH-сенсора для узлов ESP32.

## Описание

Компонент реализует драйвер для pH-датчика:
- Чтение ADC значения (аналоговый pH-датчик)
- Калибровка (2-3 точки) согласно NodeConfig
- Температурная компенсация (если доступна температура)
- Медианный фильтр для сглаживания значений
- Проверка диапазона значений (4.0-10.0 pH)
- Интеграция с i2c_bus (если используется I²C датчик)

## Использование

### Инициализация

```c
#include "ph_sensor.h"

ph_calibration_point_t cal_points[] = {
    {.ph_value = 4.0f, .voltage = 1.2f},
    {.ph_value = 7.0f, .voltage = 2.1f},
    {.ph_value = 10.0f, .voltage = 3.0f}
};

ph_sensor_config_t config = {
    .type = PH_SENSOR_TYPE_ANALOG,
    .adc_channel = ADC1_CHANNEL_0,
    .cal_points = cal_points,
    .cal_points_count = 3,
    .cal_method = PH_CALIBRATION_LINEAR,
    .min_value = 4.0f,
    .max_value = 10.0f,
    .warning_low = 5.5f,
    .warning_high = 7.5f,
    .enable_temp_compensation = true,
    .temp_coefficient = 0.03f
};

esp_err_t err = ph_sensor_init(&config);
```

### Чтение значения

```c
ph_sensor_reading_t reading;
float temperature = 22.5f;  // Температура для компенсации

esp_err_t err = ph_sensor_read(&reading, temperature);
if (err == ESP_OK && reading.valid) {
    ESP_LOGI(TAG, "pH: %.2f (raw: %.2f)", reading.ph_value, reading.raw_value);
    if (reading.warning) {
        ESP_LOGW(TAG, "pH value out of warning range");
    }
}
```

## Требования

- ESP-IDF 5.x
- i2c_bus компонент (для I²C датчиков)
- config_storage (для init_from_config)

