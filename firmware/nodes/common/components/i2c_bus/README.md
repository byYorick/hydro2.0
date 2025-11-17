# I²C Bus Component

Общий драйвер I²C шины с thread-safe доступом для всех ESP32-нод системы Hydro 2.0.

## Описание

Компонент предоставляет единый интерфейс для работы с I²C шиной:
- Инициализация с конфигурируемыми параметрами (SDA, SCL, скорость)
- Thread-safe доступ через mutex
- Функции чтения/записи с обработкой ошибок и retry логикой
- I²C recovery при ошибках (reset bus)
- Интеграция с NodeConfig

## Использование

### Инициализация

```c
#include "i2c_bus.h"

// Ручная инициализация
i2c_bus_config_t config = {
    .sda_pin = 21,
    .scl_pin = 22,
    .clock_speed = 100000,  // 100 kHz
    .pullup_enable = true
};

esp_err_t err = i2c_bus_init(&config);
if (err != ESP_OK) {
    ESP_LOGE(TAG, "Failed to initialize I²C bus");
    return err;
}

// Или инициализация из NodeConfig
err = i2c_bus_init_from_config();
```

### Чтение/запись

```c
// Чтение одного байта из регистра
uint8_t value;
esp_err_t err = i2c_bus_read_byte(0x40, 0x00, &value, 1000);
if (err == ESP_OK) {
    ESP_LOGI(TAG, "Read value: 0x%02X", value);
}

// Запись одного байта в регистр
err = i2c_bus_write_byte(0x40, 0x00, 0x12, 1000);

// Чтение нескольких байт
uint8_t buffer[16];
err = i2c_bus_read(0x40, NULL, 0, buffer, 16, 1000);

// Запись с адресом регистра
uint8_t reg = 0x10;
uint8_t data[] = {0x01, 0x02, 0x03};
err = i2c_bus_write(0x40, &reg, 1, data, 3, 1000);
```

### Сканирование шины

```c
uint8_t addresses[128];
size_t found_count = 0;

esp_err_t err = i2c_bus_scan(addresses, 128, &found_count);
if (err == ESP_OK) {
    ESP_LOGI(TAG, "Found %zu I²C device(s)", found_count);
    for (size_t i = 0; i < found_count; i++) {
        ESP_LOGI(TAG, "  Device at 0x%02X", addresses[i]);
    }
}
```

### Восстановление при ошибках

```c
// Автоматическое восстановление при ошибках чтения/записи
// Или ручное восстановление
esp_err_t err = i2c_bus_recover();
```

## Интеграция с NodeConfig

Компонент может автоматически загружать конфигурацию из NodeConfig:

```json
{
  "hardware": {
    "i2c": {
      "sda": 21,
      "scl": 22,
      "speed": 100000
    }
  }
}
```

## API

### Инициализация

- `i2c_bus_init(const i2c_bus_config_t *config)` - инициализация с конфигурацией
- `i2c_bus_init_from_config(void)` - инициализация из NodeConfig
- `i2c_bus_deinit(void)` - деинициализация
- `i2c_bus_is_initialized(void)` - проверка инициализации

### Чтение/запись

- `i2c_bus_read()` - чтение данных с указанием адреса регистра
- `i2c_bus_write()` - запись данных с указанием адреса регистра
- `i2c_bus_read_byte()` - чтение одного байта из регистра
- `i2c_bus_write_byte()` - запись одного байта в регистр

### Утилиты

- `i2c_bus_scan()` - сканирование шины для поиска устройств
- `i2c_bus_recover()` - восстановление шины при ошибках

## Требования

- ESP-IDF 5.x
- FreeRTOS
- config_storage (для i2c_bus_init_from_config)

## Документация

- Стандарты кодирования: `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`
- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`

