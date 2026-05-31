/**
 * @file i2c_bus.h
 * @brief Общий драйвер I²C шины с thread-safe доступом
 *
 * Компонент предоставляет единый интерфейс для работы с I²C шиной:
 * - Инициализация с конфигурируемыми параметрами (SDA, SCL, скорость)
 * - Thread-safe доступ через mutex на шину
 * - Раздельные таймауты ожидания mutex и xfer (см. i2c_bus_xfer_opts_t)
 * - Кэш i2c_master_dev_handle_t per (шина, 7-bit адрес); инвалидация при recover/deinit и i2c_bus_forget_device()
 * - Повторы только для чтения (i2c_bus_read_bus_ex); запись — одна попытка (без автоповтора)
 * - Запись без malloc при len <= I2C_BUS_MAX_COMBINED_WRITE
 * - I²C recovery / reset шины
 * - i2c_bus_init_from_config(): только дефолты шины 0 из компонента (пины/скорость не в NodeConfig)
 *
 * Инварианты (порядок блокировок): держите mutex драйвера сенсора, затем вызывайте i2c_bus_*;
 * не вызывайте драйвер с удерживаемым mutex i2c_bus — риск deadlock.
 *
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md
 */

#ifndef I2C_BUS_H
#define I2C_BUS_H

#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief ID I²C шины
 */
typedef enum {
    I2C_BUS_0 = 0,  ///< I²C шина 0
    I2C_BUS_1 = 1,  ///< I²C шина 1
    I2C_BUS_MAX = 2
} i2c_bus_id_t;

/**
 * @brief Конфигурация I²C шины
 */
typedef struct {
    int sda_pin;           ///< GPIO пин для SDA
    int scl_pin;           ///< GPIO пин для SCL
    uint32_t clock_speed;  ///< Скорость I²C в Hz (обычно 100000 или 400000)
    bool pullup_enable;    ///< Внутренние pull-up ESP32 (слабые); при внешних резисторах на линии — false
} i2c_bus_config_t;

/** Максимум (reg_prefix + payload) для записи без heap; иначе ESP_ERR_INVALID_ARG */
#define I2C_BUS_MAX_COMBINED_WRITE 64

/** Максимум попыток чтения при использовании read_extra_retries (включая первую). Запись не ретраится. */
#define I2C_BUS_MAX_READ_ATTEMPTS 3

/** Если lock_timeout_ms в opts == 0: lock = max(xfer + margin, min_lock) */
#define I2C_BUS_LOCK_MARGIN_MS 50U
#define I2C_BUS_MIN_LOCK_TIMEOUT_MS 50U

/**
 * @brief Параметры одной транзакции I²C (таймауты и read-retry).
 *
 * read_extra_retries: только для read_bus_ex. Значение 0 — одна попытка (как legacy read_bus).
 * Между попытками чтения: i2c_master_bus_reset + краткая задержка (кэш dev для этого адреса сбрасывается).
 */
typedef struct {
    uint32_t xfer_timeout_ms;
    uint32_t lock_timeout_ms;   /**< 0: вычислить из xfer_timeout_ms (см. I2C_BUS_LOCK_MARGIN_MS) */
    uint8_t read_extra_retries; /**< 0 .. I2C_BUS_MAX_READ_ATTEMPTS - 1 */
} i2c_bus_xfer_opts_t;

/**
 * @brief Заполнить opts для обычного xfer: одна попытка чтения, lock по умолчанию.
 */
void i2c_bus_xfer_opts_default(uint32_t xfer_timeout_ms, i2c_bus_xfer_opts_t *out);

/**
 * @brief Инициализация I²C шины (шина 0 по умолчанию, для обратной совместимости)
 *
 * @param config Конфигурация I²C шины
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_init(const i2c_bus_config_t *config);

/**
 * @brief Инициализация конкретной I²C шины
 *
 * @param bus_id ID шины (I2C_BUS_0 или I2C_BUS_1)
 * @param config Конфигурация I²C шины
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_init_bus(i2c_bus_id_t bus_id, const i2c_bus_config_t *config);

/**
 * @brief Деинициализация I²C шины
 *
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t i2c_bus_deinit(void);

/**
 * @brief Проверка инициализации I²C шины (шина 0 по умолчанию)
 *
 * @return true если шина инициализирована
 */
