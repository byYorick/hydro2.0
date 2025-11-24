/**
 * @file i2c_cache.c
 * @brief Реализация кэша для результатов I2C операций
 * 
 * Компонент реализует кэширование результатов чтения I2C устройств с TTL.
 * Использует хеш-таблицу для быстрого доступа к записям.
 */

#include "i2c_cache.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdlib.h>
#include <limits.h>

static const char *TAG = "i2c_cache";

// Константы
#define I2C_CACHE_DEFAULT_MAX_ENTRIES 32
#define I2C_CACHE_DEFAULT_TTL_MS 1000
#define I2C_CACHE_MAX_REG_ADDR_LEN 4
#define I2C_CACHE_MAX_DATA_LEN 16
#define I2C_CACHE_HASH_TABLE_SIZE 16  // Размер хеш-таблицы (степень 2 для эффективности)

/**
 * @brief Запись в кэше
 */
typedef struct i2c_cache_entry {
    uint8_t bus_id;
    uint8_t device_addr;
    uint8_t reg_addr[I2C_CACHE_MAX_REG_ADDR_LEN];
    size_t reg_addr_len;
    uint8_t data[I2C_CACHE_MAX_DATA_LEN];
    size_t data_len;
    int64_t timestamp_us;  // Время создания записи в микросекундах
    uint32_t ttl_ms;       // TTL в миллисекундах
    struct i2c_cache_entry *next;  // Для цепочки в хеш-таблице
} i2c_cache_entry_t;

/**
 * @brief Состояние кэша
 */
typedef struct {
    i2c_cache_entry_t *hash_table[I2C_CACHE_HASH_TABLE_SIZE];
    size_t max_entries;
    uint32_t default_ttl_ms;
    size_t current_entries;
    bool initialized;
    SemaphoreHandle_t mutex;
    i2c_cache_metrics_t metrics;
    bool metrics_enabled;
} i2c_cache_state_t;

static i2c_cache_state_t s_cache = {0};

/**
 * @brief Вычислить хеш для ключа кэша
 */
static uint32_t i2c_cache_hash(uint8_t bus_id, uint8_t device_addr,
                                const uint8_t *reg_addr, size_t reg_addr_len) {
    uint32_t hash = (uint32_t)bus_id * 31;
    hash = hash * 31 + (uint32_t)device_addr;
    
    if (reg_addr != NULL && reg_addr_len > 0) {
        for (size_t i = 0; i < reg_addr_len && i < I2C_CACHE_MAX_REG_ADDR_LEN; i++) {
            hash = hash * 31 + (uint32_t)reg_addr[i];
        }
    }
    
    return hash % I2C_CACHE_HASH_TABLE_SIZE;
}

/**
 * @brief Сравнить ключи кэша
 */
static bool i2c_cache_key_match(const i2c_cache_entry_t *entry,
                                 uint8_t bus_id, uint8_t device_addr,
                                 const uint8_t *reg_addr, size_t reg_addr_len) {
    if (entry->bus_id != bus_id || entry->device_addr != device_addr) {
        return false;
    }
    
    if (entry->reg_addr_len != reg_addr_len) {
        return false;
    }
    
    if (reg_addr_len == 0) {
        return true;
    }
    
    return memcmp(entry->reg_addr, reg_addr, reg_addr_len) == 0;
}

/**
 * @brief Проверить, не устарела ли запись
 */
static bool i2c_cache_entry_is_valid(const i2c_cache_entry_t *entry) {
    if (entry == NULL) {
        return false;
    }
    
    int64_t current_time_us = esp_timer_get_time();
    int64_t elapsed_us = current_time_us - entry->timestamp_us;
    uint32_t elapsed_ms = (uint32_t)(elapsed_us / 1000);
    
    return elapsed_ms < entry->ttl_ms;
}

/**
 * @brief Найти запись в кэше
 */
static i2c_cache_entry_t* i2c_cache_find_entry(uint8_t bus_id, uint8_t device_addr,
                                                const uint8_t *reg_addr, size_t reg_addr_len) {
    uint32_t hash = i2c_cache_hash(bus_id, device_addr, reg_addr, reg_addr_len);
    i2c_cache_entry_t *entry = s_cache.hash_table[hash];
    
    while (entry != NULL) {
        if (i2c_cache_key_match(entry, bus_id, device_addr, reg_addr, reg_addr_len)) {
            return entry;
        }
        entry = entry->next;
    }
    
    return NULL;
}

/**
 * @brief Удалить устаревшие записи
 */
static void i2c_cache_cleanup_expired(void) {
    int64_t current_time_us = esp_timer_get_time();
    
    for (size_t i = 0; i < I2C_CACHE_HASH_TABLE_SIZE; i++) {
        i2c_cache_entry_t **prev = &s_cache.hash_table[i];
        i2c_cache_entry_t *entry = s_cache.hash_table[i];
        
        while (entry != NULL) {
            int64_t elapsed_us = current_time_us - entry->timestamp_us;
            uint32_t elapsed_ms = (uint32_t)(elapsed_us / 1000);
            
            if (elapsed_ms >= entry->ttl_ms) {
                // Удаляем устаревшую запись
                *prev = entry->next;
                free(entry);
                s_cache.current_entries--;
                if (s_cache.metrics_enabled) {
                    s_cache.metrics.cache_invalidations++;
                }
                entry = *prev;
            } else {
                prev = &entry->next;
                entry = entry->next;
            }
        }
    }
}

