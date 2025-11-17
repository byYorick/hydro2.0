/**
 * @file trema_ec.h
 * @brief Драйвер Trema EC-сенсора (iarduino) для узлов ESP32
 * 
 * Компонент реализует драйвер для Trema EC-датчика через I²C:
 * - Чтение EC значения (mS/cm)
 * - Калибровка (2 этапа)
 * - Температурная компенсация
 * - Чтение TDS значения (ppm)
 * - Обработка ошибок
 * 
 * Адаптирован из mesh_hydro/hydro1.0 для новой архитектуры hydro2.0
 */

#ifndef TREMA_EC_H
#define TREMA_EC_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

// Default I2C address for the EC sensor
#define TREMA_EC_ADDR 0x08

// Register addresses
#define REG_TDS_KNOWN_TDS   0x0A  // Known TDS value for calibration (2 bytes)
#define REG_TDS_CALIBRATION 0x10  // Calibration control register
#define REG_TDS_S           0x20  // Measured conductivity (2 bytes)
#define REG_TDS_EC          0x22  // Converted conductivity (2 bytes)
#define REG_TDS_TDS         0x24  // TDS value (2 bytes)
#define REG_TDS_t           0x19  // Temperature register
#define REG_MODEL           0x04  // Model ID register

// Calibration bits
#define TDS_BIT_CALC_1      0x01  // Start calibration stage 1
#define TDS_BIT_CALC_2      0x02  // Start calibration stage 2
#define TDS_CODE_CALC_SAVE  0x24  // Calibration save code

/**
 * @brief Initialize the Trema EC sensor
 * @return true on success, false on failure
 */
bool trema_ec_init(void);

/**
 * @brief Read EC value from the Trema EC sensor
 * @param ec Pointer to store the EC value (mS/cm)
 * @return true on success, false on failure
 */
bool trema_ec_read(float *ec);

/**
 * @brief Start calibration of the EC sensor
 * @param stage Calibration stage (1 or 2)
 * @param known_tds Known TDS value for calibration (0 - 10000 ppm)
 * @return true on success, false on failure
 */
bool trema_ec_calibrate(uint8_t stage, uint16_t known_tds);

/**
 * @brief Get calibration status
 * @return 0 if no calibration, 1 for stage 1, 2 for stage 2
 */
uint8_t trema_ec_get_calibration_status(void);

/**
 * @brief Set temperature for temperature compensation
 * @param temperature Temperature in Celsius (0 - 63.75 °C)
 * @return true on success, false on failure
 */
bool trema_ec_set_temperature(float temperature);

/**
 * @brief Get the last measured TDS value
 * @return TDS value (ppm)
 */
uint16_t trema_ec_get_tds(void);

/**
 * @brief Get the last measured conductivity
 * @return Conductivity value (mS/cm)
 */
float trema_ec_get_conductivity(void);

/**
 * @brief Check if we're using stub values (sensor not connected)
 * @return true if using stub values, false if sensor is connected
 */
bool trema_ec_is_using_stub_values(void);

#ifdef __cplusplus
}
#endif

#endif // TREMA_EC_H