bool i2c_bus_is_initialized(void);

/**
 * @brief Проверка инициализации конкретной I²C шины
 *
 * @param bus_id ID шины
 * @return true если шина инициализирована
 */
bool i2c_bus_is_initialized_bus(i2c_bus_id_t bus_id);

/**
 * @brief Чтение данных с I²C устройства (шина 0 по умолчанию, для обратной совместимости)
 *
 * @param timeout_ms Таймаут xfer (мс); ожидание mutex вычисляется отдельно (см. i2c_bus_xfer_opts_t).
 */
esp_err_t i2c_bus_read(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                       uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Чтение данных с I²C устройства на конкретной шине (одна попытка, без автоповтора).
 */
esp_err_t i2c_bus_read_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                           uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Чтение с опциями (раздельные таймауты mutex/xfer; повторы только для read).
 *
 * @param opts обязателен (не NULL)
 */
esp_err_t i2c_bus_read_bus_ex(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                              uint8_t *data, size_t data_len, const i2c_bus_xfer_opts_t *opts);

/**
 * @brief Запись данных в I²C устройство (шина 0 по умолчанию, для обратной совместимости)
 */
esp_err_t i2c_bus_write(uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                        const uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Запись данных на конкретную шину (одна попытка; combined len <= I2C_BUS_MAX_COMBINED_WRITE).
 */
esp_err_t i2c_bus_write_bus(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                            const uint8_t *data, size_t data_len, uint32_t timeout_ms);

/**
 * @brief Запись с опциями (read_extra_retries в opts игнорируется; без повторов записи).
 *
 * @param opts обязателен (не NULL)
 */
esp_err_t i2c_bus_write_bus_ex(i2c_bus_id_t bus_id, uint8_t device_addr, const uint8_t *reg_addr, size_t reg_addr_len,
                               const uint8_t *data, size_t data_len, const i2c_bus_xfer_opts_t *opts);

/**
 * @brief Удалить кэшированный dev-handle для адреса (после смены 7-bit адреса Trema и т.п.).
 */
/**
 * @brief Удалить кэшированный dev-handle для 7-bit адреса.
 * @return ESP_OK если запись была и удалена; ESP_ERR_NOT_FOUND если адреса не было в кэше (идемпотентно для вызывающего);
 *         ESP_ERR_INVALID_STATE / ESP_ERR_TIMEOUT — шина не готова или mutex.
 */
esp_err_t i2c_bus_forget_device(i2c_bus_id_t bus_id, uint8_t device_addr_7bit);

/**
 * @brief Чтение одного байта из регистра
 */
esp_err_t i2c_bus_read_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t *data, uint32_t timeout_ms);

/**
 * @brief Запись одного байта в регистр
 */
esp_err_t i2c_bus_write_byte(uint8_t device_addr, uint8_t reg_addr, uint8_t data, uint32_t timeout_ms);

/**
 * @brief Сканирование I²C шины для поиска устройств
 */
esp_err_t i2c_bus_scan(uint8_t *found_addresses, size_t max_addresses, size_t *found_count);

/**
 * @brief Сканирование указанной I²C шины (адреса 0x08–0x77, probe через приём 1 байта)
 */
esp_err_t i2c_bus_scan_bus(i2c_bus_id_t bus_id, uint8_t *found_addresses, size_t max_addresses,
                           size_t *found_count);

/**
 * @brief Восстановление I²C шины при ошибках (полный deinit + init; кэш dev сбрасывается).
 */
esp_err_t i2c_bus_recover(void);

/**
 * @brief Аппаратный сброс FSM мастера I²C (без удаления шины и mutex).
 */
esp_err_t i2c_bus_reset_bus(i2c_bus_id_t bus_id);

/**
 * @brief Инициализация шины 0 дефолтами компонента (совместимость API; NodeConfig не читается).
 *
 * Пины, скорость и вторая шина задаются в коде ноды (i2c_bus_init / i2c_bus_init_bus).
 */
esp_err_t i2c_bus_init_from_config(void);

#ifdef __cplusplus
}
#endif

#endif // I2C_BUS_H
