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
#include "freertos/FreeRTOS.h"
#include "freertos/timers.h"
#include "cJSON.h"
#include <string.h>

static const char *TAG = "relay_node_fw";

#define RELAY_NODE_MAX_AUTO_OFF_CHANNELS 16
#define RELAY_NODE_MAX_CHANNEL_NAME_LEN 64
#define RELAY_NODE_MAX_CMD_ID_LEN 64
#define RELAY_NODE_MAX_AUTO_OFF_DURATION_MS 300000U

typedef struct {
    char channel_name[RELAY_NODE_MAX_CHANNEL_NAME_LEN];
    char cmd_id[RELAY_NODE_MAX_CMD_ID_LEN];
    TimerHandle_t timer;
    bool in_use;
} relay_node_auto_off_entry_t;

static relay_node_auto_off_entry_t s_auto_off_entries[RELAY_NODE_MAX_AUTO_OFF_CHANNELS] = {0};

// Forward declaration для callback safe_mode
static esp_err_t relay_node_disable_actuators_in_safe_mode(void *user_ctx);
static cJSON *relay_node_channels_callback(void *user_ctx);
static void relay_node_build_error_details(
    esp_err_t err,
    const char *channel,
    int requested_state,
    const char *action,
    const char **error_code_out,
    const char **error_message_out,
    cJSON **extra_out
);

