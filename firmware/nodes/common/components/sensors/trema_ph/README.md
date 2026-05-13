# Trema pH Sensor Component

Драйвер для Trema pH-сенсора (iarduino) через I²C.

## Соответствие iarduino и флаги сборки

После успешного обнаружения модуля `trema_ph_init()` по умолчанию выполняет **программный reset** (как
`iarduino_I2C_pH::_begin` → `reset()`), затем паузу **5 ms** (`TREMA_PH_POST_INIT_RESET_MS`), чтобы регистры
модуля соответствовали состоянию после `begin()` в Arduino.

| Макрос | По умолчанию | Назначение |
|--------|----------------|------------|
| `TREMA_PH_INIT_SOFTWARE_RESET` | `1` | `1` — soft reset после probe; `0` — только задержка 5 ms без сброса (быстрее, не 1:1 с iarduino). |
| `TREMA_PH_POST_INIT_RESET_MS` | `5` | Пауза после reset при init (в оригинале `delay(5)`). |
| `TREMA_PH_READ_SOFT_RESET_RECOVERY` | `0` | `1` — во второй фазе `trema_ph_read` при сыром `0xFFFF` выполняется soft reset и доп. попытки (расширение, не из оригинального `getPH`). |

Переопределение (чтобы **не** сбрасывать модуль при каждом `trema_ph_init`):

1. В `trema_ph/CMakeLists.txt` сразу после `idf_component_register(...)` добавьте строку  
   `target_compile_definitions(${COMPONENT_LIB} PRIVATE TREMA_PH_INIT_SOFTWARE_RESET=0)`  
   (так макрос попадёт в компиляцию `trema_ph.c`).

2. Либо задайте значение до включения заголовка только в отдельной обёртке (редко нужно).

## Интеграция ph_node (один poll за тик)

На **ph_node** периодический путь: **`ph_node_ph_poll_sensor_once()`** — лёгкий **`trema_ph_probe_chip_quick()`**
(байт `REG_MODEL` и несколько типичных адресов, без полного discovery), при необходимости **`trema_ph_init()`**,
затем **`trema_ph_read()`** (снимок в очереди драйвера). MQTT и OLED берут значение только из
**`trema_ph_try_cached_measurement`**; для индикации «модуль на шине» в том же тике —
**`ph_node_ph_last_poll_chip_present()`**. Полный **`trema_ph_probe_presence()`** / discovery остаётся для
диагностики и init.

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
    .pullup_enable = false
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

