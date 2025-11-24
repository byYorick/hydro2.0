/**
 * @file ccs811.h
 * @brief Драйвер CCS811 (CO₂/TVOC сенсор) для узлов ESP32
 * 
 * Компонент реализует драйвер для CCS811 датчика через I²C:
 * - Чтение CO₂ (ppm) и TVOC (ppb) значений
 * - Инициализация и проверка сенсора
 * - Обработка ошибок
 * - Интеграция с i2c_cache и diagnostics
 * 
 * Согласно спецификации CCS811 от AMS
 */

#ifndef CCS811_H
#define CCS811_H

#include "esp_err.h"
#include "i2c_bus.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Default I2C address for CCS811
#define CCS811_I2C_ADDR_DEFAULT 0x5A  // Адрес по умолчанию (может быть 0x5B)

// CCS811 Register addresses
#define CCS811_REG_STATUS          0x00  // Status register
#define CCS811_REG_MEAS_MODE       0x01  // Measurement mode register
#define CCS811_REG_ALG_RESULT_DATA 0x02  // Algorithm result data (4 bytes)
#define CCS811_REG_RAW_DATA        0x03  // Raw data register
#define CCS811_REG_ENV_DATA        0x05  // Environment data register
#define CCS811_REG_NTC             0x06  // NTC register
#define CCS811_REG_THRESHOLDS      0x10  // Thresholds register
#define CCS811_REG_BASELINE        0x11  // Baseline register
#define CCS811_REG_HW_ID           0x20  // Hardware ID (should be 0x81)
#define CCS811_REG_HW_VERSION      0x21  // Hardware version
#define CCS811_REG_FW_BOOT_VERSION 0x23  // Firmware boot version
#define CCS811_REG_FW_APP_VERSION  0x24  // Firmware application version
#define CCS811_REG_ERROR_ID        0xE0  // Error ID register
#define CCS811_REG_APP_START       0xF4  // Application start command
#define CCS811_REG_SW_RESET        0xFF  // Software reset command

// Status register bits
#define CCS811_STATUS_ERROR        (1 << 0)  // Error bit
#define CCS811_STATUS_DATA_READY   (1 << 3)  // Data ready bit
#define CCS811_STATUS_APP_VALID    (1 << 4)  // Application valid bit
#define CCS811_STATUS_FW_MODE      (1 << 7)  // Firmware mode bit

// Measurement mode register values
#define CCS811_MEAS_MODE_IDLE       0x00  // Idle mode
#define CCS811_MEAS_MODE_1SEC       0x10  // 1 second interval
#define CCS811_MEAS_MODE_10SEC      0x20  // 10 seconds interval
#define CCS811_MEAS_MODE_60SEC      0x30  // 60 seconds interval
#define CCS811_MEAS_MODE_250MS      0x40  // 250ms interval
#define CCS811_MEAS_MODE_INT_DATARDY (1 << 3)  // Interrupt on data ready
#define CCS811_MEAS_MODE_INT_THRESH  (1 << 4)  // Interrupt on threshold

// Expected hardware ID
#define CCS811_HW_ID_VALUE 0x81

// Error codes
#define CCS811_ERROR_WRITE_REG_INVALID  0x01
#define CCS811_ERROR_READ_REG_INVALID   0x02
#define CCS811_ERROR_MEASMODE_INVALID   0x03
#define CCS811_ERROR_MAX_RESISTANCE     0x04
#define CCS811_ERROR_HEATER_FAULT       0x05
#define CCS811_ERROR_HEATER_SUPPLY      0x06

/**
 * @brief Результат чтения CCS811
 */
typedef struct {
    uint16_t co2_ppm;      ///< Концентрация CO₂ в ppm (400-8192)
    uint16_t tvoc_ppb;     ///< Концентрация TVOC в ppb (0-1187)
    bool valid;            ///< Валидность данных
    uint8_t error_id;      ///< Код ошибки (если есть)
} ccs811_reading_t;

/**
 * @brief Конфигурация CCS811
 */
typedef struct {
    uint8_t i2c_address;           ///< I2C адрес сенсора (0x5A или 0x5B)
    i2c_bus_id_t i2c_bus;          ///< ID I2C шины (I2C_BUS_0 или I2C_BUS_1)
    uint8_t measurement_mode;       ///< Режим измерений (CCS811_MEAS_MODE_*)
    uint32_t measurement_interval_ms; ///< Интервал измерений в миллисекундах
} ccs811_config_t;

/**
 * @brief Инициализация CCS811 сенсора
 * 
 * @param config Конфигурация сенсора (может быть NULL для значений по умолчанию)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ccs811_init(const ccs811_config_t *config);

/**
 * @brief Деинициализация CCS811 сенсора
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ccs811_deinit(void);

/**
 * @brief Чтение данных с CCS811 сенсора
 * 
 * @param reading Указатель на структуру для сохранения результатов
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ccs811_read(ccs811_reading_t *reading);

/**
 * @brief Проверка, инициализирован ли сенсор
 * 
 * @return true если сенсор инициализирован
 */
bool ccs811_is_initialized(void);

/**
 * @brief Получить статус сенсора
 * 
 * @param status Указатель для сохранения статуса
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t ccs811_get_status(uint8_t *status);

/**
 * @brief Проверить наличие данных для чтения
 * 
 * @return true если данные готовы
 */
bool ccs811_is_data_ready(void);

#ifdef __cplusplus
}
#endif

#endif // CCS811_H
