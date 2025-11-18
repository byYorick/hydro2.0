/**
 * @file trema_ph.c
 * @brief Реализация драйвера Trema pH-сенсора
 * 
 * Адаптирован из mesh_hydro/hydro1.0 для новой архитектуры hydro2.0
 * Использует новый API i2c_bus компонента
 */

#include "trema_ph.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>

static const char *TAG = "trema_ph";

// Stub values for when sensor is not connected
static bool use_stub_values = false;
static float stub_ph = 6.5f;  // Neutral pH

// Buffer for I2C communication
static uint8_t data[4];

// Sensor initialization flag
static bool sensor_initialized = false;

bool trema_ph_init(void)
{
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return false;
    }
    
    // Try to communicate with the sensor
    // Read the model register to verify sensor presence
    uint8_t reg_model = REG_MODEL;
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_model, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read from pH sensor: %s", esp_err_to_name(err));
        return false;
    }
    
    // Check if we got a valid response
    // For iarduino pH sensor, model ID should be 0x1A
    if (data[0] != 0x1A) {
        ESP_LOGW(TAG, "Invalid pH sensor model ID: 0x%02X", data[0]);
        return false;
    }
    
    sensor_initialized = true;
    use_stub_values = false;
    ESP_LOGI(TAG, "pH sensor initialized successfully");
    return true;
}

bool trema_ph_read(float *ph)
{
    if (ph == NULL) {
        return false;
    }
    
    if (!sensor_initialized) {
        if (!trema_ph_init()) {
            ESP_LOGD(TAG, "PH sensor not connected, returning stub value");
            *ph = stub_ph;
            use_stub_values = true;
            return false;
        }
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        *ph = stub_ph;
        use_stub_values = true;
        return false;
    }
    
    uint8_t reg_ph = REG_PH_pH;
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_ph, 1, data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "PH sensor read failed: %s, returning stub value", esp_err_to_name(err));
        *ph = stub_ph;
        use_stub_values = true;
        return false;
    }
    
    // Convert the 2-byte value to float
    // pH value is stored as integer in thousandths (multiply by 0.001)
    uint16_t pH_raw = ((uint16_t)data[1] << 8) | data[0];
    *ph = (float)pH_raw * 0.001f;
    
    // Validate pH range
    if (*ph < 0.0f || *ph > 14.0f) {
        ESP_LOGW(TAG, "Invalid pH value: %.3f, using stub value", *ph);
        *ph = stub_ph;
        use_stub_values = true;
        return false;
    }
    
    use_stub_values = false;
    return true;
}

bool trema_ph_calibrate(uint8_t stage, float known_pH)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        return false;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return false;
    }
    
    // Validate parameters
    if ((stage != 1 && stage != 2) || known_pH < 0.0f || known_pH > 14.0f) {
        ESP_LOGW(TAG, "Invalid calibration parameters");
        return false;
    }
    
    // Write known pH value
    uint8_t reg_known_ph = REG_PH_KNOWN_PH;
    uint16_t ph_value_int = (uint16_t)(known_pH * 1000.0f);
    uint8_t ph_data[2] = {
        ph_value_int & 0x00FF,       // LSB
        (ph_value_int >> 8) & 0x00FF // MSB
    };
    
    esp_err_t err = i2c_bus_write(TREMA_PH_ADDR, &reg_known_ph, 1, ph_data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write known pH value: %s", esp_err_to_name(err));
        return false;
    }
    
    vTaskDelay(pdMS_TO_TICKS(10));
    
    // Send calibration command
    uint8_t reg_cal = REG_PH_CALIBRATION;
    uint8_t cal_cmd = (stage == 1 ? PH_BIT_CALC_1 : PH_BIT_CALC_2) | PH_CODE_CALC_SAVE;
    
    err = i2c_bus_write(TREMA_PH_ADDR, &reg_cal, 1, &cal_cmd, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send calibration command: %s", esp_err_to_name(err));
        return false;
    }
    
    ESP_LOGI(TAG, "Calibration stage %d started with pH %.3f", stage, known_pH);
    return true;
}

uint8_t trema_ph_get_calibration_status(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        return 0;
    }
    
    if (!i2c_bus_is_initialized()) {
        return 0;
    }
    
    // Read calibration status
    uint8_t reg_cal = REG_PH_CALIBRATION;
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_cal, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration status: %s", esp_err_to_name(err));
        return 0;
    }
    
    if (data[0] & 0x40) { // PH_FLG_STATUS_1
        return 1;
    } else if (data[0] & 0x80) { // PH_FLG_STATUS_2
        return 2;
    }
    
    return 0;
}

bool trema_ph_get_calibration_result(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        return false;
    }
    
    if (!i2c_bus_is_initialized()) {
        return false;
    }
    
    // Read error flags
    uint8_t reg_error = REG_PH_ERROR;
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_error, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration result: %s", esp_err_to_name(err));
        return false;
    }
    
    // Return true if calibration error flag is NOT set
    return !(data[0] & PH_FLG_CALC_ERR);
}

bool trema_ph_get_stability(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        return false;
    }
    
    if (!i2c_bus_is_initialized()) {
        return false;
    }
    
    // Read error flags
    uint8_t reg_error = REG_PH_ERROR;
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_error, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read stability status: %s", esp_err_to_name(err));
        return false;
    }
    
    // Check if stability error flag is set
    if (data[0] & PH_FLG_STAB_ERR) {
        ESP_LOGD(TAG, "pH measurement is not stable (STAB_ERR flag set)");
        return false;
    }
    
    // Return true if stability error flag is NOT set
    return true;
}

bool trema_ph_wait_for_stable_reading(uint32_t timeout_ms)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        return false;
    }
    
    uint32_t elapsed_time = 0;
    const uint32_t check_interval = 100; // Check every 100ms
    
    while (elapsed_time < timeout_ms) {
        if (trema_ph_get_stability()) {
            return true; // Measurement is stable
        }
        
        vTaskDelay(pdMS_TO_TICKS(check_interval));
        elapsed_time += check_interval;
    }
    
    ESP_LOGW(TAG, "Timeout waiting for stable pH measurement after %u ms", (unsigned int)timeout_ms);
    return false; // Timeout occurred
}

float trema_ph_get_value(void)
{
    float ph;
    if (trema_ph_read(&ph)) {
        return ph;
    }
    return stub_ph;
}

bool trema_ph_reset(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Cannot reset uninitialized pH sensor");
        return false;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        return false;
    }
    
    // Send reset command
    // For iarduino pH sensor, we need to set bit 7 of REG_BITS_0
    uint8_t reg_bits = 0x01; // REG_BITS_0
    
    // Read current value
    esp_err_t err = i2c_bus_read(TREMA_PH_ADDR, &reg_bits, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read from pH sensor for reset: %s", esp_err_to_name(err));
        return false;
    }
    
    // Set reset bit (bit 7)
    uint8_t reset_value = data[0] | 0x80;
    err = i2c_bus_write(TREMA_PH_ADDR, &reg_bits, 1, &reset_value, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send reset command to pH sensor: %s", esp_err_to_name(err));
        return false;
    }
    
    // Wait for reset to complete
    vTaskDelay(pdMS_TO_TICKS(100));
    
    ESP_LOGI(TAG, "pH sensor reset completed");
    return true;
}

bool trema_ph_is_using_stub_values(void)
{
    return use_stub_values;
}

bool trema_ph_is_initialized(void)
{
    return sensor_initialized;
}

