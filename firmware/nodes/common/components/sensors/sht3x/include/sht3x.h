/**
 * @file sht3x.h
 * @brief Драйвер SHT3x (температура/влажность)
 */

#ifndef SHT3X_H
#define SHT3X_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#include "i2c_bus.h"

typedef struct {
    float temperature;
    float humidity;
    bool valid;
} sht3x_reading_t;

typedef struct {
    uint8_t i2c_address;
    i2c_bus_id_t i2c_bus;  // I2C bus для датчика (по умолчанию I2C_BUS_0)
} sht3x_config_t;

esp_err_t sht3x_init(const sht3x_config_t *config);
esp_err_t sht3x_deinit(void);
esp_err_t sht3x_read(sht3x_reading_t *reading);

#ifdef __cplusplus
}
#endif

#endif // SHT3X_H

