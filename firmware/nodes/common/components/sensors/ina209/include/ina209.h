/**
 * @file ina209.h
 * @brief Драйвер INA209 (датчик тока)
 */

#ifndef INA209_H
#define INA209_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float bus_current_ma;
    float bus_voltage_v;
    float power_mw;
    bool valid;
} ina209_reading_t;

typedef struct {
    uint8_t i2c_address;
    float shunt_resistance_ohm;
    float max_current_ma;
    float min_bus_current_on;
    float max_bus_current_on;
} ina209_config_t;

esp_err_t ina209_init(const ina209_config_t *config);
esp_err_t ina209_deinit(void);
esp_err_t ina209_read(ina209_reading_t *reading);
bool ina209_check_current_range(float current_ma);

#ifdef __cplusplus
}
#endif

#endif // INA209_H

