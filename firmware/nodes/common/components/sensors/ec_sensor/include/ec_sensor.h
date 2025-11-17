/**
 * @file ec_sensor.h
 * @brief Драйвер EC-сенсора для узлов ESP32
 */

#ifndef EC_SENSOR_H
#define EC_SENSOR_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float ec_value;
    float raw_value;
    float temperature;
    bool valid;
    bool in_range;
} ec_sensor_reading_t;

typedef struct {
    int adc_channel;
    uint8_t i2c_address;
    float min_value;
    float max_value;
    float temp_coefficient;
} ec_sensor_config_t;

esp_err_t ec_sensor_init(const ec_sensor_config_t *config);
esp_err_t ec_sensor_deinit(void);
esp_err_t ec_sensor_read(ec_sensor_reading_t *reading, float temperature);
esp_err_t ec_sensor_init_from_config(const char *channel_id);

#ifdef __cplusplus
}
#endif

#endif // EC_SENSOR_H

