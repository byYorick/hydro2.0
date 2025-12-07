/**
 * @file ccs811.c
 * @brief Реализация драйвера CCS811 (CO₂/TVOC сенсор)
 * 
 * Реализует полноценный драйвер для CCS811 сенсора с:
 * - Инициализацией и проверкой сенсора
 * - Чтением CO₂ и TVOC значений
 * - Интеграцией с i2c_cache для оптимизации
 * - Интеграцией с diagnostics для метрик
 * 
 * Согласно спецификации CCS811 от AMS
 */

#include "ccs811.h"
#include "i2c_bus.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

// Условный include для diagnostics
#ifdef __has_include
    #if __has_include("diagnostics.h")
        #include "diagnostics.h"
        #define DIAGNOSTICS_AVAILABLE 1
    #endif
#endif
#ifndef DIAGNOSTICS_AVAILABLE
    #define DIAGNOSTICS_AVAILABLE 0
#endif

static const char *TAG = "ccs811";

// Stub values for when sensor is not connected
static bool use_stub_values = false;
static uint16_t stub_co2 = 650;   // Нормальный уровень CO₂ в помещении
static uint16_t stub_tvoc = 15;   // Нормальный уровень TVOC

// Buffer for I2C communication
static uint8_t data[8];

// Sensor state
static struct {
    bool initialized;
    bool config_initialized;
    ccs811_config_t config;
    uint32_t last_read_time_ms;
} s_ccs811 = {0};

/**
 * @brief Чтение регистра CCS811
 */
static esp_err_t ccs811_read_register(uint8_t reg, uint8_t *data, size_t len) {
    if (!s_ccs811.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (!i2c_bus_is_initialized_bus(s_ccs811.config.i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", s_ccs811.config.i2c_bus);
        return ESP_ERR_INVALID_STATE;
    }
    
    return i2c_bus_read_bus(s_ccs811.config.i2c_bus, s_ccs811.config.i2c_address, 
                          &reg, 1, data, len, 1000);
}

/**
 * @brief Запись в регистр CCS811
 */
static esp_err_t ccs811_write_register(uint8_t reg, const uint8_t *data, size_t len) {
    if (!s_ccs811.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (!i2c_bus_is_initialized_bus(s_ccs811.config.i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", s_ccs811.config.i2c_bus);
        return ESP_ERR_INVALID_STATE;
    }
    
    // Передаем регистр отдельно, а данные отдельно
    return i2c_bus_write_bus(s_ccs811.config.i2c_bus, s_ccs811.config.i2c_address,
                             &reg, 1, data, len, 1000);
}

/**
 * @brief Проверка Hardware ID сенсора
 */
static esp_err_t ccs811_check_hw_id(void) {
    uint8_t hw_id = 0;
    esp_err_t err = ccs811_read_register(CCS811_REG_HW_ID, &hw_id, 1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read HW_ID: %s", esp_err_to_name(err));
        return err;
    }
    
    if (hw_id != CCS811_HW_ID_VALUE) {
        ESP_LOGE(TAG, "Invalid HW_ID: 0x%02X (expected 0x%02X)", hw_id, CCS811_HW_ID_VALUE);
        return ESP_ERR_NOT_FOUND;
    }
    
    ESP_LOGI(TAG, "CCS811 HW_ID verified: 0x%02X", hw_id);
    return ESP_OK;
}

/**
 * @brief Запуск приложения CCS811
 */
static esp_err_t ccs811_app_start(void) {
    // Проверяем статус перед запуском
    uint8_t status = 0;
    esp_err_t err = ccs811_read_register(CCS811_REG_STATUS, &status, 1);
    if (err != ESP_OK) {
        return err;
    }
    
    // Если приложение уже запущено, ничего не делаем
    if (status & CCS811_STATUS_APP_VALID) {
        ESP_LOGI(TAG, "CCS811 application already started");
        return ESP_OK;
    }
    
    // Запускаем приложение (команда без данных)
    uint8_t app_start_cmd = 0;
    err = ccs811_write_register(CCS811_REG_APP_START, &app_start_cmd, 1);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start CCS811 application: %s", esp_err_to_name(err));
        return err;
    }
    
    // Ждем немного для инициализации
    vTaskDelay(pdMS_TO_TICKS(100));
    
    // Проверяем статус снова
    err = ccs811_read_register(CCS811_REG_STATUS, &status, 1);
    if (err != ESP_OK) {
        return err;
    }
    
    if (!(status & CCS811_STATUS_APP_VALID)) {
        ESP_LOGE(TAG, "CCS811 application failed to start (status=0x%02X)", status);
        return ESP_FAIL;
    }
    
    ESP_LOGI(TAG, "CCS811 application started successfully");
    return ESP_OK;
}

/**
 * @brief Настройка режима измерений
 */
static esp_err_t ccs811_set_measurement_mode(uint8_t mode) {
    return ccs811_write_register(CCS811_REG_MEAS_MODE, &mode, 1);
}

esp_err_t ccs811_init(const ccs811_config_t *config) {
    if (s_ccs811.initialized) {
        ESP_LOGW(TAG, "CCS811 already initialized");
        return ESP_OK;
    }
    
    // Установка конфигурации по умолчанию
    if (config != NULL) {
        memcpy(&s_ccs811.config, config, sizeof(ccs811_config_t));
    } else {
        s_ccs811.config.i2c_address = CCS811_I2C_ADDR_DEFAULT;
        s_ccs811.config.i2c_bus = I2C_BUS_0;
        s_ccs811.config.measurement_mode = CCS811_MEAS_MODE_1SEC;
        s_ccs811.config.measurement_interval_ms = 1000;
    }
    s_ccs811.config_initialized = true;
    
    // Проверка инициализации I2C шины
    if (!i2c_bus_is_initialized_bus(s_ccs811.config.i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", s_ccs811.config.i2c_bus);
        return ESP_ERR_INVALID_STATE;
    }
    
    ESP_LOGI(TAG, "Initializing CCS811 (addr=0x%02X, bus=%d)", 
             s_ccs811.config.i2c_address, s_ccs811.config.i2c_bus);
    
    // Проверка Hardware ID
    esp_err_t err = ccs811_check_hw_id();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "CCS811 not found or invalid, will use stub values");
        use_stub_values = true;
        s_ccs811.initialized = false;
        return err;
    }
    
    // Запуск приложения
    err = ccs811_app_start();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to start CCS811 application, will use stub values");
        use_stub_values = true;
        s_ccs811.initialized = false;
        return err;
    }
    
    // Настройка режима измерений
    err = ccs811_set_measurement_mode(s_ccs811.config.measurement_mode);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set measurement mode, using default");
        s_ccs811.config.measurement_mode = CCS811_MEAS_MODE_1SEC;
        ccs811_set_measurement_mode(s_ccs811.config.measurement_mode);
    }
    
    s_ccs811.initialized = true;
    use_stub_values = false;
    s_ccs811.last_read_time_ms = 0;
    
    ESP_LOGI(TAG, "CCS811 initialized successfully (mode=0x%02X)", s_ccs811.config.measurement_mode);
    return ESP_OK;
}

