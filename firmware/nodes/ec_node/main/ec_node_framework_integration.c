/**
 * @file ec_node_framework_integration.c
 * @brief Интеграция ec_node с node_framework
 * 
 * Этот файл связывает ec_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "ec_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "ec_node_app.h"
#include "pump_driver.h"
#include "trema_ec.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include <string.h>
#include <math.h>
#include <float.h>

static const char *TAG = "ec_node_fw";

// Forward declaration для callback safe_mode
static esp_err_t ec_node_disable_actuators_in_safe_mode(void *user_ctx);

// Callback для инициализации каналов из NodeConfig
static esp_err_t ec_node_init_channel_callback(
    const char *channel_name,
    const cJSON *channel_config,
    void *user_ctx
) {
    (void)user_ctx;
    
    if (channel_name == NULL || channel_config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Initializing channel: %s", channel_name);

    // Проверяем тип канала
    cJSON *type_item = cJSON_GetObjectItem(channel_config, "type");
    if (!cJSON_IsString(type_item)) {
        ESP_LOGW(TAG, "Channel %s: missing or invalid type", channel_name);
        return ESP_ERR_INVALID_ARG;
    }

    const char *channel_type = type_item->valuestring;

    // Инициализация насосов
    // Примечание: pump_driver инициализируется через pump_driver_init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcmp(channel_type, "pump") == 0) {
        cJSON *pin_item = cJSON_GetObjectItem(channel_config, "pin");
        if (!cJSON_IsNumber(pin_item)) {
            ESP_LOGW(TAG, "Channel %s: missing or invalid pin", channel_name);
            return ESP_ERR_INVALID_ARG;
        }

        int pin = pin_item->valueint;
        ESP_LOGI(TAG, "Pump channel %s configured on pin %d (will be initialized via pump_driver_init_from_config)", 
                channel_name, pin);
        return ESP_OK;
    }

    return ESP_OK;
}

// Обработчик команды run_pump
static esp_err_t handle_run_pump(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    if (!cJSON_IsNumber(duration_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_params",
            "Missing or invalid duration_ms",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    int duration_ms = duration_item->valueint;
    if (duration_ms <= 0 || duration_ms > 60000) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_params",
            "duration_ms must be between 1 and 60000",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = pump_driver_run(channel, duration_ms);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "pump_error",
            "Failed to run pump",
            NULL
        );
        return err;
    }

    *response = node_command_handler_create_response(
        NULL,
        "ACK",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "Pump %s started for %d ms", channel, duration_ms);
    return ESP_OK;
}

// Обработчик команды stop_pump
static esp_err_t handle_stop_pump(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)params;
    (void)user_ctx;

    if (channel == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = pump_driver_stop(channel);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "pump_error",
            "Failed to stop pump",
            NULL
        );
        return err;
    }

    *response = node_command_handler_create_response(
        NULL,
        "ACK",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "Pump %s stopped", channel);
    return ESP_OK;
}

// Обработчик команды calibrate
static esp_err_t handle_calibrate(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)channel;
    (void)user_ctx;

    if (params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *stage_item = cJSON_GetObjectItem(params, "stage");
    cJSON *tds_value_item = cJSON_GetObjectItem(params, "tds_value");

    if (!cJSON_IsNumber(stage_item) || !cJSON_IsNumber(tds_value_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_format",
            "Missing stage or tds_value",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
    uint16_t known_tds = (uint16_t)cJSON_GetNumberValue(tds_value_item);

    if (stage != 1 && stage != 2) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_stage",
            "Stage must be 1 or 2",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (known_tds > 10000) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_tds",
            "TDS value must be <= 10000",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    ESP_LOGI(TAG, "Starting EC calibration: stage=%d, known_tds=%u ppm", stage, known_tds);

    bool cal_success = trema_ec_calibrate(stage, known_tds);
    trema_ec_error_t cal_error = trema_ec_get_error();

    if (!cal_success || cal_error != TREMA_EC_ERROR_NONE) {
        const char *error_msg = "Calibration failed";
        if (cal_error == TREMA_EC_ERROR_NOT_INITIALIZED) {
            error_msg = "EC sensor not initialized";
        } else if (cal_error == TREMA_EC_ERROR_INVALID_VALUE) {
            error_msg = "Invalid calibration value";
        } else if (cal_error == TREMA_EC_ERROR_INVALID_VALUE) {
            error_msg = "Invalid TDS value";
        }

        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "calibration_failed",
            error_msg,
            NULL
        );
        return ESP_FAIL;
    }

    *response = node_command_handler_create_response(
        NULL,
        "ACK",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "EC calibration stage %d completed successfully", stage);
    return ESP_OK;
}

// Публикация телеметрии через node_framework
esp_err_t ec_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    // Инициализация сенсора, если не инициализирован
    // Проверяем через попытку чтения температуры (если сенсор не инициализирован, вернет false)
    float temp_check = 0.0f;
    bool sensor_ready = trema_ec_get_temperature(&temp_check);
    
    if (!sensor_ready && i2c_bus_is_initialized()) {
        if (trema_ec_init()) {
            ESP_LOGI(TAG, "Trema EC sensor initialized");
            sensor_ready = true;
        }
    }

    // Получение температуры для компенсации
    float compensation_temp = 25.0f;
    bool stored_temp_valid = (config_storage_get_last_temperature(&compensation_temp) == ESP_OK);
    if (!stored_temp_valid) {
        compensation_temp = 25.0f;
    }

    // Применение температурной компенсации
    if (sensor_ready) {
        if (!trema_ec_set_temperature(compensation_temp)) {
            ESP_LOGW(TAG, "Failed to apply stored temperature %.2fC", compensation_temp);
        }
    }

    // Чтение значения EC
    float ec_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    uint16_t tds_value = 0;
    trema_ec_error_t read_error = TREMA_EC_ERROR_NOT_INITIALIZED;

    if (sensor_ready) {
        read_success = trema_ec_read(&ec_value);
        using_stub = trema_ec_is_using_stub_values();
        read_error = trema_ec_get_error();
        if (!read_success || isnan(ec_value)) {
            ESP_LOGW(TAG, "Failed to read EC value, using stub");
            ec_value = 1.2f;
            using_stub = true;
        }
        tds_value = trema_ec_get_tds();
    } else {
        ESP_LOGW(TAG, "EC sensor not initialized, using stub value");
        ec_value = 1.2f;
        using_stub = true;
    }

    // Публикация EC через node_telemetry_engine
    int32_t raw_value = (int32_t)(ec_value * 1000);  // Raw value в тысячных
    esp_err_t err = node_telemetry_publish_sensor(
        "ec_sensor",
        METRIC_TYPE_EC,
        ec_value,
        "mS/cm",
        raw_value,
        using_stub,
        true  // is_stable - всегда true для EC
    );

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish EC telemetry: %s", esp_err_to_name(err));
    }

    // Публикация TDS (если доступно) - используем METRIC_TYPE_CUSTOM
    if (sensor_ready && read_error == TREMA_EC_ERROR_NONE && tds_value > 0) {
        err = node_telemetry_publish_sensor(
            "ec_sensor",
            METRIC_TYPE_CUSTOM,
            (float)tds_value,
            "ppm",
            tds_value,
            false,  // not stub
            true     // is_stable
        );

        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish TDS telemetry: %s", esp_err_to_name(err));
        }
    }

    return ESP_OK;
}

// Wrapper для обработчика config (C-совместимый)
static void ec_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    (void)user_ctx;
    node_config_handler_process(topic, data, data_len, user_ctx);
}

// Wrapper для обработчика command (C-совместимый)
static void ec_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

/**
 * @brief Инициализация интеграции ec_node с node_framework
 */
esp_err_t ec_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing ec_node framework integration...");

    // Инициализация node_framework
    node_framework_config_t config = {
        .node_type = "ec",
        .default_node_id = NULL,  // Будет загружен из конфига
        .default_gh_uid = NULL,
        .default_zone_uid = NULL,
        .channel_init_cb = ec_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = ec_node_publish_telemetry_callback,
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация обработчиков команд
    err = node_command_handler_register("run_pump", handle_run_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("stop_pump", handle_stop_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register stop_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("calibrate", handle_calibrate, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register calibrate handler: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(ec_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    ESP_LOGI(TAG, "ec_node framework integration initialized successfully");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t ec_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    return pump_driver_emergency_stop();
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 * 
 * mqtt_client - это алиас для mqtt_manager, поэтому используем mqtt_manager API
 */
void ec_node_framework_register_mqtt_handlers(void) {
    ESP_LOGI(TAG, "Registering MQTT handlers through node_framework...");
    
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(ec_node_config_handler_wrapper, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(ec_node_command_handler_wrapper, NULL);
    
    ESP_LOGI(TAG, "MQTT handlers registered");
}

