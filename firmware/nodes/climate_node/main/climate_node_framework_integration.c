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
#include <stdlib.h>
#include <stdint.h>
#include <strings.h>
#include <math.h>
#include <float.h>

static const char *TAG = "climate_node_fw";

// Forward declaration для callback safe_mode
static esp_err_t climate_node_disable_actuators_in_safe_mode(void *user_ctx);

static bool climate_node_parse_state(const cJSON *state_item, bool *state_out) {
    if (!state_item || !state_out) {
        return false;
    }

    if (cJSON_IsBool(state_item)) {
        *state_out = cJSON_IsTrue(state_item);
        return true;
    }

    if (cJSON_IsNumber(state_item)) {
        *state_out = (state_item->valueint != 0);
        return true;
    }

    if (cJSON_IsString(state_item) && state_item->valuestring) {
        const char *value = state_item->valuestring;
        if (strcasecmp(value, "open") == 0 ||
            strcasecmp(value, "off") == 0 ||
            strcasecmp(value, "false") == 0) {
            *state_out = false;
            return true;
        }
        if (strcasecmp(value, "closed") == 0 ||
            strcasecmp(value, "on") == 0 ||
            strcasecmp(value, "true") == 0) {
            *state_out = true;
            return true;
        }
        char *endptr = NULL;
        long parsed = strtol(value, &endptr, 10);
        if (endptr && *endptr == '\0') {
            *state_out = (parsed != 0);
            return true;
        }
    }

    return false;
}

static bool climate_node_channel_matches(const cJSON *entry, const char *name) {
    if (entry == NULL || name == NULL || !cJSON_IsObject(entry)) {
        return false;
    }

    const cJSON *name_item = cJSON_GetObjectItem(entry, "name");
    if (cJSON_IsString(name_item) && name_item->valuestring &&
        strcmp(name_item->valuestring, name) == 0) {
        return true;
    }

    const cJSON *channel_item = cJSON_GetObjectItem(entry, "channel");
    if (cJSON_IsString(channel_item) && channel_item->valuestring &&
        strcmp(channel_item->valuestring, name) == 0) {
        return true;
    }

    return false;
}

static bool climate_node_has_channel(const cJSON *channels, const char *name) {
    if (channels == NULL || name == NULL || !cJSON_IsArray(channels)) {
        return false;
    }

    const int count = cJSON_GetArraySize(channels);
    for (int i = 0; i < count; i++) {
        const cJSON *entry = cJSON_GetArrayItem(channels, i);
        if (climate_node_channel_matches(entry, name)) {
            return true;
        }
    }

    return false;
}

static cJSON *climate_node_build_sensor_entry(
    const char *name,
    const char *metric,
    uint32_t poll_interval_ms,
    const char *unit,
    int precision
) {
    cJSON *entry = cJSON_CreateObject();
    if (entry == NULL) {
        return NULL;
    }

    cJSON_AddStringToObject(entry, "name", name);
    cJSON_AddStringToObject(entry, "channel", name);
    cJSON_AddStringToObject(entry, "type", "SENSOR");
    cJSON_AddStringToObject(entry, "metric", metric);
    cJSON_AddNumberToObject(entry, "poll_interval_ms", (double)poll_interval_ms);
    cJSON_AddStringToObject(entry, "unit", unit);
    cJSON_AddNumberToObject(entry, "precision", (double)precision);

    return entry;
}

