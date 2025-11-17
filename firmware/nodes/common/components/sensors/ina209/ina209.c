/**
 * @file ina209.c
 * @brief Реализация драйвера INA209
 */

#include "ina209.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "ina209";

static struct {
    bool initialized;
    ina209_config_t config;
} s_ina209 = {0};

esp_err_t ina209_init(const ina209_config_t *config) {
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memcpy(&s_ina209.config, config, sizeof(ina209_config_t));
    s_ina209.initialized = true;
    ESP_LOGI(TAG, "INA209 initialized");
    return ESP_OK;
}

esp_err_t ina209_deinit(void) {
    s_ina209.initialized = false;
    return ESP_OK;
}

esp_err_t ina209_read(ina209_reading_t *reading) {
    if (!s_ina209.initialized || reading == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    memset(reading, 0, sizeof(ina209_reading_t));
    // Упрощенная реализация - чтение регистров INA209
    uint8_t current_reg[2];
    esp_err_t err = i2c_bus_read(s_ina209.config.i2c_address, (uint8_t[]){0x01}, 1, 
                                 current_reg, 2, 1000);
    if (err != ESP_OK) {
        return err;
    }
    int16_t raw_current = (current_reg[0] << 8) | current_reg[1];
    reading->bus_current_ma = (float)raw_current * 0.1f;  // Зависит от shunt resistance
    reading->valid = true;
    return ESP_OK;
}

bool ina209_check_current_range(float current_ma) {
    if (!s_ina209.initialized) {
        return false;
    }
    return (current_ma >= s_ina209.config.min_bus_current_on && 
            current_ma <= s_ina209.config.max_bus_current_on);
}

