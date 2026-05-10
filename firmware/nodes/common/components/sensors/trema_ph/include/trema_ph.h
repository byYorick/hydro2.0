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

// 7-bit адрес по умолчанию — 0x09 (datasheet/wiki iarduino FLASH-I2C pH); 0x0A — встречается у части плат
#define TREMA_PH_ADDR 0x09

/**
 * @brief Задать 7-bit I²C адрес модуля до/между инициализациями (если отличается от TREMA_PH_ADDR).
 */
void trema_ph_set_i2c_address(uint8_t addr_7bit);

/**
 * @brief Текущий 7-bit I²C адрес драйвера.
 */
uint8_t trema_ph_get_i2c_address(void);

/**
 * @brief Версия прошивки модуля (байт из заголовка REG_MODEL+1), 0 если ещё не было успешного init.
 *
 * См. wiki iarduino: нормализация/getStability — с FW ≥ 6.
 */
uint8_t trema_ph_get_firmware_version(void);

/** Идентификатор модели и линейки чипа — как в iarduino_I2C_pH.h v1.2.3 (tre.ru / GitHub) */
#define TREMA_PH_MODEL_ID       0x1A
#define TREMA_PH_CHIP_ID_FLASH  0x3C
#define TREMA_PH_CHIP_ID_METRO  0xC3

// Register addresses
#define REG_PH_KNOWN_PH     0x0A  // Known pH value for calibration (2 bytes)
#define REG_PH_CALIBRATION  0x10  // Calibration control register
#define REG_PH_pH           0x1D  // pH measurement result (2 bytes)
#define REG_PH_ERROR        0x1F  // Error flags
#define REG_MODEL           0x04  // Model ID register

// Error flags (REG_PH_ERROR)
#define PH_FLG_STAB_ERR     0x02  // Stability error flag
#define PH_FLG_CALC_ERR     0x01  // Calibration error flag

// Calibration control (REG_PH_CALIBRATION): status bits + command bits
#define PH_FLG_STATUS_1     0x40  // Stage 1 calibration in progress / done (iarduino)
#define PH_FLG_STATUS_2     0x80  // Stage 2 calibration in progress / done (iarduino)
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
 * @brief Стабильность для последнего успешного trema_ph_read (тот же кадр, что REG_PH_pH + REG_PH_ERROR).
 *
 * Для телеметрии предпочтительнее, чем отдельный trema_ph_get_stability(), чтобы не было гонки по I²C.
 * Если успешного чтения ещё не было — возвращает false.
 */
bool trema_ph_get_last_read_stability(void);

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

/**
 * @brief Log I²C bus 1 connectivity status for the pH sensor
 * @return true if sensor responded with expected model ID, false otherwise
 */
bool trema_ph_log_connection_status(void);

/**
 * @brief Быстрая проверка наличия модуля по правилам iarduino (REG_MODEL..CHIP_ID, 4 байта).
 * Не требует успешного trema_ph_init().
 */
bool trema_ph_probe_presence(void);

/**
 * @brief Подробные шаги чтения/инициализации в лог.
 *
 * @param verbose true — шаги через ESP_LOGI (каждый опрос, шумно).
 *                false — шаги только ESP_LOGD (нужен esp_log_level_set("trema_ph", ESP_LOG_DEBUG)).
 */
void trema_ph_set_read_trace_verbose(bool verbose);

#ifdef __cplusplus
}
#endif

#endif // TREMA_PH_H

