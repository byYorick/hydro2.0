/**
 * @file trema_light.c
 * @brief Реализация драйвера Trema датчика освещенности
 * 
 * Адаптирован из trema_ph для новой архитектуры hydro2.0
 * Использует новый API i2c_bus компонента
 */

#include "trema_light.h"
#include "i2c_bus.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>

static const char *TAG = "trema_light";
static const uint8_t kExpectedModelId = TREMA_LIGHT_MODEL_ID;

// Stub values for when sensor is not connected
static bool use_stub_values = false;
static float stub_lux = 500.0f;  // 500 lux (типичное офисное освещение)

// Buffer for I2C communication
static uint8_t data[4];

// Sensor initialization flag
static bool sensor_initialized = false;
static i2c_bus_id_t s_i2c_bus = I2C_BUS_0;

bool trema_light_init(i2c_bus_id_t i2c_bus)
{
    ESP_LOGI(TAG, "Initializing Trema light sensor on I2C bus %d, address 0x%02X", i2c_bus, TREMA_LIGHT_ADDR);
    
    if (!i2c_bus_is_initialized_bus(i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", i2c_bus);
        return false;
    }
    
    ESP_LOGD(TAG, "I2C bus %d is initialized, attempting to read model ID from address 0x%02X", i2c_bus, TREMA_LIGHT_ADDR);
    
    s_i2c_bus = i2c_bus;
    
    // Try to communicate with the sensor
    // Read the model register to verify sensor presence
    uint8_t reg_model = REG_MODEL;
    ESP_LOGD(TAG, "Reading model register 0x%02X from address 0x%02X", reg_model, TREMA_LIGHT_ADDR);
    esp_err_t err = i2c_bus_read_bus(i2c_bus, TREMA_LIGHT_ADDR, &reg_model, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read from light sensor at address 0x%02X: %s (error code: %d)", 
                 TREMA_LIGHT_ADDR, esp_err_to_name(err), err);
        ESP_LOGD(TAG, "I2C read error details: bus=%d, addr=0x%02X, reg=0x%02X", i2c_bus, TREMA_LIGHT_ADDR, reg_model);
        return false;
    }
    
    ESP_LOGD(TAG, "Received data from sensor: 0x%02X", data[0]);
    
    // Check if we got a valid response
    // Поддерживаем оба возможных model ID: 0x06 и 0x1B
    if (data[0] != kExpectedModelId && data[0] != 0x1B) {
        ESP_LOGW(TAG, "Invalid light sensor model ID: received 0x%02X, expected 0x%02X or 0x1B (address 0x%02X)", 
                 data[0], kExpectedModelId, TREMA_LIGHT_ADDR);
        return false;
    }
    
    if (data[0] != kExpectedModelId) {
        ESP_LOGI(TAG, "Light sensor model ID: 0x%02X (using alternative ID, expected 0x%02X)", 
                 data[0], kExpectedModelId);
    }
    
    sensor_initialized = true;
    use_stub_values = false;
    ESP_LOGI(TAG, "Light sensor initialized successfully on I2C bus %d, address 0x%02X, model ID: 0x%02X", 
             i2c_bus, TREMA_LIGHT_ADDR, data[0]);
    return true;
}

bool trema_light_read(float *lux)
{
    if (lux == NULL) {
        ESP_LOGE(TAG, "trema_light_read: lux pointer is NULL");
        return false;
    }
    
    ESP_LOGD(TAG, "trema_light_read: sensor_initialized=%d, bus=%d, addr=0x%02X", 
             sensor_initialized, s_i2c_bus, TREMA_LIGHT_ADDR);
    
    if (!sensor_initialized) {
        ESP_LOGD(TAG, "Sensor not initialized, attempting initialization...");
        if (!trema_light_init(s_i2c_bus)) {
            ESP_LOGW(TAG, "Light sensor initialization failed, returning stub value");
            *lux = stub_lux;
            use_stub_values = true;
            return false;
        }
    }
    
    if (!i2c_bus_is_initialized_bus(s_i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", s_i2c_bus);
        *lux = stub_lux;
        use_stub_values = true;
        return false;
    }
    
    uint8_t reg_lux = REG_LIGHT_LUX;
    esp_err_t err = ESP_ERR_NOT_FOUND;
    
    // Попытка получить данные из кэша (TTL 500ms для частого опроса)
    if (i2c_cache_is_initialized()) {
        ESP_LOGD(TAG, "Checking I2C cache for light value...");
        err = i2c_cache_get(s_i2c_bus, TREMA_LIGHT_ADDR, &reg_lux, 1, data, 2, 500);
        if (err == ESP_OK) {
            ESP_LOGD(TAG, "Light value retrieved from cache: data[0]=0x%02X, data[1]=0x%02X", data[0], data[1]);
        } else {
            ESP_LOGD(TAG, "Cache miss or expired, will read from I2C");
        }
    }
    
    // Если данных нет в кэше, читаем из I2C
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "Reading light value from I2C: bus=%d, addr=0x%02X, reg=0x%02X", 
                 s_i2c_bus, TREMA_LIGHT_ADDR, reg_lux);
        err = i2c_bus_read_bus(s_i2c_bus, TREMA_LIGHT_ADDR, &reg_lux, 1, data, 2, 1000);
        if (err == ESP_OK) {
            ESP_LOGD(TAG, "I2C read successful: data[0]=0x%02X, data[1]=0x%02X", data[0], data[1]);
            if (i2c_cache_is_initialized()) {
                // Сохраняем в кэш
                i2c_cache_put(s_i2c_bus, TREMA_LIGHT_ADDR, &reg_lux, 1, data, 2, 500);
                ESP_LOGD(TAG, "Light value cached");
            }
        } else {
            ESP_LOGW(TAG, "I2C read failed: %s (error code: %d), bus=%d, addr=0x%02X", 
                     esp_err_to_name(err), err, s_i2c_bus, TREMA_LIGHT_ADDR);
        }
    }
    
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Light sensor read failed: %s, returning stub value %.0f lux", 
                 esp_err_to_name(err), stub_lux);
        *lux = stub_lux;
        use_stub_values = true;
        return false;
    }
    
    // Convert the 2-byte value to float (люкс)
    // Значение хранится как целое число
    uint16_t lux_raw = ((uint16_t)data[1] << 8) | data[0];
    *lux = (float)lux_raw;
    
    ESP_LOGD(TAG, "Raw light value: 0x%04X (%u), converted: %.0f lux", lux_raw, lux_raw, *lux);
    
    // Validate lux range (0 - 65535 lux)
    if (*lux < 0.0f || *lux > 65535.0f) {
        ESP_LOGW(TAG, "Invalid light value: %.0f lux (out of range 0-65535), using stub value", *lux);
        *lux = stub_lux;
        use_stub_values = true;
        return false;
    }
    
    use_stub_values = false;
    ESP_LOGD(TAG, "Light sensor read successful: %.0f lux", *lux);
    return true;
}

bool trema_light_is_using_stub_values(void)
{
    return use_stub_values;
}

bool trema_light_is_initialized(void)
{
    return sensor_initialized;
}

