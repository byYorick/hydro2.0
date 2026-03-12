/**
 * @file light_node_framework_integration.c
 * @brief Интеграция light_node с node_framework
 */

#include "light_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "trema_light.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include <math.h>

static const char *TAG = "light_node_fw";

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
        }
    } else {
        ESP_LOGW(TAG, "Failed to read light sensor: success=%d, lux=%.0f", read_success, light_lux);
        
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

// Wrapper для обработчика config
static void light_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    (void)user_ctx;
    node_config_handler_process(topic, data, data_len, user_ctx);
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

/**
 * @brief Инициализация интеграции light_node с node_framework
 */
esp_err_t light_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing light_node framework integration...");

    node_framework_config_t config = {
        .node_type = "light",
        .default_node_id = NULL,
        .default_gh_uid = NULL,
        .default_zone_uid = NULL,
        .channel_init_cb = NULL,  // Нет актуаторов
        .command_handler_cb = NULL,
        .telemetry_cb = light_node_publish_telemetry_callback,
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        return err;
    }

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
    
    ESP_LOGI(TAG, "MQTT handlers registered");
}

