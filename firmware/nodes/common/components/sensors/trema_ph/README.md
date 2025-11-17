# Trema pH Sensor Component

Драйвер для Trema pH-сенсора (iarduino) через I²C.

## Описание

Компонент реализует драйвер для Trema pH-датчика:
- Чтение pH значения через I²C
- Калибровка (2 этапа: pH 7.0 и pH 4.0/10.0)
- Проверка стабильности измерений
- Обработка ошибок и использование заглушек при отсутствии сенсора

## Использование

### Инициализация

```c
#include "trema_ph.h"
#include "i2c_bus.h"

// Инициализация I²C шины (должна быть выполнена заранее)
i2c_bus_config_t i2c_config = {
    .sda_pin = 21,
    .scl_pin = 22,
    .clock_speed = 100000,
    .pullup_enable = true
};
i2c_bus_init(&i2c_config);

// Инициализация pH-сенсора
if (trema_ph_init()) {
    ESP_LOGI(TAG, "pH sensor initialized");
} else {
    ESP_LOGW(TAG, "pH sensor not found");
}
```

### Чтение значения

```c
float ph_value;
if (trema_ph_read(&ph_value)) {
    ESP_LOGI(TAG, "pH: %.2f", ph_value);
} else {
    ESP_LOGW(TAG, "Failed to read pH");
}
```

### Калибровка

```c
// Этап 1: калибровка на pH 7.0
if (trema_ph_calibrate(1, 7.0f)) {
    ESP_LOGI(TAG, "Calibration stage 1 started");
}

// Этап 2: калибровка на pH 4.0 или 10.0
if (trema_ph_calibrate(2, 4.0f)) {
    ESP_LOGI(TAG, "Calibration stage 2 started");
}

// Проверка статуса калибровки
uint8_t cal_status = trema_ph_get_calibration_status();
ESP_LOGI(TAG, "Calibration status: %d", cal_status);
```

### Проверка стабильности

```c
// Проверка текущей стабильности
if (trema_ph_get_stability()) {
    ESP_LOGI(TAG, "Measurement is stable");
}

// Ожидание стабильного измерения
if (trema_ph_wait_for_stable_reading(5000)) {
    ESP_LOGI(TAG, "Measurement is stable");
} else {
    ESP_LOGW(TAG, "Timeout waiting for stable reading");
}
```

## API

- `trema_ph_init()` - инициализация сенсора
- `trema_ph_read(float *ph)` - чтение pH значения
- `trema_ph_calibrate(uint8_t stage, float known_pH)` - калибровка
- `trema_ph_get_calibration_status()` - получение статуса калибровки
- `trema_ph_get_calibration_result()` - проверка результата калибровки
- `trema_ph_get_stability()` - проверка стабильности измерения
- `trema_ph_wait_for_stable_reading(uint32_t timeout_ms)` - ожидание стабильного измерения
- `trema_ph_get_value()` - получение последнего значения
- `trema_ph_reset()` - сброс сенсора
- `trema_ph_is_using_stub_values()` - проверка использования заглушек

## Технические характеристики

- I²C адрес: 0x0A
- Диапазон pH: 0.0 - 14.0
- Разрешение: 0.001 pH
- Калибровка: 2 этапа (pH 7.0 и pH 4.0/10.0)

## Требования

- ESP-IDF 5.x
- i2c_bus компонент

## Интеграция

Компонент интегрирован в `ph_node` и используется для:
- Периодического чтения pH значений
- Публикации телеметрии через MQTT
- Обработки команд калибровки

