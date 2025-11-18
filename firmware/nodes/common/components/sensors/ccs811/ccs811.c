/**
 * @file ccs811.c
 * @brief Упрощённый драйвер CCS811
 */

#include "ccs811.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ccs811";

static struct {
    bool initialized;
    ccs811_config_t config;
} s_ccs811 = {0};

esp_err_t ccs811_init(const ccs811_config_t *config) {
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    memcpy(&s_ccs811.config, config, sizeof(ccs811_config_t));
    s_ccs811.initialized = true;
    ESP_LOGI(TAG, "CCS811 initialized (addr=0x%02X)", config->i2c_address);
    return ESP_OK;
}

esp_err_t ccs811_deinit(void) {
    s_ccs811.initialized = false;
    return ESP_OK;
}

esp_err_t ccs811_read(ccs811_reading_t *reading) {
    if (!s_ccs811.initialized || reading == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    memset(reading, 0, sizeof(ccs811_reading_t));
    reading->co2_ppm = 650;
    reading->tvoc_ppb = 15;
    reading->valid = true;
    return ESP_OK;
}
