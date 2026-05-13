# Trema EC Sensor Component

Драйвер для Trema EC-сенсора (iarduino) через I²C.

На **ec_node** используется **`I2C_BUS_1`** (отдельная линия, по умолчанию SDA 18 / SCL 19), как Trema pH на **ph_node**; шина 0 — OLED/INA209. См. `ec_node_defaults.h`, `TREMA_EC_I2C_BUS` в `trema_ec.c`.

Компонент реализует драйвер для Trema EC-датчика:
- Чтение EC значения (mS/cm) через I²C
- Чтение TDS значения (ppm)
- Калибровка (2 этапа)
- Температурная компенсация
- Обработка ошибок и использование заглушек при отсутствии сенсора

**Снимок телеметрии (`trema_ec_measurement_t`):** при `trema_ec_push_telemetry_snapshot` в очередь кладутся EC (mS/cm), raw EC, **tds_ppm** и флаг stub — узел публикует MQTT из очереди без повторного `trema_ec_get_tds` в callback.

## Использование

### Инициализация

```c
#include "trema_ec.h"
#include "i2c_bus.h"

// Инициализация I²C шины 1 для ec_node (Trema EC только на этой шине; шина 0 — OLED/INA)
i2c_bus_config_t i2c_config = {
    .sda_pin = 18,
    .scl_pin = 19,
    .clock_speed = 100000,
    .pullup_enable = false
};
i2c_bus_init_bus(I2C_BUS_1, &i2c_config);

// Инициализация EC-сенсора
if (trema_ec_init()) {
    ESP_LOGI(TAG, "EC sensor initialized");
} else {
    ESP_LOGW(TAG, "EC sensor not found");
}
```

### Чтение значения

```c
float ec_value;
if (trema_ec_read(&ec_value)) {
    ESP_LOGI(TAG, "EC: %.2f mS/cm", ec_value);
} else {
    ESP_LOGW(TAG, "Failed to read EC");
}

// Чтение TDS значения
uint16_t tds = trema_ec_get_tds();
ESP_LOGI(TAG, "TDS: %u ppm", tds);
```

### Калибровка

```c
// Этап 1: калибровка на известное TDS значение
if (trema_ec_calibrate(1, 1413)) {  // 1413 ppm (стандартный раствор)
    ESP_LOGI(TAG, "Calibration stage 1 started");
}

// Этап 2: калибровка на другое TDS значение
if (trema_ec_calibrate(2, 2764)) {  // 2764 ppm
    ESP_LOGI(TAG, "Calibration stage 2 started");
}

// Проверка статуса калибровки
uint8_t cal_status = trema_ec_get_calibration_status();
ESP_LOGI(TAG, "Calibration status: %d", cal_status);
```

### Температурная компенсация

```c
// Установка температуры для компенсации
if (trema_ec_set_temperature(25.0f)) {
    ESP_LOGI(TAG, "Temperature compensation set to 25°C");
}
```

## API

- `trema_ec_init()` - инициализация сенсора
- `trema_ec_read(float *ec)` - чтение EC значения (mS/cm)
- `trema_ec_get_tds()` - получение TDS значения (ppm)
- `trema_ec_calibrate(uint8_t stage, uint16_t known_tds)` - калибровка
- `trema_ec_get_calibration_status()` - получение статуса калибровки
- `trema_ec_set_temperature(float temperature)` - установка температуры для компенсации
- `trema_ec_get_conductivity()` - получение последнего значения проводимости
- `trema_ec_is_using_stub_values()` - проверка использования заглушек

## Технические характеристики

- I²C (7-bit): **первый пробуемый адрес** — **`TREMA_EC_ADDR` = 0x09** (заводской дефолт Trema Flash-I²C / iarduino; см. [карточку iarduino](https://iarduino.ru/shop/Sensory-Datchiki/solemer-tds-ec-flash-i2c.html), [iarduino_I2C_TDS](https://github.com/tremaru/iarduino_I2C_TDS)). Если модуль не отвечает на 0x09, `trema_ec_init()` перебирает **0x08–0x77**; фактический адрес после init — **`trema_ec_get_i2c_address()`**.
- **Зафиксировано в документации репозитория:** на референс-железе `ec_node` модуль отвечает по адресу **0x08** (адрес мог быть ранее записан во FLASH модуля). См. `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`, раздел 2.2.
- Диапазон EC: 0.0 - 10.0 mS/cm
- Диапазон TDS: 0 - 10000 ppm
- Разрешение: 0.001 mS/cm
- Температурная компенсация: 0 - 63.75 °C (шаг 0.25 °C)
- Калибровка: 2 этапа

## Требования

- ESP-IDF 5.x
- i2c_bus компонент

## Интеграция

Компонент интегрирован в `ec_node` и используется для:
- Периодического чтения EC и TDS значений
- Публикации телеметрии через MQTT
- Обработки команд калибровки

