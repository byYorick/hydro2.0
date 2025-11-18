/**
 * @file trema_ec.c
 * @brief Реализация драйвера Trema EC-сенсора
 * 
 * Адаптирован из mesh_hydro/hydro1.0 для новой архитектуры hydro2.0
 * Использует новый API i2c_bus компонента
 */

#include "trema_ec.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>

static const char *TAG = "trema_ec";

// Stub values for when sensor is not connected
static bool use_stub_values = false;
static float stub_ec = 1.2f;  // 1.2 mS/cm
static uint16_t stub_tds = 800;  // 800 ppm
static trema_ec_error_t last_error = TREMA_EC_ERROR_NONE;
static float last_temperature_c = NAN;

// Buffer for I2C communication
static uint8_t data[4];

// Sensor initialization flag
static bool sensor_initialized = false;

bool trema_ec_init(void)
{
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    // Try to communicate with the sensor
    // Read the model register to verify sensor presence
    uint8_t reg_model = REG_MODEL;
    esp_err_t err = i2c_bus_read(TREMA_EC_ADDR, &reg_model, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read from EC sensor: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    // Check if we got a valid response
    // For iarduino TDS sensor, model ID should be 0x19
    if (data[0] != 0x19) {
        ESP_LOGW(TAG, "Invalid EC sensor model ID: 0x%02X", data[0]);
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    sensor_initialized = true;
    use_stub_values = false;
    last_error = TREMA_EC_ERROR_NONE;
    ESP_LOGI(TAG, "EC sensor initialized successfully");
    return true;
}

bool trema_ec_read(float *ec)
{
    if (ec == NULL) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    if (!sensor_initialized) {
        if (!trema_ec_init()) {
            ESP_LOGD(TAG, "EC sensor not connected, returning stub value");
            *ec = stub_ec;
            use_stub_values = true;
            last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
            return false;
        }
    }

    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    uint8_t reg_ec = REG_TDS_EC;
    esp_err_t err = i2c_bus_read(TREMA_EC_ADDR, &reg_ec, 1, data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "EC sensor read failed: %s, returning stub value", esp_err_to_name(err));
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    uint16_t ec_raw = ((uint16_t)data[1] << 8) | data[0];
    *ec = (float)ec_raw * 0.001f;
    
    if (*ec < 0.0f || *ec > 10.0f) {
        ESP_LOGW(TAG, "Invalid EC value: %.3f mS/cm, using stub value", *ec);
        *ec = stub_ec;
        use_stub_values = true;
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    use_stub_values = false;
    last_error = TREMA_EC_ERROR_NONE;
    return true;
}

bool trema_ec_calibrate(uint8_t stage, uint16_t known_tds)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        return false;
    }
    
    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    // Validate parameters
    if ((stage != 1 && stage != 2) || known_tds > 10000) {
        ESP_LOGW(TAG, "Invalid calibration parameters");
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }
    
    // Write known TDS value
    uint8_t reg_known_tds = REG_TDS_KNOWN_TDS;
    uint8_t tds_data[2] = {
        known_tds & 0x00FF,       // LSB
        (known_tds >> 8) & 0x00FF // MSB
    };
    
    esp_err_t err = i2c_bus_write(TREMA_EC_ADDR, &reg_known_tds, 1, tds_data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to write known TDS value: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    vTaskDelay(pdMS_TO_TICKS(10));
    
    // Send calibration command
    uint8_t reg_cal = REG_TDS_CALIBRATION;
    uint8_t cal_cmd = (stage == 1 ? TDS_BIT_CALC_1 : TDS_BIT_CALC_2) | TDS_CODE_CALC_SAVE;
    
    err = i2c_bus_write(TREMA_EC_ADDR, &reg_cal, 1, &cal_cmd, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to send calibration command: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    ESP_LOGI(TAG, "Calibration stage %d started with TDS %u ppm", stage, known_tds);
    last_error = TREMA_EC_ERROR_NONE;
    return true;
}

uint8_t trema_ec_get_calibration_status(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        return 0;
    }
    
    if (!i2c_bus_is_initialized()) {
        return 0;
    }
    
    // Read calibration status
    uint8_t reg_cal = REG_TDS_CALIBRATION;
    esp_err_t err = i2c_bus_read(TREMA_EC_ADDR, &reg_cal, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read calibration status: %s", esp_err_to_name(err));
        return 0;
    }
    
    if (data[0] & 0x40) { // TDS_FLG_STATUS_1
        return 1;
    } else if (data[0] & 0x80) { // TDS_FLG_STATUS_2
        return 2;
    }
    
    return 0;
}

bool trema_ec_set_temperature(float temperature)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        ESP_LOGW(TAG, "Sensor not initialized");
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        return false;
    }

    if (!i2c_bus_is_initialized()) {
        ESP_LOGE(TAG, "I²C bus not initialized");
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }
    
    // Validate temperature range (0 - 63.75 °C)
    if (temperature < 0.0f || temperature > 63.75f) {
        ESP_LOGW(TAG, "Invalid temperature: %.2f C", temperature);
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }
    
    // Convert temperature to register format (0.25°C steps)
    uint8_t temp_reg = (uint8_t)(temperature * 4.0f);
    
    // Write temperature to register
    uint8_t reg_temp = REG_TDS_t;
    esp_err_t err = i2c_bus_write(TREMA_EC_ADDR, &reg_temp, 1, &temp_reg, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set temperature: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    ESP_LOGD(TAG, "Temperature set to %.2f C", temperature);
    last_temperature_c = temperature;
    last_error = TREMA_EC_ERROR_NONE;
    return true;
}

bool trema_ec_get_temperature(float *temperature)
{
    if (temperature == NULL) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        return false;
    }

    if (!i2c_bus_is_initialized()) {
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    uint8_t reg_temp = REG_TDS_t;
    esp_err_t err = i2c_bus_read(TREMA_EC_ADDR, &reg_temp, 1, data, 1, 1000);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to read temperature: %s", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return false;
    }

    float temp_c = (float)data[0] / 4.0f;
    if (temp_c < 0.0f || temp_c > 63.75f) {
        last_error = TREMA_EC_ERROR_INVALID_VALUE;
        return false;
    }

    *temperature = temp_c;
    last_temperature_c = temp_c;
    last_error = TREMA_EC_ERROR_NONE;
    return true;
}

uint16_t trema_ec_get_tds(void)
{
    // Check if sensor is initialized
    if (!sensor_initialized) {
        last_error = TREMA_EC_ERROR_NOT_INITIALIZED;
        return stub_tds;
    }

    if (!i2c_bus_is_initialized()) {
        last_error = TREMA_EC_ERROR_I2C;
        return stub_tds;
    }
    
    // Request TDS measurement
    uint8_t reg_tds = REG_TDS_TDS;
    esp_err_t err = i2c_bus_read(TREMA_EC_ADDR, &reg_tds, 1, data, 2, 1000);
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "TDS sensor read failed: %s, using stub values", esp_err_to_name(err));
        last_error = TREMA_EC_ERROR_I2C;
        return stub_tds;
    }

    // Convert the 2-byte value to uint16_t
    last_error = TREMA_EC_ERROR_NONE;
    return ((uint16_t)data[1] << 8) | data[0];
}

float trema_ec_get_conductivity(void)
{
    float ec;
    if (trema_ec_read(&ec)) {
        return ec;
    }
    return stub_ec;
}

bool trema_ec_is_using_stub_values(void)
{
    return use_stub_values;
}

trema_ec_error_t trema_ec_get_error(void)
{
    return last_error;
}

