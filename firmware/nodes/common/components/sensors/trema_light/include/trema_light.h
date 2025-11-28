/**
 * @file trema_light.h
 * @brief Драйвер Trema датчика освещенности (iarduino) для узлов ESP32
 * 
 * Компонент реализует драйвер для Trema датчика освещенности через I²C:
 * - Чтение значения освещенности (люкс)
 * - Обработка ошибок
 * 
 * Адаптирован из trema_ph для новой архитектуры hydro2.0
 */

#ifndef TREMA_LIGHT_H
#define TREMA_LIGHT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>
#include "i2c_bus.h"

// Default I2C address for the light sensor
#define TREMA_LIGHT_ADDR 0x21

// Register addresses
#define REG_LIGHT_LUX      0x1D  // Освещенность (2 bytes, люкс)
#define REG_LIGHT_ERROR    0x1F  // Error flags
#define REG_MODEL          0x04  // Model ID register

// Expected model ID for Trema light sensor
// Примечание: некоторые датчики возвращают 0x06 вместо 0x1B
#define TREMA_LIGHT_MODEL_ID 0x06

/**
 * @brief Initialize the Trema light sensor
 * @param i2c_bus I2C bus ID (I2C_BUS_0 or I2C_BUS_1)
 * @return true on success, false on failure
 */
bool trema_light_init(i2c_bus_id_t i2c_bus);

/**
 * @brief Read light value from the Trema light sensor
 * @param lux Pointer to store the light value (lux)
 * @return true on success, false on failure
 */
bool trema_light_read(float *lux);

/**
 * @brief Check if we're using stub values (sensor not connected)
 * @return true if using stub values, false if sensor is connected
 */
bool trema_light_is_using_stub_values(void);

/**
 * @brief Check if light sensor is initialized
 * @return true if sensor is initialized, false otherwise
 */
bool trema_light_is_initialized(void);

#ifdef __cplusplus
}
#endif

#endif // TREMA_LIGHT_H