static bool climate_node_ensure_sensor_channel(
    cJSON *channels,
    const char *name,
    const char *metric,
    uint32_t poll_interval_ms,
    const char *unit,
    int precision,
    bool *changed
) {
    if (climate_node_has_channel(channels, name)) {
        return true;
    }

    cJSON *entry = climate_node_build_sensor_entry(name, metric, poll_interval_ms, unit, precision);
    if (entry == NULL) {
        return false;
    }

    cJSON_AddItemToArray(channels, entry);
    if (changed != NULL) {
        *changed = true;
    }
    return true;
}

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
    const char *actuator_type = channel_type;

    if (strcasecmp(channel_type, "ACTUATOR") == 0) {
        cJSON *actuator_item = cJSON_GetObjectItem(channel_config, "actuator_type");
        if (!cJSON_IsString(actuator_item)) {
            ESP_LOGW(TAG, "Channel %s: missing or invalid actuator_type", channel_name);
            return ESP_ERR_INVALID_ARG;
        }
        actuator_type = actuator_item->valuestring;
    }

    // Инициализация реле и PWM
    // Примечание: relay_driver и pwm_driver инициализируются через init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcasecmp(actuator_type, "RELAY") == 0 ||
        strcasecmp(actuator_type, "VALVE") == 0 ||
        strcasecmp(actuator_type, "PWM") == 0 ||
        strcasecmp(actuator_type, "FAN") == 0 ||
        strcasecmp(actuator_type, "HEATER") == 0 ||
        strcasecmp(actuator_type, "LED") == 0) {
        cJSON *pin_item = cJSON_GetObjectItem(channel_config, "pin");
        cJSON *gpio_item = cJSON_GetObjectItem(channel_config, "gpio");
        cJSON *pin_src = cJSON_IsNumber(pin_item) ? pin_item : (cJSON_IsNumber(gpio_item) ? gpio_item : NULL);
        if (pin_src) {
            int pin = pin_src->valueint;
            ESP_LOGI(TAG, "%s channel %s configured on pin %d (will be initialized via driver_init_from_config)",
                    actuator_type, channel_name, pin);
        } else {
            ESP_LOGI(TAG, "%s channel %s configured (GPIO resolved in firmware)", actuator_type, channel_name);
        }
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
    bool state = false;
    if (!climate_node_parse_state(state_item, &state)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_params",
            "Missing or invalid state",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    relay_state_t relay_state = state ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
    
    esp_err_t err = relay_driver_set_state(channel, relay_state);
    if (err != ESP_OK) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "relay_driver_failed",
            "Failed to set relay state",
            NULL
        );
        return err;
    }

    *response = node_command_handler_create_response(
        NULL,
        "DONE",
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
            "FAILED",
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
            "FAILED",
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
            "FAILED",
            "pwm_failed",
            "Failed to set PWM duty",
            NULL
        );
        return err;
    }

    *response = node_command_handler_create_response(
        NULL,
        "DONE",
        NULL,
        NULL,
        NULL
    );

    ESP_LOGI(TAG, "PWM %s set to %d (%.1f%%)", channel, pwm_value, duty_percent);
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

    if (strcmp(channel, "temperature") == 0 || strcmp(channel, "humidity") == 0) {
        if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "i2c_not_initialized",
                "I2C bus 1 is not initialized",
                NULL
            );
            return ESP_ERR_INVALID_STATE;
        }

        sht3x_reading_t reading = {0};
        esp_err_t err = sht3x_read(&reading);
        if (err == ESP_ERR_INVALID_STATE) {
            sht3x_config_t sht_config = {
                .i2c_address = 0x44,
                .i2c_bus = I2C_BUS_1,
            };
            esp_err_t init_err = sht3x_init(&sht_config);
            if (init_err != ESP_OK) {
                *response = node_command_handler_create_response(
                    NULL,
                    "FAILED",
                    "sensor_init_failed",
                    "Failed to initialize SHT3x sensor",
                    NULL
                );
                return init_err;
            }
            err = sht3x_read(&reading);
        }

        if (err != ESP_OK || !reading.valid) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "read_failed",
                "Failed to read SHT3x sensor",
                NULL
            );
            return err != ESP_OK ? err : ESP_FAIL;
        }

        const float value = (strcmp(channel, "temperature") == 0) ? reading.temperature : reading.humidity;
        if (!isfinite(value)) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "invalid_value",
                "Sensor returned invalid value",
                NULL
            );
            return ESP_FAIL;
        }

        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "value", value);
            if (strcmp(channel, "temperature") == 0) {
                cJSON_AddStringToObject(extra, "unit", "°C");
                cJSON_AddStringToObject(extra, "metric_type", "TEMPERATURE");
            } else {
                cJSON_AddStringToObject(extra, "unit", "%");
                cJSON_AddStringToObject(extra, "metric_type", "HUMIDITY");
            }
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

    if (strcmp(channel, "co2") == 0) {
        if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "i2c_not_initialized",
                "I2C bus 0 is not initialized",
                NULL
            );
            return ESP_ERR_INVALID_STATE;
        }

        ccs811_reading_t reading = {0};
        esp_err_t err = ccs811_read(&reading);
        if (err == ESP_ERR_NOT_FINISHED) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "sensor_not_ready",
                "CO2 sensor data not ready",
                NULL
            );
            return err;
        }

        if (err != ESP_OK || !reading.valid) {
            *response = node_command_handler_create_response(
                NULL,
                "FAILED",
                "sensor_stub",
                "CO2 sensor returned invalid or stub values",
                NULL
            );
            return err != ESP_OK ? err : ESP_FAIL;
        }

        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "value", (double)reading.co2_ppm);
            cJSON_AddStringToObject(extra, "unit", "ppm");
            cJSON_AddStringToObject(extra, "metric_type", "CO2");
            cJSON_AddBoolToObject(extra, "stable", true);
            if (reading.tvoc_ppb > 0) {
                cJSON_AddNumberToObject(extra, "tvoc_ppb", (double)reading.tvoc_ppb);
            }
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

    *response = node_command_handler_create_response(
        NULL,
        "FAILED",
        "invalid_channel",
        "Unknown sensor channel",
        NULL
    );
    return ESP_ERR_INVALID_ARG;
}