esp_err_t ccs811_deinit(void) {
    if (!s_ccs811.initialized) {
        return ESP_OK;
    }
    
    // Переводим в режим IDLE
    uint8_t idle_mode = CCS811_MEAS_MODE_IDLE;
    ccs811_set_measurement_mode(idle_mode);
    
    s_ccs811.initialized = false;
    use_stub_values = false;
    
    ESP_LOGI(TAG, "CCS811 deinitialized");
    return ESP_OK;
}

esp_err_t ccs811_read(ccs811_reading_t *reading) {
    if (reading == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    memset(reading, 0, sizeof(ccs811_reading_t));
    
    // Если сенсор не инициализирован, пытаемся инициализировать
    if (!s_ccs811.initialized) {
        const ccs811_config_t *cfg = NULL;
        if (s_ccs811.config_initialized) {
            cfg = &s_ccs811.config;
        }
        esp_err_t err = ccs811_init(cfg);
        if (err != ESP_OK) {
            // Используем stub значения
            reading->co2_ppm = stub_co2;
            reading->tvoc_ppb = stub_tvoc;
            reading->valid = false;
            use_stub_values = true;
            
            #if DIAGNOSTICS_AVAILABLE
            if (diagnostics_is_initialized()) {
                diagnostics_update_sensor_metrics("ccs811", false);
            }
            #endif
            
            return ESP_ERR_INVALID_STATE;
        }
    }
    
    if (use_stub_values) {
        reading->co2_ppm = stub_co2;
        reading->tvoc_ppb = stub_tvoc;
        reading->valid = false;
        return ESP_ERR_INVALID_STATE;
    }
    
    if (!i2c_bus_is_initialized_bus(s_ccs811.config.i2c_bus)) {
        ESP_LOGE(TAG, "I²C bus %d not initialized", s_ccs811.config.i2c_bus);
        reading->co2_ppm = stub_co2;
        reading->tvoc_ppb = stub_tvoc;
        reading->valid = false;
        use_stub_values = true;
        return ESP_ERR_INVALID_STATE;
    }
    
    uint8_t reg_result = CCS811_REG_ALG_RESULT_DATA;
    esp_err_t err = ESP_ERR_NOT_FOUND;
    
    // Попытка получить данные из кэша (TTL 1000ms для CCS811)
    if (i2c_cache_is_initialized()) {
        err = i2c_cache_get(s_ccs811.config.i2c_bus, s_ccs811.config.i2c_address,
                           &reg_result, 1, data, 4, 1000);
        if (err == ESP_OK) {
            ESP_LOGD(TAG, "CCS811 data retrieved from cache");
        }
    }
    
    // Если данных нет в кэше, читаем из I2C
    if (err != ESP_OK) {
        // Сначала проверяем статус
        uint8_t status = 0;
        err = ccs811_read_register(CCS811_REG_STATUS, &status, 1);
        if (err != ESP_OK) {
            ESP_LOGD(TAG, "Failed to read status: %s", esp_err_to_name(err));
            reading->co2_ppm = stub_co2;
            reading->tvoc_ppb = stub_tvoc;
            reading->valid = false;
            use_stub_values = true;
            
            #if DIAGNOSTICS_AVAILABLE
            if (diagnostics_is_initialized()) {
                diagnostics_update_sensor_metrics("ccs811", false);
            }
            #endif
            
            return err;
        }
        
        // Проверяем наличие ошибок
        if (status & CCS811_STATUS_ERROR) {
            uint8_t error_id = 0;
            ccs811_read_register(CCS811_REG_ERROR_ID, &error_id, 1);
            ESP_LOGW(TAG, "CCS811 error detected: 0x%02X", error_id);
            reading->error_id = error_id;
        }
        
        // Проверяем готовность данных
        if (!(status & CCS811_STATUS_DATA_READY)) {
            ESP_LOGD(TAG, "CCS811 data not ready (status=0x%02X)", status);
            reading->co2_ppm = stub_co2;
            reading->tvoc_ppb = stub_tvoc;
            reading->valid = false;
            return ESP_ERR_NOT_FINISHED;
        }
        
        // Читаем результаты измерений (4 байта: CO2 MSB, CO2 LSB, TVOC MSB, TVOC LSB)
        err = ccs811_read_register(CCS811_REG_ALG_RESULT_DATA, data, 4);
        if (err == ESP_OK && i2c_cache_is_initialized()) {
            // Сохраняем в кэш
            i2c_cache_put(s_ccs811.config.i2c_bus, s_ccs811.config.i2c_address,
                        &reg_result, 1, data, 4, 1000);
        }
    }
    
    if (err != ESP_OK) {
        ESP_LOGD(TAG, "CCS811 read failed: %s, returning stub values", esp_err_to_name(err));
        reading->co2_ppm = stub_co2;
        reading->tvoc_ppb = stub_tvoc;
        reading->valid = false;
        use_stub_values = true;
        
        #if DIAGNOSTICS_AVAILABLE
        if (diagnostics_is_initialized()) {
            diagnostics_update_sensor_metrics("ccs811", false);
        }
        #endif
        
        return err;
    }
    
    // Парсим данные (big-endian)
    reading->co2_ppm = ((uint16_t)data[0] << 8) | data[1];
    reading->tvoc_ppb = ((uint16_t)data[2] << 8) | data[3];
    
    // Валидация значений
    // CO₂: 400-8192 ppm (нормальный диапазон)
    // TVOC: 0-1187 ppb
    if (reading->co2_ppm < 400 || reading->co2_ppm > 8192) {
        ESP_LOGW(TAG, "Invalid CO2 value: %u ppm, using stub", reading->co2_ppm);
        reading->co2_ppm = stub_co2;
        reading->valid = false;
    } else if (reading->tvoc_ppb > 1187) {
        ESP_LOGW(TAG, "Invalid TVOC value: %u ppb, using stub", reading->tvoc_ppb);
        reading->tvoc_ppb = stub_tvoc;
        reading->valid = false;
    } else {
        reading->valid = true;
    }
    
    use_stub_values = false;
    s_ccs811.last_read_time_ms = (uint32_t)(esp_timer_get_time() / 1000);
    
    // Обновление метрик диагностики
    #if DIAGNOSTICS_AVAILABLE
    if (diagnostics_is_initialized()) {
        diagnostics_update_sensor_metrics("ccs811", reading->valid);
    }
    #endif
    
    return ESP_OK;
}

bool ccs811_is_initialized(void) {
    return s_ccs811.initialized && !use_stub_values;
}

esp_err_t ccs811_get_status(uint8_t *status) {
    if (status == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!s_ccs811.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    return ccs811_read_register(CCS811_REG_STATUS, status, 1);
}

bool ccs811_is_data_ready(void) {
    if (!s_ccs811.initialized) {
        return false;
    }
    
    uint8_t status = 0;
    if (ccs811_get_status(&status) != ESP_OK) {
        return false;
    }
    
    return (status & CCS811_STATUS_DATA_READY) != 0;
}
