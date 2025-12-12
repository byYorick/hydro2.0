/**
 * @file relay_node_framework_integration.c
 * @brief Интеграция relay_node с node_framework
 * 
 * Этот файл связывает relay_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "relay_node_framework_integration.h"
#include "node_framework.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_state_manager.h"
#include "relay_node_app.h"
#include "relay_node_defaults.h"
#include "relay_node_hw_map.h"
#include "relay_driver.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include <string.h>

static const char *TAG = "relay_node_fw";

// Forward declaration для callback safe_mode
static esp_err_t relay_node_disable_actuators_in_safe_mode(void *user_ctx);

// Реализация резолвера аппаратной карты для драйвера реле
bool relay_driver_resolve_hw_gpio(const char *channel_name, int *gpio_pin_out, bool *active_high_out, relay_type_t *relay_type_out) {
    if (channel_name == NULL || gpio_pin_out == NULL) {
        return false;
    }

    for (size_t i = 0; i < RELAY_NODE_HW_CHANNELS_COUNT; i++) {
        const relay_node_hw_channel_t *hw = &RELAY_NODE_HW_CHANNELS[i];
        if (strcmp(hw->channel_name, channel_name) == 0) {
            *gpio_pin_out = hw->gpio_pin;
            if (active_high_out) {
                *active_high_out = hw->active_high;
            }
            if (relay_type_out) {
                *relay_type_out = hw->relay_type;
            }
            ESP_LOGI(TAG, "Resolved GPIO for channel %s -> %d (active_high=%s, type=%s)",
                     channel_name, hw->gpio_pin,
                     hw->active_high ? "true" : "false",
                     hw->relay_type == RELAY_TYPE_NC ? "NC" : "NO");
            return true;
        }
    }

    ESP_LOGW(TAG, "No hardware mapping for channel %s", channel_name);
    return false;
}

// Callback для инициализации каналов из NodeConfig
static esp_err_t relay_node_init_channel_callback(
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

    // Инициализация реле
    // Примечание: relay_driver инициализируется через relay_driver_init_from_config()
    // после применения всех каналов, поэтому здесь только логируем
    if (strcmp(channel_type, "ACTUATOR") == 0) {
        cJSON *actuator_type = cJSON_GetObjectItem(channel_config, "actuator_type");
        if (actuator_type && cJSON_IsString(actuator_type)) {
            const char *act_type = actuator_type->valuestring;
            if (strcmp(act_type, "RELAY") == 0) {
                // GPIO теперь задаётся только в прошивке; наличие или отсутствие в конфиге не критично
                ESP_LOGI(TAG, "Relay channel %s acknowledged (GPIO resolved in firmware)", channel_name);
                return ESP_OK;
            }
        }
    }

    ESP_LOGW(TAG, "Unknown channel type: %s for channel %s", channel_type, channel_name);
    return ESP_ERR_NOT_SUPPORTED;
}

// Обработчик команды set_state с командным автоматом
// Состояния: ACCEPTED -> DONE/FAILED
static esp_err_t handle_set_state(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;

    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Извлекаем cmd_id из params
    cJSON *cmd_id_item = cJSON_GetObjectItem(params, "cmd_id");
    const char *cmd_id = NULL;
    if (cmd_id_item && cJSON_IsString(cmd_id_item)) {
        cmd_id = cmd_id_item->valuestring;
    }

    cJSON *state_item = cJSON_GetObjectItem(params, "state");
    int state = 0;
    if (cJSON_IsNumber(state_item)) {
        state = state_item->valueint;
    } else if (cJSON_IsBool(state_item)) {
        state = cJSON_IsTrue(state_item) ? 1 : 0;
    } else if (cJSON_IsString(state_item) && state_item->valuestring) {
        state = atoi(state_item->valuestring);
    } else {
        ESP_LOGW(TAG, "set_state invalid params: channel=%s, state json type=%d", channel, state_item ? state_item->type : -1);
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "Missing or invalid state",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    
    // Шаг 1: Отправляем ACCEPTED сразу при принятии команды
    if (cmd_id) {
        cJSON *accepted_response = node_command_handler_create_response(cmd_id, "ACCEPTED", NULL, NULL, NULL);
        if (accepted_response) {
            char *json_str = cJSON_PrintUnformatted(accepted_response);
            if (json_str) {
                mqtt_manager_publish_command_response(channel, json_str);
                free(json_str);
            }
            cJSON_Delete(accepted_response);
        }
    }
    
    relay_state_t relay_state = (state == 0) ? RELAY_STATE_OPEN : RELAY_STATE_CLOSED;

    // Шаг 2: Выполняем команду
    esp_err_t err = relay_driver_set_state(channel, relay_state);
    
    // Шаг 3: Отправляем финальный ответ DONE или FAILED
    const char *final_status;
    const char *error_code = NULL;
    const char *error_message = NULL;
    
    if (err != ESP_OK) {
        final_status = "FAILED";
        error_code = "relay_error";
        error_message = "Failed to set relay state";
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", err, error_message);
    } else {
        final_status = "DONE";
    }

    *response = node_command_handler_create_response(
        cmd_id,
        final_status,
        error_code,
        error_message,
        NULL
    );

    ESP_LOGI(TAG, "Relay %s set to state %d (%s)", channel, state, final_status);
    return err;
}

// Обработчик команды toggle
static esp_err_t handle_toggle(
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

    relay_state_t current_state;
    esp_err_t get_err = relay_driver_get_state(channel, &current_state);
    
    if (get_err != ESP_OK) {
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", get_err, "Relay channel not found");
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "relay_not_found",
            "Relay channel not found",
            NULL
        );
        return get_err;
    }

    relay_state_t new_state = (current_state == RELAY_STATE_OPEN) ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
    esp_err_t err = relay_driver_set_state(channel, new_state);
    
    if (err != ESP_OK) {
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", err, "Failed to toggle relay");
        *response = node_command_handler_create_response(
            NULL,
            "ERROR",
            "relay_error",
            "Failed to toggle relay",
            NULL
        );
        return err;
    }

    cJSON *extra = cJSON_CreateObject();
    cJSON_AddNumberToObject(extra, "state", new_state);
    *response = node_command_handler_create_response(
        NULL,
        "ACK",
        NULL,
        NULL,
        extra
    );
    cJSON_Delete(extra);

    ESP_LOGI(TAG, "Relay %s toggled to state %d", channel, new_state);
    return ESP_OK;
}

// Инициализация node_framework для relay_node
esp_err_t relay_node_framework_init(void) {
    ESP_LOGI(TAG, "Initializing node_framework for relay_node...");

    node_framework_config_t config = {
        .node_type = "relay",
        .default_node_id = RELAY_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = RELAY_NODE_DEFAULT_GH_UID,
        .default_zone_uid = RELAY_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = relay_node_init_channel_callback,
        .command_handler_cb = NULL,
        .telemetry_cb = NULL,  // Релейная нода не публикует телеметрию сенсоров
        .user_ctx = NULL
    };

    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", err, "Node framework initialization failed");
        return err;
    }

    // Регистрация обработчиков команд
    err = node_command_handler_register("set_state", handle_set_state, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register set_state handler: %s", esp_err_to_name(err));
    }

    err = node_command_handler_register("toggle", handle_toggle, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register toggle handler: %s", esp_err_to_name(err));
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(relay_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    ESP_LOGI(TAG, "node_framework initialized for relay_node");
    return ESP_OK;
}

// Wrapper для обработчика команд (C-совместимый)
static void relay_node_command_handler_wrapper(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t relay_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    
    // Отключаем все реле (устанавливаем в OPEN состояние)
    // Примечание: relay_driver не имеет функции emergency_stop, поэтому
    // нужно будет добавить или использовать другой механизм
    // Пока просто логируем
    ESP_LOGW(TAG, "Safe mode: all relays should be opened");
    return ESP_OK;
}

// Регистрация MQTT обработчиков через node_framework
void relay_node_framework_register_mqtt_handlers(void) {
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(node_config_handler_process, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(relay_node_command_handler_wrapper, NULL);
    
    // Регистрация MQTT callbacks в node_config_handler для config_apply_mqtt
    node_config_handler_set_mqtt_callbacks(
        node_config_handler_process,
        relay_node_command_handler_wrapper,
        NULL,
        NULL,
        RELAY_NODE_DEFAULT_NODE_ID,
        RELAY_NODE_DEFAULT_GH_UID,
        RELAY_NODE_DEFAULT_ZONE_UID
    );
}
