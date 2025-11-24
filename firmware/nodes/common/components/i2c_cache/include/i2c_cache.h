/**
 * @file i2c_cache.h
 * @brief Кэш для результатов I2C операций
 * 
 * Компонент предоставляет:
 * - Кэширование результатов чтения I2C устройств
 * - TTL (Time To Live) для записей кэша
 * - Автоматическая инвалидация устаревших записей
 * - Метрики использования кэша
 * - Thread-safe доступ
 */

#ifndef I2C_CACHE_H
#define I2C_CACHE_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация кэша I2C
 */
typedef struct {
    size_t max_entries;          ///< Максимальное количество записей в кэше (по умолчанию 32)
    uint32_t default_ttl_ms;     ///< TTL по умолчанию в миллисекундах (по умолчанию 1000)
    bool enable_metrics;         ///< Включить сбор метрик (по умолчанию true)
} i2c_cache_config_t;

/**
 * @brief Метрики использования кэша
 */
typedef struct {
    uint32_t cache_hits;         ///< Попадания в кэш
    uint32_t cache_misses;       ///< Промахи кэша
    uint32_t cache_evictions;    ///< Вытеснения из кэша (когда кэш полон)
    uint32_t cache_invalidations; ///< Инвалидации (устаревшие записи)
    size_t current_entries;      ///< Текущее количество записей в кэше
} i2c_cache_metrics_t;

/**
 * @brief Инициализация кэша I2C
 * 
 * @param config Конфигурация кэша (может быть NULL для значений по умолчанию)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_init(const i2c_cache_config_t *config);

/**
 * @brief Деинициализация кэша I2C
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_deinit(void);

/**
 * @brief Получить данные из кэша
 * 
 * @param bus_id ID I2C шины
 * @param device_addr Адрес I2C устройства (7-bit)
 * @param reg_addr Адрес регистра (может быть NULL)
 * @param reg_addr_len Длина адреса регистра в байтах (0 если reg_addr == NULL)
 * @param data Буфер для данных (выделяется вызывающим)
 * @param data_len Размер буфера / количество байт для чтения
 * @param ttl_ms TTL в миллисекундах (0 для использования default_ttl_ms)
 * @return esp_err_t ESP_OK если данные найдены в кэше и не устарели, ESP_ERR_NOT_FOUND если нет в кэше
 */
esp_err_t i2c_cache_get(uint8_t bus_id, uint8_t device_addr, 
                        const uint8_t *reg_addr, size_t reg_addr_len,
                        uint8_t *data, size_t data_len, uint32_t ttl_ms);

/**
 * @brief Сохранить данные в кэш
 * 
 * @param bus_id ID I2C шины
 * @param device_addr Адрес I2C устройства (7-bit)
 * @param reg_addr Адрес регистра (может быть NULL)
 * @param reg_addr_len Длина адреса регистра в байтах (0 если reg_addr == NULL)
 * @param data Данные для сохранения
 * @param data_len Количество байт данных
 * @param ttl_ms TTL в миллисекундах (0 для использования default_ttl_ms)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_put(uint8_t bus_id, uint8_t device_addr,
                       const uint8_t *reg_addr, size_t reg_addr_len,
                       const uint8_t *data, size_t data_len, uint32_t ttl_ms);

/**
 * @brief Инвалидировать запись в кэше
 * 
 * @param bus_id ID I2C шины
 * @param device_addr Адрес I2C устройства (7-bit)
 * @param reg_addr Адрес регистра (может быть NULL)
 * @param reg_addr_len Длина адреса регистра в байтах (0 если reg_addr == NULL)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_invalidate(uint8_t bus_id, uint8_t device_addr,
                               const uint8_t *reg_addr, size_t reg_addr_len);

/**
 * @brief Очистить весь кэш
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_clear(void);

/**
 * @brief Получить метрики использования кэша
 * 
 * @param metrics Указатель на структуру для метрик
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_cache_get_metrics(i2c_cache_metrics_t *metrics);

/**
 * @brief Проверить, инициализирован ли кэш
 * 
 * @return true если кэш инициализирован
 */
bool i2c_cache_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // I2C_CACHE_H

