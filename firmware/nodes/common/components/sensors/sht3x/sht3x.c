/**
 * @file sht3x.c
 * @brief Реализация драйвера SHT3x
 */

#include "sht3x.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <stdbool.h>
#include <stdint.h>
#include <math.h>

static const char *TAG = "sht3x";

static struct {
    bool initialized;
    sht3x_config_t config;
} s_sht3x = {0};

esp_err_t sht3x_init(const sht3x_config_t *config) {
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memcpy(&s_sht3x.config, config, sizeof(sht3x_config_t));
    
    // Проверяем, что указанный I2C bus инициализирован
    i2c_bus_id_t bus_id = config->i2c_bus;
    if (!i2c_bus_is_initialized_bus(bus_id)) {
        ESP_LOGE(TAG, "I2C bus %d not initialized for SHT3x", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    s_sht3x.initialized = true;
    ESP_LOGI(TAG, "SHT3x initialized on I2C bus %d, address 0x%02X", bus_id, config->i2c_address);
    return ESP_OK;
}

esp_err_t sht3x_deinit(void) {
    s_sht3x.initialized = false;
    return ESP_OK;
}

// SHT3x команды
#define SHT3X_CMD_SINGLE_SHOT_HIGH_REP 0x2400  // Single shot, high repeatability (15ms delay)
#define SHT3X_CMD_SINGLE_SHOT_MED_REP  0x240B  // Single shot, medium repeatability (6ms delay)
#define SHT3X_CMD_SINGLE_SHOT_LOW_REP  0x2416  // Single shot, low repeatability (4ms delay)

// Простая проверка CRC (полином 0x31)
static uint8_t sht3x_crc8(const uint8_t *data, size_t len) {
    uint8_t crc = 0xFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t bit = 8; bit > 0; bit--) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0x31;
            } else {
                crc = (crc << 1);
            }
        }
    }
    return crc;
}

esp_err_t sht3x_read(sht3x_reading_t *reading) {
    if (!s_sht3x.initialized || reading == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    
    memset(reading, 0, sizeof(sht3x_reading_t));
    reading->valid = false;
    
    i2c_bus_id_t bus_id = s_sht3x.config.i2c_bus;
    if (!i2c_bus_is_initialized_bus(bus_id)) {
        ESP_LOGE(TAG, "I2C bus %d not initialized", bus_id);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Отправляем команду измерения (high repeatability)
    uint8_t cmd[2] = {
        (SHT3X_CMD_SINGLE_SHOT_HIGH_REP >> 8) & 0xFF,
        SHT3X_CMD_SINGLE_SHOT_HIGH_REP & 0xFF
    };
    
    esp_err_t err = i2c_bus_write_bus(bus_id, s_sht3x.config.i2c_address, NULL, 0, cmd, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send measurement command: %s", esp_err_to_name(err));
        return err;
    }
    
    // Ждем завершения измерения (15ms для high repeatability)
    vTaskDelay(pdMS_TO_TICKS(20));  // Небольшой запас
    
    // Читаем 6 байт: 2 байта temp, 1 CRC, 2 байта humidity, 1 CRC
    uint8_t data[6];
    err = i2c_bus_read_bus(bus_id, s_sht3x.config.i2c_address, NULL, 0, data, 6, 1000);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read measurement data: %s", esp_err_to_name(err));
        return err;
    }
    
    // Проверяем CRC для температуры
    uint8_t temp_crc = sht3x_crc8(data, 2);
    if (temp_crc != data[2]) {
        ESP_LOGE(TAG, "Temperature CRC mismatch: calculated=0x%02X, received=0x%02X", temp_crc, data[2]);
        return ESP_ERR_INVALID_RESPONSE;
    }
    
    // Проверяем CRC для влажности
    uint8_t hum_crc = sht3x_crc8(&data[3], 2);
    if (hum_crc != data[5]) {
        ESP_LOGE(TAG, "Humidity CRC mismatch: calculated=0x%02X, received=0x%02X", hum_crc, data[5]);
        return ESP_ERR_INVALID_RESPONSE;
    }
    
    // Преобразуем данные
    uint16_t temp_raw = (data[0] << 8) | data[1];
    uint16_t hum_raw = (data[3] << 8) | data[4];
    
    // Формулы из datasheet SHT3x
    // Температура: T = -45 + 175 * (ST / 65535)
    reading->temperature = -45.0f + 175.0f * ((float)temp_raw / 65535.0f);
    
    // Влажность: RH = 100 * (SRH / 65535)
    reading->humidity = 100.0f * ((float)hum_raw / 65535.0f);
    
    // Проверяем валидность значений
    if (reading->temperature >= -40.0f && reading->temperature <= 125.0f &&
        reading->humidity >= 0.0f && reading->humidity <= 100.0f) {
        reading->valid = true;
        ESP_LOGD(TAG, "SHT3x read: T=%.1f°C, H=%.1f%%", reading->temperature, reading->humidity);
    } else {
        ESP_LOGW(TAG, "SHT3x values out of range: T=%.1f°C, H=%.1f%%", 
                reading->temperature, reading->humidity);
        reading->valid = false;
        return ESP_ERR_INVALID_RESPONSE;
    }
    
    return ESP_OK;
}