/**
 * @brief Удалить самую старую запись (LRU eviction)
 */
static void i2c_cache_evict_oldest(void) {
    i2c_cache_entry_t *oldest_entry = NULL;
    i2c_cache_entry_t **oldest_prev = NULL;
    int64_t oldest_timestamp = INT64_MAX;
    
    for (size_t i = 0; i < I2C_CACHE_HASH_TABLE_SIZE; i++) {
        i2c_cache_entry_t **prev = &s_cache.hash_table[i];
        i2c_cache_entry_t *entry = s_cache.hash_table[i];
        
        while (entry != NULL) {
            if (entry->timestamp_us < oldest_timestamp) {
                oldest_timestamp = entry->timestamp_us;
                oldest_entry = entry;
                oldest_prev = prev;
            }
            prev = &entry->next;
            entry = entry->next;
        }
    }
    
    if (oldest_entry != NULL && oldest_prev != NULL) {
        *oldest_prev = oldest_entry->next;
        free(oldest_entry);
        s_cache.current_entries--;
        if (s_cache.metrics_enabled) {
            s_cache.metrics.cache_evictions++;
        }
    }
}

esp_err_t i2c_cache_init(const i2c_cache_config_t *config) {
    if (s_cache.initialized) {
        ESP_LOGW(TAG, "I2C cache already initialized");
        return ESP_OK;
    }
    
    ESP_LOGI(TAG, "Initializing I2C cache...");
    
    // Установка конфигурации
    if (config != NULL) {
        s_cache.max_entries = config->max_entries > 0 ? config->max_entries : I2C_CACHE_DEFAULT_MAX_ENTRIES;
        s_cache.default_ttl_ms = config->default_ttl_ms > 0 ? config->default_ttl_ms : I2C_CACHE_DEFAULT_TTL_MS;
        s_cache.metrics_enabled = config->enable_metrics;
    } else {
        s_cache.max_entries = I2C_CACHE_DEFAULT_MAX_ENTRIES;
        s_cache.default_ttl_ms = I2C_CACHE_DEFAULT_TTL_MS;
        s_cache.metrics_enabled = true;
    }
    
    // Инициализация хеш-таблицы
    memset(s_cache.hash_table, 0, sizeof(s_cache.hash_table));
    s_cache.current_entries = 0;
    
    // Создание mutex
    s_cache.mutex = xSemaphoreCreateMutex();
    if (s_cache.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }
    
    // Инициализация метрик
    memset(&s_cache.metrics, 0, sizeof(s_cache.metrics));
    
    s_cache.initialized = true;
    
    ESP_LOGI(TAG, "I2C cache initialized: max_entries=%zu, default_ttl_ms=%u",
             s_cache.max_entries, s_cache.default_ttl_ms);
    
    return ESP_OK;
}

esp_err_t i2c_cache_deinit(void) {
    if (!s_cache.initialized) {
        return ESP_OK;
    }
    
    ESP_LOGI(TAG, "Deinitializing I2C cache...");
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take mutex for deinit");
        return ESP_ERR_TIMEOUT;
    }
    
    // Очистка всех записей
    for (size_t i = 0; i < I2C_CACHE_HASH_TABLE_SIZE; i++) {
        i2c_cache_entry_t *entry = s_cache.hash_table[i];
        while (entry != NULL) {
            i2c_cache_entry_t *next = entry->next;
            free(entry);
            entry = next;
        }
        s_cache.hash_table[i] = NULL;
    }
    
    s_cache.current_entries = 0;
    s_cache.initialized = false;
    
    xSemaphoreGive(s_cache.mutex);
    
    // Удаление mutex
    if (s_cache.mutex != NULL) {
        vSemaphoreDelete(s_cache.mutex);
        s_cache.mutex = NULL;
    }
    
    ESP_LOGI(TAG, "I2C cache deinitialized");
    
    return ESP_OK;
}

