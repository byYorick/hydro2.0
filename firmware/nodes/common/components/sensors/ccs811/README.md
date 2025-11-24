# CCS811 Driver

Драйвер для CCS811 сенсора (CO₂/TVOC) для узлов ESP32.

## Описание

CCS811 - это цифровой сенсор для измерения концентрации CO₂ (углекислого газа) и TVOC (летучих органических соединений) в воздухе. Сенсор использует I²C интерфейс для связи с микроконтроллером.

## Возможности

- Измерение концентрации CO₂ в диапазоне 400-8192 ppm
- Измерение концентрации TVOC в диапазоне 0-1187 ppb
- Автоматическая инициализация и проверка сенсора
- Интеграция с i2c_cache для оптимизации I²C операций
- Интеграция с diagnostics для сбора метрик
- Обработка ошибок и использование stub значений при недоступности сенсора

## Использование

### Инициализация

```c
#include "ccs811.h"
#include "i2c_bus.h"

// Инициализация I²C шины (если еще не инициализирована)
i2c_bus_config_t i2c_config = {
    .sda_pin = 21,
    .scl_pin = 22,
    .clock_speed = 100000,
    .pullup_enable = true
};
i2c_bus_init_bus(I2C_BUS_1, &i2c_config);

// Инициализация CCS811
ccs811_config_t ccs_config = {
    .i2c_address = CCS811_I2C_ADDR_DEFAULT,  // 0x5A
    .i2c_bus = I2C_BUS_1,
    .measurement_mode = CCS811_MEAS_MODE_1SEC,
    .measurement_interval_ms = 1000
};
esp_err_t err = ccs811_init(&ccs_config);
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to initialize CCS811: %s", esp_err_to_name(err));
}
```

### Чтение данных

```c
ccs811_reading_t reading = {0};
esp_err_t err = ccs811_read(&reading);
if (err == ESP_OK && reading.valid) {
    ESP_LOGI(TAG, "CO₂: %u ppm, TVOC: %u ppb", reading.co2_ppm, reading.tvoc_ppb);
} else {
    ESP_LOGW(TAG, "Failed to read CCS811 or invalid data");
}
```

## Режимы измерений

- `CCS811_MEAS_MODE_IDLE` - режим ожидания (измерения не выполняются)
- `CCS811_MEAS_MODE_1SEC` - измерения каждую секунду
- `CCS811_MEAS_MODE_10SEC` - измерения каждые 10 секунд
- `CCS811_MEAS_MODE_60SEC` - измерения каждую минуту
- `CCS811_MEAS_MODE_250MS` - измерения каждые 250 мс

## I²C Адреса

- `CCS811_I2C_ADDR_DEFAULT` (0x5A) - адрес по умолчанию
- Альтернативный адрес: 0x5B (если ADDR пин подключен к VCC)

## Интеграция

### i2c_cache

Драйвер автоматически использует i2c_cache для кэширования результатов чтения (TTL 1000ms), что снижает нагрузку на I²C шину.

### diagnostics

Драйвер автоматически обновляет метрики diagnostics при каждом чтении:
- Успешные чтения увеличивают счетчик `read_count`
- Ошибки увеличивают счетчик `error_count`

## Обработка ошибок

При недоступности сенсора или ошибках чтения драйвер:
- Возвращает stub значения (CO₂: 650 ppm, TVOC: 15 ppb)
- Устанавливает `reading.valid = false`
- Логирует предупреждения
- Продолжает работу системы

## Зависимости

- `i2c_bus` - для работы с I²C шиной
- `i2c_cache` - для кэширования результатов (опционально)
- `diagnostics` - для сбора метрик (опционально)

## Спецификация

Согласно спецификации CCS811 от AMS (ams.com).

