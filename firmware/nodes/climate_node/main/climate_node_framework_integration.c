/**
 * @file climate_node_framework_integration.c
 * @brief Интеграция climate_node с node_framework
 * 
 * Этот файл связывает climate_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "climate_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "climate_node_app.h"
#include "relay_driver.h"
#include "pwm_driver.h"
#include "sht3x.h"
#include "ccs811.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "cJSON.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>
#include <math.h>
#include <float.h>

static const char *TAG = "climate_node_fw";

// Forward declaration для callback safe_mode
static esp_err_t climate_node_disable_actuators_in_safe_mode(void *user_ctx);

// Callback для инициализации каналов из NodeConfig
static esp_err_t climate_node_init_channel_callback(
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

    // Инициализация реле и PWM
    // Примечание: relay_driver и pwm_driver инициализируются через init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcmp(channel_type, "relay") == 0 || strcmp(channel_type, "pwm") == 0) {
        cJSON *pin_item = cJSON_GetObjectItem(channel_config, "pin");
        if (!cJSON_IsNumber(pin_item)) {
            ESP_LOGW(TAG, "Channel %s: missing or invalid pin", channel_name);
            return ESP_ERR_INVALID_ARG;
        }

        int pin = pin_item->valueint;
        ESP_LOGI(TAG, "%s channel %s configured on pin %d (will be initialized via driver_init_from_config)", 
                channel_type, channel_name, pin);
        return ESP_OK;
    }

    return ESP_OK;
}

// Обработчик команды set_relay
static esp_err_t handle_set_relay(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *state_item = cJSON_GetObjectItem(params, "state");
    if (!cJSON_IsBool(state_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_params",
            "Missing or invalid state (must be boolean)",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    bool state = cJSON_IsTrue(state_item);
    relay_state_t relay_state = state ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
    
    esp_err_t err = relay_driver_set_state(channel, relay_state);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "relay_driver_failed",
            "Failed to set relay state",
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

    ESP_LOGI(TAG, "Relay %s set to %s", channel, state ? "ON" : "OFF");
    return ESP_OK;
}

// Обработчик команды set_pwm
static esp_err_t handle_set_pwm(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *value_item = cJSON_GetObjectItem(params, "value");
    if (!cJSON_IsNumber(value_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_params",
            "Missing or invalid value (must be number)",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    int pwm_value = (int)cJSON_GetNumberValue(value_item);
    float duty_percent;
    
    // Если значение <= 100, считаем это процентом, иначе 0-255
    if (pwm_value <= 100) {
        duty_percent = (float)pwm_value;
    } else {
        if (pwm_value < 0) {
            pwm_value = 0;
        }
        if (pwm_value > 255) {
            pwm_value = 255;
        }
        duty_percent = ((float)pwm_value / 255.0f) * 100.0f;
    }

    if (duty_percent < 0.0f || duty_percent > 100.0f) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "invalid_params",
            "PWM value must be between 0 and 100 (or 0-255)",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = pwm_driver_set_duty_percent(channel, duty_percent);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "pwm_failed",
            "Failed to set PWM duty",
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

    ESP_LOGI(TAG, "PWM %s set to %d (%.1f%%)", channel, pwm_value, duty_percent);
    return ESP_OK;
}

// Публикация телеметрии через node_framework
esp_err_t climate_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    // Чтение температуры и влажности (SHT3x)
    sht3x_reading_t sht_reading = {0};
    esp_err_t sht_err = sht3x_read(&sht_reading);
    
    ESP_LOGD(TAG, "SHT3x read attempt: err=%s, valid=%d, T=%.1f°C, H=%.1f%%", 
            esp_err_to_name(sht_err), sht_reading.valid, 
            sht_reading.temperature, sht_reading.humidity);
    
    if (sht_err == ESP_OK && sht_reading.valid) {
        ESP_LOGI(TAG, "SHT3x: T=%.1f°C, H=%.1f%%", 
                sht_reading.temperature, sht_reading.humidity);
        // Публикация температуры
        esp_err_t err = node_telemetry_publish_sensor(
            "temperature",
            METRIC_TYPE_TEMPERATURE,
            sht_reading.temperature,
            "°C",
            0,  // raw value не используется
            false,  // not stub
            true     // is_stable
        );
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish temperature: %s", esp_err_to_name(err));
        }

        // Публикация влажности
        err = node_telemetry_publish_sensor(
            "humidity",
            METRIC_TYPE_HUMIDITY,
            sht_reading.humidity,
            "%",
            0,  // raw value не используется
            false,  // not stub
            true     // is_stable
        );
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish humidity: %s", esp_err_to_name(err));
        }
    } else {
        esp_err_t report_err = (sht_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : sht_err;
        ESP_LOGW(TAG, "Failed to read SHT3x: %s", esp_err_to_name(report_err));
        
        // Публикация ошибок
        node_telemetry_publish_sensor(
            "temperature",
            METRIC_TYPE_TEMPERATURE,
            NAN,
            "°C",
            0,
            true,  // stub (ошибка)
            false
        );
        node_telemetry_publish_sensor(
            "humidity",
            METRIC_TYPE_HUMIDITY,
            NAN,
            "%",
            0,
            true,  // stub (ошибка)
            false
        );
    }

    // Чтение CO₂ (CCS811)
    ccs811_reading_t ccs_reading = {0};
    esp_err_t ccs_err = ccs811_read(&ccs_reading);
    
    if (ccs_err == ESP_OK && ccs_reading.valid) {
        esp_err_t err = node_telemetry_publish_sensor(
            "co2",
            METRIC_TYPE_CUSTOM,  // CO₂ пока нет в enum, используем CUSTOM
            (float)ccs_reading.co2_ppm,
            "ppm",
            ccs_reading.co2_ppm,
            false,  // not stub
            true     // is_stable
        );
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish CO2: %s", esp_err_to_name(err));
        }
    } else {
        esp_err_t report_err = (ccs_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : ccs_err;
        ESP_LOGW(TAG, "Failed to read CCS811: %s", esp_err_to_name(report_err));
        
        // Публикация ошибки
        node_telemetry_publish_sensor(
            "co2",
            METRIC_TYPE_CUSTOM,
            NAN,
            "ppm",
            0,
            true,  // stub (ошибка)
            false
        );
    }

    return ESP_OK;
}

// Wrapper для обработчика config (C-совместимый)
static void climate_node_config_handler_wrapper(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    (void)user_ctx;
    node_config_handler_process(topic, data, data_len, user_ctx);
}

// Wrapper для обработчика command (C-совместимый)
static void climate_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

/**
 * @brief Инициализация интеграции climate_node с node_framework
 */