static void relay_node_auto_off_timer_cb(TimerHandle_t timer) {
    relay_node_auto_off_entry_t *entry = (relay_node_auto_off_entry_t *) pvTimerGetTimerID(timer);
    if (!entry || !entry->channel_name[0]) {
        return;
    }

    esp_err_t err = relay_driver_set_state(entry->channel_name, RELAY_STATE_OPEN);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Auto-off failed for channel %s: %s",
                 entry->channel_name, esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "Auto-off: relay %s opened", entry->channel_name);
    }

    if (entry->cmd_id[0]) {
        cJSON *done_response = node_command_handler_create_response(
            entry->cmd_id,
            "DONE",
            NULL,
            NULL,
            NULL
        );
        if (done_response) {
            char *json_str = cJSON_PrintUnformatted(done_response);
            if (json_str) {
                mqtt_manager_publish_command_response(entry->channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(done_response);
        }
        node_command_handler_cache_final_status(entry->cmd_id, entry->channel_name, "DONE");
        entry->cmd_id[0] = '\0';
    }
}

static relay_node_auto_off_entry_t *relay_node_get_auto_off_entry(const char *channel, bool create) {
    if (!channel || !channel[0]) {
        return NULL;
    }

    for (size_t i = 0; i < RELAY_NODE_MAX_AUTO_OFF_CHANNELS; i++) {
        if (s_auto_off_entries[i].in_use &&
            strcmp(s_auto_off_entries[i].channel_name, channel) == 0) {
            return &s_auto_off_entries[i];
        }
    }

    if (!create) {
        return NULL;
    }

    for (size_t i = 0; i < RELAY_NODE_MAX_AUTO_OFF_CHANNELS; i++) {
        if (!s_auto_off_entries[i].in_use) {
            relay_node_auto_off_entry_t *entry = &s_auto_off_entries[i];
            entry->in_use = true;
            strncpy(entry->channel_name, channel, sizeof(entry->channel_name) - 1);
            entry->channel_name[sizeof(entry->channel_name) - 1] = '\0';
            return entry;
        }
    }

    ESP_LOGW(TAG, "Auto-off table full, cannot schedule for channel %s", channel);
    return NULL;
}

static void relay_node_schedule_auto_off(const char *channel, const char *cmd_id, uint32_t duration_ms) {
    relay_node_auto_off_entry_t *entry = relay_node_get_auto_off_entry(channel, true);
    if (!entry) {
        return;
    }

    if (cmd_id && cmd_id[0]) {
        strncpy(entry->cmd_id, cmd_id, sizeof(entry->cmd_id) - 1);
        entry->cmd_id[sizeof(entry->cmd_id) - 1] = '\0';
    } else {
        entry->cmd_id[0] = '\0';
    }

    if (!entry->timer) {
        entry->timer = xTimerCreate("relay_off",
                                    pdMS_TO_TICKS(1000),
                                    pdFALSE,
                                    entry,
                                    relay_node_auto_off_timer_cb);
        if (!entry->timer) {
            ESP_LOGW(TAG, "Failed to create auto-off timer for channel %s", channel);
            return;
        }
    }

    if (xTimerChangePeriod(entry->timer, pdMS_TO_TICKS(duration_ms), 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to set auto-off timer for channel %s", channel);
        return;
    }

    if (xTimerStart(entry->timer, 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to start auto-off timer for channel %s", channel);
    }
}

static void relay_node_cancel_auto_off(const char *channel, bool clear_cmd_id) {
    relay_node_auto_off_entry_t *entry = relay_node_get_auto_off_entry(channel, false);
    if (!entry || !entry->timer) {
        return;
    }

    xTimerStop(entry->timer, 0);
    if (clear_cmd_id) {
        entry->cmd_id[0] = '\0';
    }
}

static cJSON *relay_node_copy_channels_from_config(void) {
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];

    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        return NULL;
    }

    cJSON *config = cJSON_Parse(config_json);
    if (!config) {
        return NULL;
    }

    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (!channels || !cJSON_IsArray(channels) || cJSON_GetArraySize(channels) == 0) {
        cJSON_Delete(config);
        return NULL;
    }

    cJSON *dup = cJSON_Duplicate(channels, 1);
    cJSON_Delete(config);
    return dup;
}

static cJSON *relay_node_build_channels_from_hw_map(void) {
    cJSON *channels = cJSON_CreateArray();
    if (!channels) {
        return NULL;
    }

    for (size_t i = 0; i < RELAY_NODE_HW_CHANNELS_COUNT; i++) {
        const relay_node_hw_channel_t *hw = &RELAY_NODE_HW_CHANNELS[i];
        if (!hw->channel_name) {
            continue;
        }

        cJSON *entry = cJSON_CreateObject();
        if (!entry) {
            cJSON_Delete(channels);
            return NULL;
        }

        cJSON_AddStringToObject(entry, "name", hw->channel_name);
        cJSON_AddStringToObject(entry, "channel", hw->channel_name);
        cJSON_AddStringToObject(entry, "type", "ACTUATOR");
        cJSON_AddStringToObject(entry, "actuator_type", "RELAY");
        cJSON_AddStringToObject(entry, "metric", "RELAY");
        cJSON_AddBoolToObject(entry, "active_high", hw->active_high);
        cJSON_AddStringToObject(entry, "relay_type", hw->relay_type == RELAY_TYPE_NC ? "NC" : "NO");
        cJSON_AddItemToArray(channels, entry);
    }

    return channels;
}

static cJSON *relay_node_channels_callback(void *user_ctx) {
    (void)user_ctx;

    cJSON *channels = relay_node_copy_channels_from_config();
    if (channels) {
        return channels;
    }

    return relay_node_build_channels_from_hw_map();
}

static void relay_node_build_error_details(
    esp_err_t err,
    const char *channel,
    int requested_state,
    const char *action,
    const char **error_code_out,
    const char **error_message_out,
    cJSON **extra_out
) {
    const char *error_code = "relay_gpio_error";
    const char *error_message = "Relay GPIO error";

    switch (err) {
        case ESP_ERR_INVALID_STATE:
            error_code = "relay_not_initialized";
            error_message = "Relay driver not initialized";
            break;
        case ESP_ERR_INVALID_ARG:
            error_code = "relay_invalid_channel";
            error_message = "Invalid relay channel";
            break;
        case ESP_ERR_NOT_FOUND:
            error_code = "relay_channel_not_found";
            error_message = "Relay channel not found";
            break;
        case ESP_ERR_TIMEOUT:
            error_code = "relay_mutex_timeout";
            error_message = "Relay command timeout";
            break;
        default:
            break;
    }

    if (error_code_out) {
        *error_code_out = error_code;
    }
    if (error_message_out) {
        *error_message_out = error_message;
    }

    if (extra_out) {
        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            if (channel) {
                cJSON_AddStringToObject(extra, "channel", channel);
            }
            cJSON_AddStringToObject(extra, "action", action ? action : "set_state");
            cJSON_AddNumberToObject(extra, "requested_state", requested_state);
            cJSON_AddStringToObject(extra, "esp_err", esp_err_to_name(err));
        }
        *extra_out = extra;
    }
}

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

    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    uint32_t duration_ms = 0;
    if (cJSON_IsNumber(duration_item)) {
        duration_ms = (uint32_t) cJSON_GetNumberValue(duration_item);
    } else if (cJSON_IsString(duration_item) && duration_item->valuestring) {
        duration_ms = (uint32_t) atoi(duration_item->valuestring);
    }

    if (duration_ms > RELAY_NODE_MAX_AUTO_OFF_DURATION_MS) {
        duration_ms = RELAY_NODE_MAX_AUTO_OFF_DURATION_MS;
    }
    
    bool use_delayed_done = (state == 1 && duration_ms > 0);

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
    cJSON *error_details = NULL;
    
    if (err != ESP_OK) {
        final_status = "FAILED";
        relay_node_build_error_details(
            err,
            channel,
            state,
            "set_state",
            &error_code,
            &error_message,
            &error_details
        );
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", err, error_message);
        relay_node_cancel_auto_off(channel, true);
    } else {
        if (use_delayed_done) {
            final_status = "ACCEPTED";
            relay_node_schedule_auto_off(channel, cmd_id, duration_ms);
        } else {
            final_status = "DONE";
            relay_node_cancel_auto_off(channel, true);
        }
    }

    *response = node_command_handler_create_response(
        cmd_id,
        final_status,
        error_code,
        error_message,
        error_details
    );
    if (error_details) {
        cJSON_Delete(error_details);
    }

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
    (void)user_ctx;

    if (channel == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Извлекаем cmd_id из params
    cJSON *cmd_id_item = cJSON_GetObjectItem(params, "cmd_id");
    const char *cmd_id = NULL;
    if (cmd_id_item && cJSON_IsString(cmd_id_item)) {
        cmd_id = cmd_id_item->valuestring;
    }

    relay_state_t current_state;
    esp_err_t get_err = relay_driver_get_state(channel, &current_state);
    
    if (get_err != ESP_OK) {
        const char *error_code = NULL;
        const char *error_message = NULL;
        cJSON *error_details = NULL;

        relay_node_build_error_details(
            get_err,
            channel,
            -1,
            "toggle",
            &error_code,
            &error_message,
            &error_details
        );
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", get_err, error_message);
        *response = node_command_handler_create_response(
            cmd_id,
            "FAILED",
            error_code,
            error_message,
            error_details
        );
        if (error_details) {
            cJSON_Delete(error_details);
        }
        return get_err;
    }

    relay_state_t new_state = (current_state == RELAY_STATE_OPEN) ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
    esp_err_t err = relay_driver_set_state(channel, new_state);
    
    if (err != ESP_OK) {
        const char *error_code = NULL;
        const char *error_message = NULL;
        cJSON *error_details = NULL;

        relay_node_build_error_details(
            err,
            channel,
            new_state == RELAY_STATE_CLOSED ? 1 : 0,
            "toggle",
            &error_code,
            &error_message,
            &error_details
        );
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "relay_driver", err, error_message);
        *response = node_command_handler_create_response(
            cmd_id,
            "FAILED",
            error_code,
            error_message,
            error_details
        );
        if (error_details) {
            cJSON_Delete(error_details);
        }
        return err;
    }

    cJSON *extra = cJSON_CreateObject();
    cJSON_AddNumberToObject(extra, "state", new_state);
    *response = node_command_handler_create_response(
        cmd_id,
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

    node_config_handler_set_channels_callback(relay_node_channels_callback, NULL);

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
