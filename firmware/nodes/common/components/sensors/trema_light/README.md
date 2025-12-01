# Trema Light Sensor Component

Драйвер для Trema датчика освещенности (iarduino DSL) через I²C.

## Описание

Компонент реализует драйвер для Trema датчика освещенности:
- Чтение значения освещенности (люкс) через I²C
- Поддержка кэширования I2C запросов для оптимизации
- Обработка ошибок и использование заглушек при отсутствии сенсора
- Автоматическая инициализация при первом чтении

## Использование

### Инициализация

```c
#include "trema_light.h"
#include "i2c_bus.h"

// Инициализация I²C шины (должна быть выполнена заранее)
i2c_bus_config_t i2c_config = {
    .sda_pin = 4,
    .scl_pin = 5,
    .clock_speed = 100000,
    .pullup_enable = true
};
i2c_bus_init_bus(I2C_BUS_0, &i2c_config);

// Инициализация датчика освещенности
if (trema_light_init(I2C_BUS_0)) {
    ESP_LOGI(TAG, "Light sensor initialized");
} else {
    ESP_LOGW(TAG, "Light sensor not found");
}
```

### Чтение значения

```c
float lux_value;
if (trema_light_read(&lux_value)) {
    ESP_LOGI(TAG, "Light: %.0f lux", lux_value);
} else {
    ESP_LOGW(TAG, "Failed to read light sensor, using stub value");
    // Функция автоматически вернет stub значение (500 lux)
}
```

### Проверка статуса

```c
// Проверка инициализации
if (trema_light_is_initialized()) {
    ESP_LOGI(TAG, "Sensor is initialized");
}

// Проверка использования stub значений
if (trema_light_is_using_stub_values()) {
    ESP_LOGW(TAG, "Using stub values (sensor not connected)");
}
```

## API

- `trema_light_init(i2c_bus_id_t i2c_bus)` - инициализация сенсора на указанной I²C шине
- `trema_light_read(float *lux)` - чтение значения освещенности (люкс)
- `trema_light_is_using_stub_values()` - проверка использования заглушек
- `trema_light_is_initialized()` - проверка инициализации сенсора

## Технические характеристики

- **I²C адрес**: 0x21 (по умолчанию)
- **Диапазон освещенности**: 0 - 65535 люкс
- **Разрешение**: 1 люкс
- **Model ID**: 0x06 (DEF_MODEL_DSL) или 0x1B (альтернативная версия)
- **Регистр значения**: 0x11 (REG_DSL_LUX_L) - 2 байта (LSB, MSB)
- **Формат данных**: Little-endian (LSB первый, затем MSB)
- **Формула**: `lux = (MSB << 8) | LSB`

## Протокол I²C

### Регистры

- **0x04 (REG_MODEL)**: Model ID регистр (1 байт)
  - Ожидаемое значение: 0x06 или 0x1B
  - Используется для проверки наличия датчика

- **0x11 (REG_DSL_LUX_L)**: Регистр значения освещенности (2 байта)
  - Байт 0 (LSB): младший байт значения
  - Байт 1 (MSB): старший байт значения
  - Формула: `lux = (data[1] << 8) | data[0]`

### Пример чтения

```c
// 1. Проверка наличия датчика (чтение Model ID)
uint8_t reg_model = 0x04;
uint8_t model_id;
i2c_bus_read_bus(I2C_BUS_0, 0x21, &reg_model, 1, &model_id, 1, 1000);

// 2. Чтение значения освещенности
uint8_t reg_lux = 0x11;
uint8_t data[2];
i2c_bus_read_bus(I2C_BUS_0, 0x21, &reg_lux, 1, data, 2, 1000);

// 3. Преобразование в люкс
uint16_t lux = ((uint16_t)data[1] << 8) | data[0];
```

## Кэширование

Компонент использует `i2c_cache` для оптимизации частых запросов:
- TTL кэша: 500 мс
- Автоматическое кэширование при успешном чтении
- Автоматическое использование кэша при повторных запросах

## Stub значения

При отсутствии датчика или ошибках чтения компонент возвращает stub значение:
- **Освещенность**: 500 люкс (типичное офисное освещение)
- Флаг `use_stub_values` устанавливается в `true`
- Функция `trema_light_is_using_stub_values()` возвращает `true`

## Требования

- ESP-IDF 5.x
- `i2c_bus` компонент
- `i2c_cache` компонент (опционально, для оптимизации)

## Интеграция

Компонент интегрирован в `light_node` и используется для:
- Периодического чтения значений освещенности (интервал 5 секунд)
- Публикации телеметрии через MQTT
- Отображения значений на OLED дисплее
- Обработки ошибок и отображения статуса I2C

## Пример использования в узле

```c
// В задаче опроса сенсоров
float lux_value;
if (trema_light_read(&lux_value)) {
    // Обновление OLED модели
    oled_ui_model_t model = {0};
    model.lux_value = lux_value;
    model.sensor_status.i2c_connected = true;
    model.sensor_status.has_error = false;
    oled_ui_update_model(&model);
    
    // Публикация телеметрии
    node_telemetry_publish_sensor("light", METRIC_TYPE_CUSTOM, 
                                  lux_value, "lux", 0, false, true);
} else {
    // Обработка ошибки
    oled_ui_model_t model = {0};
    model.lux_value = NAN;
    model.sensor_status.i2c_connected = false;
    model.sensor_status.has_error = true;
    strncpy(model.sensor_status.error_msg, "Read failed", 
            sizeof(model.sensor_status.error_msg) - 1);
    oled_ui_update_model(&model);
}
```

## Известные проблемы

- Некоторые версии датчика возвращают Model ID 0x1B вместо 0x06 - компонент поддерживает оба значения
- При отсутствии датчика на шине I²C могут возникать задержки из-за таймаутов - рекомендуется использовать кэширование

## Ссылки

- [iarduino Trema модуль датчика освещенности](https://iarduino.ru/shop/Sensory-Datchiki/datchik-osveshhennosti-lyuksmetr-i2c-trema-modul-v2-0.html)