esp_err_t climate_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing climate_node framework integration...");

    // Инициализация node_framework
    node_framework_config_t config = {
        .node_type = "climate",
        .default_node_id = NULL,  // Будет загружен из конфига
        .default_gh_uid = NULL,
        .default_zone_uid = NULL,
        .channel_init_cb = climate_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = climate_node_publish_telemetry_callback,
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация обработчиков команд
    err = node_command_handler_register("set_relay", handle_set_relay, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register set_relay handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("set_pwm", handle_set_pwm, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register set_pwm handler: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(climate_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    ESP_LOGI(TAG, "climate_node framework integration initialized successfully");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t climate_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    
    // Отключаем все реле и PWM через конфиг
    char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err == ESP_OK) {
        cJSON *config = cJSON_Parse(config_json);
        if (config) {
            cJSON *channels = cJSON_GetObjectItem(config, "channels");
            if (channels && cJSON_IsArray(channels)) {
                int channel_count = cJSON_GetArraySize(channels);
                for (int i = 0; i < channel_count; i++) {
                    cJSON *ch = cJSON_GetArrayItem(channels, i);
                    if (ch && cJSON_IsObject(ch)) {
                        cJSON *name = cJSON_GetObjectItem(ch, "name");
                        cJSON *type = cJSON_GetObjectItem(ch, "type");
                        if (cJSON_IsString(name) && cJSON_IsString(type)) {
                            const char *channel_name = name->valuestring;
                            const char *channel_type = type->valuestring;
                            
                            // Отключаем реле
                            if (strcmp(channel_type, "relay") == 0 || 
                                strcmp(channel_type, "RELAY") == 0) {
                                relay_driver_set_state(channel_name, RELAY_STATE_OPEN);
                            }
                            
                            // Отключаем PWM (устанавливаем duty в 0%)
                            if (strcmp(channel_type, "pwm") == 0 || 
                                strcmp(channel_type, "PWM") == 0) {
                                pwm_driver_set_duty_percent(channel_name, 0.0f);
                            }
                        }
                    }
                }
            }
            cJSON_Delete(config);
        }
    }
    
    return ESP_OK;
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 * 
 * mqtt_client - это алиас для mqtt_manager, поэтому используем mqtt_manager API
 */
void climate_node_framework_register_mqtt_handlers(void) {
    ESP_LOGI(TAG, "Registering MQTT handlers through node_framework...");
    
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(climate_node_config_handler_wrapper, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(climate_node_command_handler_wrapper, NULL);
    
    ESP_LOGI(TAG, "MQTT handlers registered");
}

