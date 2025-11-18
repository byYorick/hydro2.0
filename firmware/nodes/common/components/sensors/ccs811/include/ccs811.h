/**
 * @file ccs811.h
 * @brief Простой драйвер CCS811 (CO₂/TVOC)
 */

#ifndef CCS811_H
#define CCS811_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t co2_ppm;
    uint16_t tvoc_ppb;
    bool valid;
} ccs811_reading_t;

typedef struct {
    uint8_t i2c_address;
    uint32_t measurement_interval_ms;
} ccs811_config_t;

esp_err_t ccs811_init(const ccs811_config_t *config);
esp_err_t ccs811_deinit(void);
esp_err_t ccs811_read(ccs811_reading_t *reading);

#ifdef __cplusplus
}
#endif

#endif // CCS811_H
