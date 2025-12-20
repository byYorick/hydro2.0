/**
 * @file ph_node_framework_integration.c
 * @brief Интеграция ph_node с node_framework
 * 
 * Этот файл связывает ph_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "ph_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "ph_node_app.h"
#include "ph_node_defaults.h"
#include "pump_driver.h"
#include "trema_ph.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include <string.h>
#include <strings.h>
#include <math.h>
#include <float.h>

static const char *TAG = "ph_node_fw";

// Forward declaration для callback safe_mode
static esp_err_t ph_node_disable_actuators_in_safe_mode(void *user_ctx);

// Callback для инициализации каналов из NodeConfig
static esp_err_t ph_node_init_channel_callback(
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

    // Инициализация насосов
    // Примечание: pump_driver инициализируется через pump_driver_init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcasecmp(actuator_type, "PUMP") == 0) {
        cJSON *pin_item = cJSON_GetObjectItem(channel_config, "pin");
        cJSON *gpio_item = cJSON_GetObjectItem(channel_config, "gpio");
        cJSON *pin_src = cJSON_IsNumber(pin_item) ? pin_item : (cJSON_IsNumber(gpio_item) ? gpio_item : NULL);
        if (pin_src) {
            int pin = pin_src->valueint;
            ESP_LOGI(TAG, "Pump channel %s configured on pin %d (will be initialized via pump_driver_init_from_config)",
                    channel_name, pin);
        } else {
            ESP_LOGI(TAG, "Pump channel %s configured (GPIO resolved in firmware)", channel_name);
        }
        return ESP_OK;
    }

    ESP_LOGW(TAG, "Unknown channel type: %s for channel %s", channel_type, channel_name);
    return ESP_ERR_NOT_SUPPORTED;
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
        // cmd_id будет добавлен автоматически в node_command_handler_process
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
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
            "FAILED",
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
            "FAILED",
            "pump_error",
            "Failed to run pump",
            NULL
        );
        return err;
    }

    // Успешный ответ - cmd_id будет добавлен автоматически
    *response = node_command_handler_create_response(
        NULL,
        "DONE",
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
            "FAILED",
            "pump_error",
            "Failed to stop pump",
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

    ESP_LOGI(TAG, "Pump %s stopped", channel);
    return ESP_OK;
}

// Обработчик команды calibrate для pH сенсора
static esp_err_t handle_calibrate_ph(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Проверяем, что команда для ph_sensor канала
    if (strcmp(channel, "ph_sensor") != 0) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_channel",
            "calibrate command only works for ph_sensor channel",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *stage_item = cJSON_GetObjectItem(params, "stage");
    // Поддержка обоих форматов: known_ph и ph_value (для обратной совместимости)
    cJSON *known_ph_item = cJSON_GetObjectItem(params, "known_ph");
    if (!known_ph_item || !cJSON_IsNumber(known_ph_item)) {
        known_ph_item = cJSON_GetObjectItem(params, "ph_value");  // Альтернативный формат
    }

    if (!stage_item || !cJSON_IsNumber(stage_item) || 
        !known_ph_item || !cJSON_IsNumber(known_ph_item)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_parameter",
            "Missing or invalid stage/known_ph/ph_value",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
    float known_ph = (float)cJSON_GetNumberValue(known_ph_item);

    // Валидация: stage должен быть 1 или 2
    if (stage < 1 || stage > 2) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_parameter",
            "stage must be 1 or 2",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    // Валидация: known_ph должен быть в разумном диапазоне (0-14)
    if (known_ph < 0.0f || known_ph > 14.0f || isnan(known_ph) || isinf(known_ph)) {
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "invalid_parameter",
            "known_ph must be between 0.0 and 14.0",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    // Выполнение калибровки
    if (trema_ph_calibrate(stage, known_ph)) {
        *response = node_command_handler_create_response(
            NULL,
            "DONE",
            NULL,
            NULL,
            NULL
        );
        ESP_LOGI(TAG, "pH sensor calibrated: stage %d, known_pH %.2f", stage, known_ph);
        return ESP_OK;
    } else {
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "ph_sensor", ESP_FAIL, "pH sensor calibration failed");
        *response = node_command_handler_create_response(
            NULL,
            "FAILED",
            "calibration_failed",
            "Failed to calibrate pH sensor",
            NULL
        );
        return ESP_FAIL;
    }
}

// Публикация телеметрии через node_framework
static esp_err_t ph_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    // Инициализация сенсора, если не инициализирован
    if (!trema_ph_is_initialized() && i2c_bus_is_initialized()) {
        if (trema_ph_init()) {
            ESP_LOGI(TAG, "Trema pH sensor initialized");
        }
    }

    // Чтение значения pH
    float ph_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    bool is_stable = true;
    int32_t raw_value = 0;

    if (trema_ph_is_initialized()) {
        read_success = trema_ph_read(&ph_value);
        using_stub = trema_ph_is_using_stub_values();
        
        if (!read_success || isnan(ph_value)) {
            ESP_LOGW(TAG, "Failed to read pH value, using stub");
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "ph_sensor", ESP_ERR_INVALID_RESPONSE, "Failed to read pH sensor value");
            ph_value = 6.5f;  // Нейтральное значение
            using_stub = true;
        } else {
            raw_value = (int32_t)(ph_value * 1000);  // Raw value в тысячных
            is_stable = trema_ph_get_stability();
        }
    } else {
        ESP_LOGW(TAG, "pH sensor not initialized, using stub value");
        node_state_manager_report_error(ERROR_LEVEL_WARNING, "ph_sensor", ESP_ERR_INVALID_STATE, "pH sensor not initialized");
        ph_value = 6.5f;
        using_stub = true;
    }

    // Публикация через node_telemetry_engine
    esp_err_t err = node_telemetry_publish_sensor(
        "ph_sensor",
        METRIC_TYPE_PH,
        ph_value,
        "pH",
        raw_value,
        using_stub,
        is_stable
    );

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish telemetry: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish pH telemetry");
    }

    return err;
}

// Инициализация node_framework для ph_node
esp_err_t ph_node_framework_init(void) {
    ESP_LOGI(TAG, "Initializing node_framework for ph_node...");

    // Конфигурация фреймворка
    node_framework_config_t config = {
        .node_type = "ph",
        .default_node_id = PH_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = PH_NODE_DEFAULT_GH_UID,
        .default_zone_uid = PH_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = ph_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = ph_node_publish_telemetry_callback,
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
        ESP_LOGW(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
    }

    err = node_command_handler_register("stop_pump", handle_stop_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register stop_pump handler: %s", esp_err_to_name(err));
    }

    err = node_command_handler_register("calibrate", handle_calibrate_ph, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register calibrate handler: %s", esp_err_to_name(err));
    }

    err = node_command_handler_register("calibrate_ph", handle_calibrate_ph, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register calibrate_ph handler: %s", esp_err_to_name(err));
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(ph_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    ESP_LOGI(TAG, "node_framework initialized for ph_node");
    return ESP_OK;
}

// Wrapper для обработчика команд (C-совместимый)
static void ph_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t ph_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    return pump_driver_emergency_stop();
}

// Регистрация MQTT обработчиков через node_framework
void ph_node_framework_register_mqtt_handlers(void) {
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(node_config_handler_process, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(ph_node_command_handler_wrapper, NULL);
    
    // Регистрация MQTT callbacks в node_config_handler для config_apply_mqtt
    // Это позволяет автоматически переподключать MQTT при изменении конфига
    node_config_handler_set_mqtt_callbacks(
        node_config_handler_process,
        ph_node_command_handler_wrapper,
        NULL,  // connection_cb - можно добавить позже если нужно
        NULL,
        PH_NODE_DEFAULT_NODE_ID,
        PH_NODE_DEFAULT_GH_UID,
        PH_NODE_DEFAULT_ZONE_UID
    );
}
