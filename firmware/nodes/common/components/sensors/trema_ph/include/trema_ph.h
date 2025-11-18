/**
 * @file trema_ph.h
 * @brief Драйвер Trema pH-сенсора (iarduino) для узлов ESP32
 * 
 * Компонент реализует драйвер для Trema pH-датчика через I²C:
 * - Чтение pH значения
 * - Калибровка (2 этапа)
 * - Проверка стабильности измерений
 * - Обработка ошибок
 * 
 * Адаптирован из mesh_hydro/hydro1.0 для новой архитектуры hydro2.0
 */

#ifndef TREMA_PH_H
#define TREMA_PH_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

// Default I2C address for the pH sensor
#define TREMA_PH_ADDR 0x0A

// Register addresses
#define REG_PH_KNOWN_PH     0x0A  // Known pH value for calibration (2 bytes)
#define REG_PH_CALIBRATION  0x10  // Calibration control register
#define REG_PH_pH           0x1D  // pH measurement result (2 bytes)
#define REG_PH_ERROR        0x1F  // Error flags
#define REG_MODEL           0x04  // Model ID register

// Error flags
#define PH_FLG_STAB_ERR     0x02  // Stability error flag
#define PH_FLG_CALC_ERR     0x01  // Calibration error flag

// Calibration bits
#define PH_BIT_CALC_1       0x01  // Start calibration stage 1
#define PH_BIT_CALC_2       0x02  // Start calibration stage 2
#define PH_CODE_CALC_SAVE   0x24  // Calibration save code

/**
 * @brief Initialize the Trema pH sensor
 * @return true on success, false on failure
 */
bool trema_ph_init(void);

/**
 * @brief Read pH value from the Trema pH sensor
 * @param ph Pointer to store the pH value
 * @return true on success, false on failure
 */
bool trema_ph_read(float *ph);

/**
 * @brief Start calibration of the pH sensor
 * @param stage Calibration stage (1 or 2)
 * @param known_pH Known pH value for calibration (0.0 - 14.0)
 * @return true on success, false on failure
 */
bool trema_ph_calibrate(uint8_t stage, float known_pH);

/**
 * @brief Get calibration status
 * @return 0 if no calibration, 1 for stage 1, 2 for stage 2
 */
uint8_t trema_ph_get_calibration_status(void);

/**
 * @brief Get calibration result
 * @return true if calibration was successful, false otherwise
 */
bool trema_ph_get_calibration_result(void);

/**
 * @brief Get measurement stability
 * @return true if measurement is stable, false otherwise
 */
bool trema_ph_get_stability(void);

/**
 * @brief Wait for stable measurement
 * @param timeout_ms Maximum time to wait for stable measurement in milliseconds
 * @return true if measurement is stable, false if timeout occurred
 */
bool trema_ph_wait_for_stable_reading(uint32_t timeout_ms);

/**
 * @brief Get the last measured pH value
 * @return pH value (0.0 - 14.0)
 */
float trema_ph_get_value(void);

/**
 * @brief Reset the pH sensor
 * @return true on success, false on failure
 */
bool trema_ph_reset(void);

/**
 * @brief Check if we're using stub values (sensor not connected)
 * @return true if using stub values, false if sensor is connected
 */
bool trema_ph_is_using_stub_values(void);

/**
 * @brief Check if pH sensor is initialized
 * @return true if sensor is initialized, false otherwise
 */
bool trema_ph_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // TREMA_PH_H

