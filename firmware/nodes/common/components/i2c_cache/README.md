# I2C Cache Component

Компонент для кэширования результатов **чтения** I²C (не транспортный слой; поверх `i2c_bus_read*`).

## Политика (F)

- **Только успешные** реальные чтения попадают в кэш (`put` после `err == ESP_OK`).
- **TTL** задаётся вызовом `get`/`put` (или `default_ttl_ms` при init). Устаревшие записи при `get` отбрасываются (`ESP_ERR_NOT_FOUND`).
- **Инвалидация** конкретного ключа `(bus_id, dev, reg…)` обязательна после: программного reset чипа, смены 7-bit адреса, калибровки, любого события, где регистры могли измениться «мимо» кэша. Примеры: `trema_ph` — `i2c_cache_invalidate` вокруг soft reset; при смене адреса — invalidate по старому/новому ключу.
- **Не кэшировать** потоковые/критичные по свежести регистры без явного короткого TTL.
- **Порядок блокировок:** как у `i2c_bus` — mutex драйвера, затем `i2c_cache_*` и `i2c_bus_*` (см. `i2c_bus/README.md`).
- Ограничения размера: регистр до 4 байт, данные до 16 байт на запись кэша.

## Описание

Компонент предоставляет:
- Кэширование результатов чтения I2C устройств
- TTL (Time To Live) для записей кэша
- Автоматическая инвалидация устаревших записей
- Метрики использования кэша (hits, misses, evictions)
- Thread-safe доступ через mutex
- LRU eviction при переполнении кэша

## Использование

### Инициализация

```c
#include "i2c_cache.h"

// Инициализация с конфигурацией по умолчанию
esp_err_t err = i2c_cache_init(NULL);

// Или с кастомной конфигурацией
i2c_cache_config_t config = {
    .max_entries = 64,
    .default_ttl_ms = 2000,  // 2 секунды
    .enable_metrics = true
};
err = i2c_cache_init(&config);
```

### Использование кэша

```c
// Попытка получить данные из кэша
uint8_t data[2];
esp_err_t err = i2c_cache_get(I2C_BUS_0, 0x40, &reg_addr, 1, data, 2, 1000);
if (err == ESP_OK) {
    // Данные найдены в кэше
    ESP_LOGI(TAG, "Cache hit: data = 0x%02X 0x%02X", data[0], data[1]);
} else if (err == ESP_ERR_NOT_FOUND) {
    err = i2c_bus_read_bus(I2C_BUS_0, 0x40, &reg_addr, 1, data, 2, 1000);
    if (err == ESP_OK) {
        // Сохраняем в кэш
        i2c_cache_put(I2C_BUS_0, 0x40, &reg_addr, 1, data, 2, 1000);
    }
}
```

### Инвалидация кэша

```c
// Инвалидировать конкретную запись
i2c_cache_invalidate(I2C_BUS_0, 0x40, &reg_addr, 1);

// Очистить весь кэш
i2c_cache_clear();
```

### Метрики

```c
i2c_cache_metrics_t metrics;
if (i2c_cache_get_metrics(&metrics) == ESP_OK) {
    ESP_LOGI(TAG, "Cache hits: %u, misses: %u, hit rate: %.2f%%",
             metrics.cache_hits,
             metrics.cache_misses,
             metrics.cache_hits + metrics.cache_misses > 0 ?
                 (float)metrics.cache_hits * 100.0f / (metrics.cache_hits + metrics.cache_misses) : 0.0f);
}
```

## Интеграция с драйверами сенсоров

Для использования кэша в драйверах сенсоров рекомендуется обернуть вызовы `i2c_bus_read()`:

```c
// В trema_ph.c или trema_ec.c
uint8_t reg_ph = REG_PH_pH;
uint8_t data[2];

// Попытка получить из кэша
esp_err_t err = i2c_cache_get(I2C_BUS_1, TREMA_PH_ADDR, &reg_ph, 1, data, 2, 1000);
if (err != ESP_OK) {
    // Читаем из I2C
    err = i2c_bus_read_bus(I2C_BUS_1, TREMA_PH_ADDR, &reg_ph, 1, data, 2, 1000);
    if (err == ESP_OK) {
        // Сохраняем в кэш
        i2c_cache_put(I2C_BUS_1, TREMA_PH_ADDR, &reg_ph, 1, data, 2, 1000);
    }
}
```

## Конфигурация

- **max_entries**: Максимальное количество записей в кэше (по умолчанию 32)
- **default_ttl_ms**: TTL по умолчанию в миллисекундах (по умолчанию 1000)
- **enable_metrics**: Включить сбор метрик (по умолчанию true)

## Ограничения

- Максимальная длина адреса регистра: 4 байта
- Максимальная длина данных: 16 байт
- Размер хеш-таблицы: 16 (можно увеличить при необходимости)

## Производительность

Кэш использует хеш-таблицу для O(1) доступа в среднем случае. При переполнении используется LRU eviction (удаление самой старой записи).

## Зависимости

- `freertos` - для mutex
- `esp_timer` - для timestamp
- `esp_system` - для стандартных типов