// Публикация телеметрии через node_framework
esp_err_t climate_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    // Чтение температуры и влажности (SHT3x)
    sht3x_reading_t sht_reading = {0};
    esp_err_t sht_err = sht3x_read(&sht_reading);
    
    if (sht_err == ESP_OK && sht_reading.valid) {
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
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish temperature telemetry");
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
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish humidity telemetry");
        }
    } else {
        esp_err_t report_err = (sht_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : sht_err;
        ESP_LOGW(TAG, "Failed to read SHT3x: %s", esp_err_to_name(report_err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "sht3x", report_err, "Failed to read SHT3x sensor");
        
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
    
    bool co2_stub = (ccs_err != ESP_OK) || !ccs_reading.valid;
    float co2_value = (float)ccs_reading.co2_ppm;

    if (co2_stub) {
        esp_err_t report_err = (ccs_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : ccs_err;
        ESP_LOGW(TAG, "Failed to read CCS811 (will publish stub): %s", esp_err_to_name(report_err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "ccs811", report_err, "Failed to read CCS811 sensor");
    }

    esp_err_t err = node_telemetry_publish_sensor(
        "co2",
        METRIC_TYPE_CUSTOM,  // CO₂ пока нет в enum, используем CUSTOM
        co2_value,
        "ppm",
        ccs_reading.co2_ppm,
        co2_stub,
        !co2_stub
    );
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish CO2: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish CO2 telemetry");
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

    if (data == NULL || data_len <= 0) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (config == NULL) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    bool changed = false;
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels == NULL || !cJSON_IsArray(channels)) {
        if (channels) {
            cJSON_DeleteItemFromObject(config, "channels");
        }
        channels = cJSON_CreateArray();
        if (channels == NULL) {
            cJSON_Delete(config);
            node_config_handler_process(topic, data, data_len, user_ctx);
            return;
        }
        cJSON_AddItemToObject(config, "channels", channels);
        changed = true;
    }

    if (!climate_node_ensure_sensor_channel(channels, "temperature", "TEMPERATURE", 5000, "°C", 1, &changed)) {
        cJSON_Delete(config);
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }
    if (!climate_node_ensure_sensor_channel(channels, "humidity", "HUMIDITY", 5000, "%", 1, &changed)) {
        cJSON_Delete(config);
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }
    if (!climate_node_ensure_sensor_channel(channels, "co2", "CO2", 10000, "ppm", 0, &changed)) {
        cJSON_Delete(config);
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    if (!changed) {
        cJSON_Delete(config);
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    char *patched = cJSON_PrintUnformatted(config);
    cJSON_Delete(config);
    if (patched == NULL) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    ESP_LOGI(TAG, "Patching NodeConfig with climate sensor channels");
    node_config_handler_process(topic, patched, (int)strlen(patched), user_ctx);
    free(patched);
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
    ESP_LOGI(TAG, "Init framework integration");

    // ВАЖНО: Используем статические строки для node_type, чтобы указатели оставались валидными
    static const char node_type[] = "climate";
    
    // Инициализация node_framework
    node_framework_config_t config = {0};
    config.node_type = node_type;
    config.default_node_id = NULL;  // Будет загружен из конфига
    config.default_gh_uid = NULL;
    config.default_zone_uid = NULL;
    config.channel_init_cb = climate_node_init_channel_callback;
    config.command_handler_cb = NULL;  // Регистрация через API
    config.telemetry_cb = climate_node_publish_telemetry_callback;
    config.user_ctx = NULL;

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

    err = node_command_handler_register("test_sensor", handle_test_sensor, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register test_sensor handler: %s", esp_err_to_name(err));
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
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
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