esp_err_t i2c_cache_get(uint8_t bus_id, uint8_t device_addr,
                       const uint8_t *reg_addr, size_t reg_addr_len,
                       uint8_t *data, size_t data_len, uint32_t ttl_ms) {
    if (!s_cache.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (data == NULL || data_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    // Очистка устаревших записей
    i2c_cache_cleanup_expired();
    
    // Поиск записи
    i2c_cache_entry_t *entry = i2c_cache_find_entry(bus_id, device_addr, reg_addr, reg_addr_len);
    
    if (entry == NULL || !i2c_cache_entry_is_valid(entry)) {
        xSemaphoreGive(s_cache.mutex);
        if (s_cache.metrics_enabled) {
            s_cache.metrics.cache_misses++;
        }
        return ESP_ERR_NOT_FOUND;
    }
    
    // Проверка размера данных
    if (entry->data_len != data_len) {
        xSemaphoreGive(s_cache.mutex);
        if (s_cache.metrics_enabled) {
            s_cache.metrics.cache_misses++;
        }
        return ESP_ERR_INVALID_SIZE;
    }
    
    // Копирование данных
    memcpy(data, entry->data, data_len);
    
    xSemaphoreGive(s_cache.mutex);
    
    if (s_cache.metrics_enabled) {
        s_cache.metrics.cache_hits++;
    }
    
    return ESP_OK;
}

esp_err_t i2c_cache_put(uint8_t bus_id, uint8_t device_addr,
                       const uint8_t *reg_addr, size_t reg_addr_len,
                       const uint8_t *data, size_t data_len, uint32_t ttl_ms) {
    if (!s_cache.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (data == NULL || data_len == 0 || data_len > I2C_CACHE_MAX_DATA_LEN) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (reg_addr_len > I2C_CACHE_MAX_REG_ADDR_LEN) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    // Очистка устаревших записей
    i2c_cache_cleanup_expired();
    
    // Использование default TTL если не указан
    if (ttl_ms == 0) {
        ttl_ms = s_cache.default_ttl_ms;
    }
    
    // Поиск существующей записи
    i2c_cache_entry_t *entry = i2c_cache_find_entry(bus_id, device_addr, reg_addr, reg_addr_len);
    
    if (entry != NULL) {
        // Обновление существующей записи
        memcpy(entry->data, data, data_len);
        entry->data_len = data_len;
        entry->timestamp_us = esp_timer_get_time();
        entry->ttl_ms = ttl_ms;
        
        xSemaphoreGive(s_cache.mutex);
        return ESP_OK;
    }
    
    // Если кэш полон, удаляем самую старую запись
    if (s_cache.current_entries >= s_cache.max_entries) {
        i2c_cache_evict_oldest();
    }
    
    // Создание новой записи
    entry = (i2c_cache_entry_t*)malloc(sizeof(i2c_cache_entry_t));
    if (entry == NULL) {
        xSemaphoreGive(s_cache.mutex);
        ESP_LOGE(TAG, "Failed to allocate cache entry");
        return ESP_ERR_NO_MEM;
    }
    
    entry->bus_id = bus_id;
    entry->device_addr = device_addr;
    entry->reg_addr_len = reg_addr_len;
    if (reg_addr != NULL && reg_addr_len > 0) {
        memcpy(entry->reg_addr, reg_addr, reg_addr_len);
    }
    memcpy(entry->data, data, data_len);
    entry->data_len = data_len;
    entry->timestamp_us = esp_timer_get_time();
    entry->ttl_ms = ttl_ms;
    
    // Добавление в хеш-таблицу
    uint32_t hash = i2c_cache_hash(bus_id, device_addr, reg_addr, reg_addr_len);
    entry->next = s_cache.hash_table[hash];
    s_cache.hash_table[hash] = entry;
    s_cache.current_entries++;
    
    xSemaphoreGive(s_cache.mutex);
    
    return ESP_OK;
}

esp_err_t i2c_cache_invalidate(uint8_t bus_id, uint8_t device_addr,
                               const uint8_t *reg_addr, size_t reg_addr_len) {
    if (!s_cache.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    uint32_t hash = i2c_cache_hash(bus_id, device_addr, reg_addr, reg_addr_len);
    i2c_cache_entry_t **prev = &s_cache.hash_table[hash];
    i2c_cache_entry_t *entry = s_cache.hash_table[hash];
    
    while (entry != NULL) {
        if (i2c_cache_key_match(entry, bus_id, device_addr, reg_addr, reg_addr_len)) {
            *prev = entry->next;
            free(entry);
            s_cache.current_entries--;
            xSemaphoreGive(s_cache.mutex);
            return ESP_OK;
        }
        prev = &entry->next;
        entry = entry->next;
    }
    
    xSemaphoreGive(s_cache.mutex);
    return ESP_ERR_NOT_FOUND;
}

esp_err_t i2c_cache_clear(void) {
    if (!s_cache.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    for (size_t i = 0; i < I2C_CACHE_HASH_TABLE_SIZE; i++) {
        i2c_cache_entry_t *entry = s_cache.hash_table[i];
        while (entry != NULL) {
            i2c_cache_entry_t *next = entry->next;
            free(entry);
            entry = next;
        }
        s_cache.hash_table[i] = NULL;
    }
    
    s_cache.current_entries = 0;
    
    xSemaphoreGive(s_cache.mutex);
    
    return ESP_OK;
}

esp_err_t i2c_cache_get_metrics(i2c_cache_metrics_t *metrics) {
    if (!s_cache.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (metrics == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_cache.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    memcpy(metrics, &s_cache.metrics, sizeof(i2c_cache_metrics_t));
    metrics->current_entries = s_cache.current_entries;
    
    xSemaphoreGive(s_cache.mutex);
    
    return ESP_OK;
}

bool i2c_cache_is_initialized(void) {
    return s_cache.initialized;
}

