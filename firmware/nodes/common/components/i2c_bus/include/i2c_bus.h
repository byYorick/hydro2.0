/**
 * @file i2c_bus.h
 * @brief Общий драйвер I²C шины с thread-safe доступом
 * 
 * Компонент предоставляет единый интерфейс для работы с I²C шиной:
 * - Инициализация с конфигурируемыми параметрами (SDA, SCL, скорость)
 * - Thread-safe доступ через mutex
 * - Функции чтения/записи с обработкой ошибок и retry логикой
 * - I²C recovery при ошибках (reset bus)
 * - Интеграция с NodeConfig
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md
 */

#ifndef I2C_BUS_H
#define I2C_BUS_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Конфигурация I²C шины
 */
typedef struct {
    int sda_pin;           ///< GPIO пин для SDA
    int scl_pin;           ///< GPIO пин для SCL
    uint32_t clock_speed;  ///< Скорость I²C в Hz (обычно 100000 или 400000)
    bool pullup_enable;    ///< Включить внутренние pull-up резисторы
} i2c_bus_config_t;

/**
 * @brief Инициализация I²C шины
 * 
 * @param config Конфигурация I²C шины
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_init(const i2c_bus_config_t *config);

/**
 * @brief Деинициализация I²C шины
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_deinit(void);

/**
 * @brief Проверка инициализации I²C шины
 * 
 * @return true если шина инициализирована
 */
bool i2c_bus_is_initialized(void);

/**
 * @brief Чтение данных с I²C устройства
 * 
 * @param device_addr Адрес I²C устройства (7-bit)
 * @param reg_addr Адрес регистра (может быть NULL для устройств без регистров)
 * @param reg_addr_len Длина адреса регистра в байтах (0 если reg_addr == NULL)
 * @param data Буфер для чтения данных
 * @param data_len Количество байт для чтения
 * @param timeout_ms Таймаут операции в миллисекундах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_read(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                      uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Запись данных в I²C устройство
 * 
 * @param device_addr Адрес I²C устройства (7-bit)
 * @param reg_addr Адрес регистра (может быть NULL для устройств без регистров)
 * @param reg_addr_len Длина адреса регистра в байтах (0 если reg_addr == NULL)
 * @param data Буфер с данными для записи
 * @param data_len Количество байт для записи
 * @param timeout_ms Таймаут операции в миллисекундах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_write(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                       const uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Чтение одного байта из регистра
 * 
 * @param device_addr Адрес I²C устройства (7-bit)
 * @param reg_addr Адрес регистра
 * @param data Указатель для сохранения прочитанного байта
 * @param timeout_ms Таймаут операции в миллисекундах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_read_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t *data, uint32_t timeout_ms);

/**
 * @brief Запись одного байта в регистр
 * 
 * @param device_addr Адрес I²C устройства (7-bit)
 * @param reg_addr Адрес регистра
 * @param data Байт для записи
 * @param timeout_ms Таймаут операции в миллисекундах
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_write_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t data, uint32_t timeout_ms);

/**
 * @brief Сканирование I²C шины для поиска устройств
 * 
 * @param found_addresses Массив для сохранения найденных адресов (максимум 128)
 * @param max_addresses Максимальное количество адресов в массиве
 * @param found_count Указатель для сохранения количества найденных устройств
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_scan(uint8_t *found_addresses, size_t max_addresses, size_t *found_count);

/**
 * @brief Восстановление I²C шины при ошибках
 * 
 * Выполняет reset шины и повторную инициализацию
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_recover(void);

/**
 * @brief Инициализация I²C шины из NodeConfig
 * 
 * Читает параметры из hardware.i2c секции NodeConfig
 * 
 * @return esp_err_t ESP_OK при успехе, ESP_ERR_NOT_FOUND если конфиг не найден
 */
esp_err_t i2c_bus_init_from_config(void);

#ifdef __cplusplus
}
#endif

#endif // I2C_BUS_H

