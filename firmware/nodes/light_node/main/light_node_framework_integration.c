/**
 * @file light_node_framework_integration.c
 * @brief Интеграция light_node с node_framework
 */

#include "light_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "light_node_defaults.h"
#include "light_node_channel_map.h"
#include "light_node_config_utils.h"
#include "trema_light.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include <stdlib.h>
#include <math.h>
#include <string.h>

static const char *TAG = "light_node_fw";

static cJSON *light_node_channels_callback(void *user_ctx);
static void light_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
);
static void light_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
);
static esp_err_t handle_test_sensor(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
);

// Публикация телеметрии через node_framework
esp_err_t light_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    // Чтение освещенности (Trema light sensor)
    float light_lux = 0.0f;
    bool read_success = trema_light_read(&light_lux);
    bool using_stub = trema_light_is_using_stub_values();
    
    if (read_success && !isnan(light_lux) && isfinite(light_lux) && light_lux >= 0.0f) {
        ESP_LOGD(TAG, "Light sensor read: %.0f lux", light_lux);
        // Публикация освещенности
        esp_err_t err = node_telemetry_publish_sensor(
            "light",
            METRIC_TYPE_CUSTOM,  // Освещенность пока нет в enum, используем CUSTOM
            light_lux,
            "lux",
            0,  // raw value не используется
            using_stub,  // stub если датчик не подключен
            true     // is_stable
        );
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish light: %s", esp_err_to_name(err));
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish light telemetry");
        }
    } else {
        ESP_LOGW(TAG, "Failed to read light sensor: success=%d, lux=%.0f", read_success, light_lux);
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "light_sensor", ESP_ERR_INVALID_RESPONSE, "Failed to read light sensor value");
        
        // Публикация ошибки
        node_telemetry_publish_sensor(
            "light",
            METRIC_TYPE_CUSTOM,
            NAN,
            "lux",
            0,
            true,  // stub (ошибка)
            false
        );
    }

    return ESP_OK;
}

// Обработчик команды test_sensor
static esp_err_t handle_test_sensor(
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

    if (strcmp(channel, "light") != 0) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_channel",
            "Unknown sensor channel",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "i2c_not_initialized",
            "I2C bus is not initialized",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    float light_lux = NAN;
    bool read_success = trema_light_read(&light_lux);
    bool using_stub = trema_light_is_using_stub_values();

    if (!read_success || isnan(light_lux) || !isfinite(light_lux) || light_lux < 0.0f) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "read_failed",
            "Failed to read light sensor",
            NULL
        );
        return ESP_FAIL;
    }

    if (using_stub) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "sensor_stub",
            "Light sensor returned stub values",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddNumberToObject(extra, "value", light_lux);
        cJSON_AddStringToObject(extra, "unit", "lux");
        cJSON_AddStringToObject(extra, "metric_type", "LIGHT_INTENSITY");
        cJSON_AddBoolToObject(extra, "stable", true);
    }

    *response = node_command_handler_create_response(
        NULL,
        "DONE",
        NULL,
        NULL,
        extra
    );
    if (extra) {
        cJSON_Delete(extra);
    }

    return ESP_OK;
}

// Wrapper для обработчика config
static void light_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    if (data == NULL || data_len <= 0) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    bool changed = false;
    char *patched = light_node_build_patched_config(data, (size_t)data_len, true, &changed);
    if (!patched) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    node_config_handler_process(topic, patched, (int)strlen(patched), user_ctx);
    free(patched);
}

// Wrapper для обработчика command
static void light_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

static cJSON *light_node_channels_callback(void *user_ctx) {
    (void)user_ctx;
    return light_node_build_config_channels();
}

/**
 * @brief Инициализация интеграции light_node с node_framework
 */
esp_err_t light_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing light_node framework integration...");

    node_framework_config_t config = {
        .node_type = "light",
        .default_node_id = LIGHT_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = LIGHT_NODE_DEFAULT_GH_UID,
        .default_zone_uid = LIGHT_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = NULL,  // Нет актуаторов
        .command_handler_cb = NULL,
        .telemetry_cb = light_node_publish_telemetry_callback,
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", err, "Node framework initialization failed");
        return err;
    }

    esp_err_t cmd_err = node_command_handler_register("test_sensor", handle_test_sensor, NULL);
    if (cmd_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register test_sensor handler: %s", esp_err_to_name(cmd_err));
    }

    node_config_handler_set_channels_callback(light_node_channels_callback, NULL);

    ESP_LOGI(TAG, "light_node framework integration initialized successfully");
    return ESP_OK;
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void light_node_framework_register_mqtt_handlers(void) {
    ESP_LOGI(TAG, "Registering MQTT handlers through node_framework...");
    
    mqtt_manager_register_config_cb(light_node_config_handler_wrapper, NULL);
    mqtt_manager_register_command_cb(light_node_command_handler_wrapper, NULL);

    node_config_handler_set_mqtt_callbacks(
        light_node_config_handler_wrapper,
        light_node_command_handler_wrapper,
        NULL,
        NULL,
        LIGHT_NODE_DEFAULT_NODE_ID,
        LIGHT_NODE_DEFAULT_GH_UID,
        LIGHT_NODE_DEFAULT_ZONE_UID
    );
    
    ESP_LOGI(TAG, "MQTT handlers registered");
}
