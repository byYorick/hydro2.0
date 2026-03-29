/**
 * @file storage_irrigation_node_framework_integration.c
 * @brief Интеграция storage_irrigation_node с node_framework
 * 
 * Этот файл связывает storage_irrigation_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "storage_irrigation_node_framework_integration.h"
#include "storage_irrigation_node_config.h"
#include "storage_irrigation_node_init.h"
#include "storage_irrigation_node_config_utils.h"
#include "node_framework.h"
#include "node_state_manager.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "node_utils.h"
#include "pump_driver.h"
#include "ina209.h"
#include "mqtt_manager.h"
#include "oled_ui.h"
#include "connection_status.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "storage_irrigation_node_framework";
static const uint32_t STORAGE_IRRIGATION_NODE_PUMP_MAIN_DRY_RUN_MAX_MS = 3000;

// Forward declaration для callback safe_mode
static esp_err_t storage_irrigation_node_disable_actuators_in_safe_mode(void *user_ctx);

#define STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_US ((int64_t)STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_MS * 1000LL)

typedef struct {
    const storage_irrigation_node_actuator_channel_t *cfg;
    bool state;
} storage_irrigation_node_actuator_runtime_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    uint32_t duration_ms;
} storage_irrigation_node_cmd_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
    bool auto_off;
    uint32_t duration_ms;
    TimerHandle_t timer;
} storage_irrigation_node_done_entry_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
    bool auto_off;
    uint32_t duration_ms;
} storage_irrigation_node_done_event_t;

typedef struct {
    char stage[32];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    uint32_t timeout_ms;
    TimerHandle_t timer;
    bool active;
    bool timeout_pending;
} storage_irrigation_node_stage_guard_t;

typedef struct {
    bool initialized;
    bool stable_state;
    bool candidate_state;
    int64_t candidate_since_us;
} storage_irrigation_node_level_switch_debounce_t;

static storage_irrigation_node_cmd_t s_cmd_queue[STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX] = {0};
static size_t s_cmd_queue_head = 0;
static size_t s_cmd_queue_tail = 0;
static size_t s_cmd_queue_count = 0;
static SemaphoreHandle_t s_cmd_queue_mutex = NULL;
static QueueHandle_t s_cmd_work_queue = NULL;
static TimerHandle_t s_cmd_retry_timer = NULL;

static storage_irrigation_node_done_entry_t s_done_entries[STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX] = {0};
static storage_irrigation_node_stage_guard_t s_stage_guards[3] = {0};
static QueueHandle_t s_done_queue = NULL;
static SemaphoreHandle_t s_actuator_mutex = NULL;
static SemaphoreHandle_t s_level_switch_mutex = NULL;
static storage_irrigation_node_actuator_runtime_t s_actuator_runtime[PUMP_DRIVER_MAX_CHANNELS] = {0};
static storage_irrigation_node_level_switch_debounce_t s_level_switch_debounce[GPIO_NUM_MAX] = {0};
static bool s_sensor_log_initialized[GPIO_NUM_MAX] = {0};
static bool s_sensor_logged_state[GPIO_NUM_MAX] = {0};
static size_t s_actuator_runtime_count = 0;

static void storage_irrigation_node_cmd_queue_task(void *pvParameters);
static void storage_irrigation_node_done_task(void *pvParameters);
static void storage_irrigation_node_process_cmd_queue(void);
static void storage_irrigation_node_signal_cmd_process(void);
static void storage_irrigation_node_retry_timer_cb(TimerHandle_t timer);
static void storage_irrigation_node_done_timer_cb(TimerHandle_t timer);
static void storage_irrigation_node_stage_guard_timer_cb(TimerHandle_t timer);
static bool storage_irrigation_node_cmd_queue_push(const storage_irrigation_node_cmd_t *cmd);
static bool storage_irrigation_node_cmd_queue_pop(storage_irrigation_node_cmd_t *cmd);
static void storage_irrigation_node_schedule_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
                                    float current_ma, bool current_valid, bool auto_off);
static bool storage_irrigation_node_any_pump_running(void);
static storage_irrigation_node_done_entry_t *storage_irrigation_node_get_done_entry(const char *channel, bool create);
static cJSON *storage_irrigation_node_channels_callback(void *user_ctx);
static esp_err_t storage_irrigation_node_init_level_switch_inputs(void);
static float storage_irrigation_node_read_level_switch(const storage_irrigation_node_sensor_channel_t *sensor, int *raw_out);
static esp_err_t storage_irrigation_node_init_actuator_outputs(void);
static int storage_irrigation_node_find_actuator_index(const char *channel);
static bool storage_irrigation_node_parse_relay_state(const cJSON *item, bool *state_out);
static bool storage_irrigation_node_refresh_actuator_state_locked(size_t index);
static esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state);
static bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out);
static bool storage_irrigation_node_is_pump_main_dry_run_allowed(const char *channel, bool target_state, bool has_duration, uint32_t duration_ms);
static bool storage_irrigation_node_is_clean_fill_active_locked(void);
static bool storage_irrigation_node_is_solution_fill_active_locked(void);
static bool storage_irrigation_node_is_main_pump_interlock_satisfied_locked(void);
static void storage_irrigation_node_append_main_pump_interlock_error(cJSON *details);
static bool storage_irrigation_node_read_switch_state_by_name(const char *sensor_name, bool *state_out);
static void storage_irrigation_node_update_oled_runtime(void);
static cJSON *storage_irrigation_node_build_irr_state_snapshot(void);
static cJSON *storage_irrigation_node_build_legacy_state_payload(void);
static esp_err_t handle_set_relay(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
static esp_err_t handle_storage_state(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
static esp_err_t storage_irrigation_node_publish_storage_event(const char *event_code, const char *cmd_id);
static esp_err_t storage_irrigation_node_publish_terminal_response(
    const char *channel,
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *error_message,
    cJSON *details
);
static void storage_irrigation_node_check_fill_completion_events(void);
static esp_err_t storage_irrigation_node_publish_level_switch_telemetry_snapshot(void);
static bool storage_irrigation_node_parse_timeout_ms(const cJSON *item, uint32_t *timeout_ms_out);
static bool storage_irrigation_node_parse_duration_ms(const cJSON *item, uint32_t *duration_ms_out);
static bool storage_irrigation_node_parse_stage_name(const cJSON *item, char *stage_out, size_t stage_out_size);
static storage_irrigation_node_stage_guard_t *storage_irrigation_node_get_stage_guard(const char *stage, bool create);
static esp_err_t storage_irrigation_node_arm_stage_guard_locked(const char *stage, const char *cmd_id, uint32_t timeout_ms);
static bool storage_irrigation_node_complete_stage_guard_for_channel_locked(const char *channel, char *cmd_id_out, size_t cmd_id_out_size);
static bool storage_irrigation_node_stop_stage_path_locked(const char *stage);
static const char *storage_irrigation_node_timeout_event_code_for_stage(const char *stage);
static void storage_irrigation_node_process_stage_timeouts(void);

static bool s_level_switch_inputs_ready = false;

/**
 * @brief Callback для инициализации каналов при применении конфигурации
 */
static esp_err_t storage_irrigation_node_init_channel_callback(const char *channel_name, const cJSON *channel_config, void *user_ctx) {
    (void)user_ctx;
    
    if (channel_config == NULL || channel_name == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Инициализация насосов обрабатывается через config_apply_channels_pump
    // Этот callback вызывается для каждого канала, но насосы инициализируются централизованно
    ESP_LOGD(TAG, "Channel init callback for: %s", channel_name);
    
    return ESP_OK;
}

static esp_err_t storage_irrigation_node_init_actuator_outputs(void) {
    bool used_gpio[GPIO_NUM_MAX] = {0};

    if (!pump_driver_is_initialized()) {
        ESP_LOGE(TAG, "Pump driver must be initialized before actuator runtime");
        return ESP_ERR_INVALID_STATE;
    }

    if (STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT > PUMP_DRIVER_MAX_CHANNELS) {
        ESP_LOGE(TAG, "Actuator channels exceed runtime capacity: %u", (unsigned)STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT);
        return ESP_ERR_INVALID_SIZE;
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_actuator_channel_t *cfg = &STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[i];
        if (!cfg->name || cfg->gpio < 0 || cfg->gpio >= GPIO_NUM_MAX || !GPIO_IS_VALID_OUTPUT_GPIO(cfg->gpio)) {
            ESP_LOGE(TAG, "Invalid actuator channel gpio: channel=%s gpio=%d", cfg->name ? cfg->name : "unknown", cfg->gpio);
            return ESP_ERR_INVALID_ARG;
        }
        if (used_gpio[cfg->gpio]) {
            ESP_LOGE(TAG, "Duplicate actuator gpio detected: channel=%s gpio=%d", cfg->name, cfg->gpio);
            return ESP_ERR_INVALID_ARG;
        }
        used_gpio[cfg->gpio] = true;
    }

    s_actuator_runtime_count = STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT;
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        s_actuator_runtime[i].cfg = &STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[i];
        s_actuator_runtime[i].state = false;
        (void)storage_irrigation_node_refresh_actuator_state_locked(i);
    }
    return ESP_OK;
}

static int storage_irrigation_node_find_actuator_index(const char *channel) {
    if (!channel || channel[0] == '\0') {
        return -1;
    }
    for (size_t i = 0; i < s_actuator_runtime_count; i++) {
        const storage_irrigation_node_actuator_channel_t *cfg = s_actuator_runtime[i].cfg;
        if (cfg && cfg->name && strcmp(cfg->name, channel) == 0) {
            return (int)i;
        }
    }
    return -1;
}

static bool storage_irrigation_node_parse_relay_state(const cJSON *item, bool *state_out) {
    if (!item || !state_out) {
        return false;
    }
    if (cJSON_IsBool(item)) {
        *state_out = cJSON_IsTrue(item);
        return true;
    }
    if (cJSON_IsNumber(item)) {
        *state_out = cJSON_GetNumberValue(item) > 0;
        return true;
    }
    return false;
}

static bool storage_irrigation_node_refresh_actuator_state_locked(size_t index) {
    if (index >= s_actuator_runtime_count || !s_actuator_runtime[index].cfg) {
        return false;
    }

    pump_driver_state_t driver_state = PUMP_STATE_OFF;
    if (pump_driver_get_state(s_actuator_runtime[index].cfg->name, &driver_state) != ESP_OK) {
        return false;
    }

    s_actuator_runtime[index].state = (driver_state == PUMP_STATE_ON);
    return true;
}

static bool storage_irrigation_node_parse_timeout_ms(const cJSON *item, uint32_t *timeout_ms_out) {
    if (timeout_ms_out) {
        *timeout_ms_out = 0;
    }
    if (!item || !cJSON_IsNumber(item) || !timeout_ms_out) {
        return false;
    }
    double raw_value = cJSON_GetNumberValue(item);
    if (raw_value < 1.0 || raw_value > 7200000.0) {
        return false;
    }
    *timeout_ms_out = (uint32_t)raw_value;
    return true;
}

static bool storage_irrigation_node_parse_duration_ms(const cJSON *item, uint32_t *duration_ms_out) {
    if (duration_ms_out) {
        *duration_ms_out = 0;
    }
    if (!item || !cJSON_IsNumber(item) || !duration_ms_out) {
        return false;
    }

    double raw_value = cJSON_GetNumberValue(item);
    if (raw_value <= 0.0 || raw_value > (double)UINT32_MAX) {
        return false;
    }

    *duration_ms_out = (uint32_t)raw_value;
    return true;
}

static bool storage_irrigation_node_parse_stage_name(const cJSON *item, char *stage_out, size_t stage_out_size) {
    if (stage_out && stage_out_size > 0) {
        stage_out[0] = '\0';
    }
    if (!item || !cJSON_IsString(item) || !item->valuestring || !stage_out || stage_out_size == 0) {
        return false;
    }
    const char *raw = item->valuestring;
    if (strcmp(raw, "solution_fill") != 0 && strcmp(raw, "prepare_recirculation") != 0) {
        return false;
    }
    strncpy(stage_out, raw, stage_out_size - 1);
    stage_out[stage_out_size - 1] = '\0';
    return true;
}

static esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state) {
    if (index >= s_actuator_runtime_count || !s_actuator_runtime[index].cfg) {
        return ESP_ERR_NOT_FOUND;
    }

    const storage_irrigation_node_actuator_channel_t *cfg = s_actuator_runtime[index].cfg;
    esp_err_t err = state
        ? pump_driver_set_state(cfg->name, true)
        : pump_driver_stop(cfg->name);

    if (err == ESP_OK) {
        (void)storage_irrigation_node_refresh_actuator_state_locked(index);
        return ESP_OK;
    }

    if (!state && err == ESP_ERR_INVALID_STATE) {
        bool refreshed = storage_irrigation_node_refresh_actuator_state_locked(index);
        if (refreshed && !s_actuator_runtime[index].state) {
            return ESP_OK;
        }
    }

    return err;
}

static bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out) {
    if (!channel || !state_out) {
        return false;
    }
    int index = storage_irrigation_node_find_actuator_index(channel);
    if (index < 0) {
        return false;
    }
    (void)storage_irrigation_node_refresh_actuator_state_locked((size_t)index);
    *state_out = s_actuator_runtime[index].state;
    return true;
}

static bool storage_irrigation_node_is_pump_main_dry_run_allowed(const char *channel, bool target_state, bool has_duration, uint32_t duration_ms) {
    return channel
        && strcmp(channel, "pump_main") == 0
        && target_state
        && has_duration
        && duration_ms > 0
        && duration_ms <= STORAGE_IRRIGATION_NODE_PUMP_MAIN_DRY_RUN_MAX_MS;
}

static bool storage_irrigation_node_is_clean_fill_active_locked(void) {
    bool valve_clean_fill = false;
    if (!storage_irrigation_node_get_actuator_state_locked("valve_clean_fill", &valve_clean_fill)) {
        return false;
    }
    return valve_clean_fill;
}

static bool storage_irrigation_node_is_solution_fill_active_locked(void) {
    bool pump_main = false;
    bool valve_clean_supply = false;
    bool valve_solution_fill = false;
    if (!storage_irrigation_node_get_actuator_state_locked("pump_main", &pump_main)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_clean_supply", &valve_clean_supply)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &valve_solution_fill)) {
        return false;
    }
    return pump_main && valve_clean_supply && valve_solution_fill;
}

static storage_irrigation_node_stage_guard_t *storage_irrigation_node_get_stage_guard(const char *stage, bool create) {
    if (!stage || stage[0] == '\0') {
        return NULL;
    }
    for (size_t i = 0; i < sizeof(s_stage_guards) / sizeof(s_stage_guards[0]); i++) {
        if (s_stage_guards[i].stage[0] != '\0' && strcmp(s_stage_guards[i].stage, stage) == 0) {
            return &s_stage_guards[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (size_t i = 0; i < sizeof(s_stage_guards) / sizeof(s_stage_guards[0]); i++) {
        if (s_stage_guards[i].stage[0] != '\0') {
            continue;
        }
        strncpy(s_stage_guards[i].stage, stage, sizeof(s_stage_guards[i].stage) - 1);
        s_stage_guards[i].timer = xTimerCreate(
            "irr_stage_guard",
            pdMS_TO_TICKS(1000),
            pdFALSE,
            &s_stage_guards[i],
            storage_irrigation_node_stage_guard_timer_cb
        );
        if (!s_stage_guards[i].timer) {
            s_stage_guards[i].stage[0] = '\0';
            return NULL;
        }
        return &s_stage_guards[i];
    }
    return NULL;
}

static esp_err_t storage_irrigation_node_arm_stage_guard_locked(const char *stage, const char *cmd_id, uint32_t timeout_ms) {
    storage_irrigation_node_stage_guard_t *guard = storage_irrigation_node_get_stage_guard(stage, true);
    if (!guard) {
        return ESP_ERR_NO_MEM;
    }
    guard->active = true;
    guard->timeout_pending = false;
    guard->timeout_ms = timeout_ms;
    if (cmd_id) {
        strncpy(guard->cmd_id, cmd_id, sizeof(guard->cmd_id) - 1);
        guard->cmd_id[sizeof(guard->cmd_id) - 1] = '\0';
    } else {
        guard->cmd_id[0] = '\0';
    }
    if (xTimerChangePeriod(guard->timer, pdMS_TO_TICKS(timeout_ms), 0) != pdPASS) {
        guard->active = false;
        guard->cmd_id[0] = '\0';
        return ESP_ERR_INVALID_STATE;
    }
    if (xTimerStart(guard->timer, 0) != pdPASS) {
        guard->active = false;
        guard->cmd_id[0] = '\0';
        return ESP_ERR_INVALID_STATE;
    }
    return ESP_OK;
}

static bool storage_irrigation_node_complete_stage_guard_for_channel_locked(const char *channel, char *cmd_id_out, size_t cmd_id_out_size) {
    if (cmd_id_out && cmd_id_out_size > 0) {
        cmd_id_out[0] = '\0';
    }
    if (!channel || strcmp(channel, "pump_main") != 0) {
        return false;
    }
    for (size_t i = 0; i < sizeof(s_stage_guards) / sizeof(s_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &s_stage_guards[i];
        if (!guard->active) {
            continue;
        }
        guard->active = false;
        guard->timeout_pending = false;
        xTimerStop(guard->timer, 0);
        if (cmd_id_out && cmd_id_out_size > 0 && guard->cmd_id[0] != '\0') {
            strncpy(cmd_id_out, guard->cmd_id, cmd_id_out_size - 1);
            cmd_id_out[cmd_id_out_size - 1] = '\0';
        }
        guard->cmd_id[0] = '\0';
        return true;
    }
    return false;
}

static bool storage_irrigation_node_stop_stage_path_locked(const char *stage) {
    const char *channels[3] = {0};
    size_t count = 0;
    if (strcmp(stage, "solution_fill") == 0) {
        channels[0] = "pump_main";
        channels[1] = "valve_solution_fill";
        channels[2] = "valve_clean_supply";
        count = 3;
    } else if (strcmp(stage, "prepare_recirculation") == 0) {
        channels[0] = "pump_main";
        channels[1] = "valve_solution_fill";
        channels[2] = "valve_solution_supply";
        count = 3;
    } else {
        return false;
    }

    bool all_ok = true;
    for (size_t i = 0; i < count; i++) {
        int idx = storage_irrigation_node_find_actuator_index(channels[i]);
        if (idx < 0) {
            all_ok = false;
            continue;
        }
        esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)idx, false);
        if (stop_err != ESP_OK) {
            all_ok = false;
            ESP_LOGE(TAG, "Failed to stop %s on stage timeout %s: %s", channels[i], stage, esp_err_to_name(stop_err));
        }
    }
    return all_ok;
}

static const char *storage_irrigation_node_timeout_event_code_for_stage(const char *stage) {
    if (!stage) {
        return NULL;
    }
    if (strcmp(stage, "solution_fill") == 0) {
        return "solution_fill_timeout";
    }
    if (strcmp(stage, "prepare_recirculation") == 0) {
        return "prepare_recirculation_timeout";
    }
    return NULL;
}

static bool storage_irrigation_node_is_main_pump_interlock_satisfied_locked(void) {
    bool valve_clean_supply = false;
    bool valve_solution_supply = false;
    bool valve_solution_fill = false;
    bool valve_irrigation = false;

    (void)storage_irrigation_node_get_actuator_state_locked("valve_clean_supply", &valve_clean_supply);
    (void)storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &valve_solution_supply);
    (void)storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &valve_solution_fill);
    (void)storage_irrigation_node_get_actuator_state_locked("valve_irrigation", &valve_irrigation);

    return (valve_clean_supply || valve_solution_supply) &&
           (valve_solution_fill || valve_irrigation);
}

static void storage_irrigation_node_append_main_pump_interlock_error(cJSON *details) {
    if (!details) {
        return;
    }
    cJSON_AddStringToObject(details, "error", "pump_interlock_blocked");
    cJSON_AddStringToObject(details, "error_code", "pump_interlock_blocked");
    cJSON_AddStringToObject(
        details,
        "error_message",
        "pump_main requires open supply valve and open solution_fill or irrigation valve"
    );
}

static bool storage_irrigation_node_read_switch_state_by_name(const char *sensor_name, bool *state_out) {
    if (!sensor_name || !state_out) {
        return false;
    }

    if (!s_level_switch_inputs_ready) {
        if (storage_irrigation_node_init_level_switch_inputs() != ESP_OK) {
            return false;
        }
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        if (strcmp(sensor->name, sensor_name) == 0) {
            *state_out = storage_irrigation_node_read_level_switch(sensor, NULL) >= 0.5f;
            return true;
        }
    }
    return false;
}

static void storage_irrigation_node_oled_push_bool_channel(
    oled_ui_model_t *model,
    size_t *index,
    const char *name,
    bool state
) {
    if (!model || !index || !name || *index >= 8) {
        return;
    }
    strncpy(model->channels[*index].name, name, sizeof(model->channels[*index].name) - 1);
    model->channels[*index].name[sizeof(model->channels[*index].name) - 1] = '\0';
    model->channels[*index].value = state ? 1.0f : 0.0f;
    model->channels[*index].active = state;
    (*index)++;
}

static void storage_irrigation_node_update_oled_runtime(void) {
    if (!oled_ui_is_initialized()) {
        return;
    }

    oled_ui_model_t model = {0};
    connection_status_t conn_status = {0};
    size_t channel_index = 0;
    bool state = false;

    if (connection_status_get(&conn_status) == ESP_OK) {
        model.connections.wifi_connected = conn_status.wifi_connected;
        model.connections.mqtt_connected = conn_status.mqtt_connected;
        model.connections.wifi_rssi = conn_status.wifi_rssi;
    }

    model.sensor_status.has_error = false;
    model.sensor_status.i2c_connected = true;
    model.sensor_status.using_stub = false;

    if (storage_irrigation_node_read_switch_state_by_name("level_clean_min", &state)) {
        storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "level_clean_min", state);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_clean_max", &state)) {
        storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "level_clean_max", state);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_solution_min", &state)) {
        storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "level_solution_min", state);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_solution_max", &state)) {
        storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "level_solution_max", state);
    }

    if (s_actuator_mutex && xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        if (storage_irrigation_node_get_actuator_state_locked("pump_main", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "pump_main", state);
        }
        if (storage_irrigation_node_get_actuator_state_locked("valve_clean_fill", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "valve_clean_fill", state);
        }
        if (storage_irrigation_node_get_actuator_state_locked("valve_clean_supply", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "valve_clean_supply", state);
        }
        if (storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "valve_solution_fill", state);
        }
        if (storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "valve_solution_supply", state);
        }
        if (storage_irrigation_node_get_actuator_state_locked("valve_irrigation", &state)) {
            storage_irrigation_node_oled_push_bool_channel(&model, &channel_index, "valve_irrigation", state);
        }
        xSemaphoreGive(s_actuator_mutex);
    }

    if (channel_index == 0) {
        return;
    }

    model.channel_count = channel_index;
    (void)oled_ui_update_model(&model);
}

static cJSON *storage_irrigation_node_build_irr_state_snapshot(void) {
    bool clean_level_max = false;
    bool clean_level_min = false;
    bool solution_level_max = false;
    bool solution_level_min = false;
    bool clean_level_max_ok = false;
    bool clean_level_min_ok = false;
    bool solution_level_max_ok = false;
    bool solution_level_min_ok = false;
    bool pump_main = false;
    bool valve_clean_fill = false;
    bool valve_clean_supply = false;
    bool valve_solution_fill = false;
    bool valve_solution_supply = false;
    bool valve_irrigation = false;
    bool actuators_ok = false;

    cJSON *snapshot = cJSON_CreateObject();
    if (!snapshot) {
        return NULL;
    }

    clean_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_clean_max", &clean_level_max);
    clean_level_min_ok = storage_irrigation_node_read_switch_state_by_name("level_clean_min", &clean_level_min);
    solution_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_solution_max", &solution_level_max);
    solution_level_min_ok = storage_irrigation_node_read_switch_state_by_name("level_solution_min", &solution_level_min);

    if (s_actuator_mutex && xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        bool ok = true;
        ok = storage_irrigation_node_get_actuator_state_locked("pump_main", &pump_main) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_clean_fill", &valve_clean_fill) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_clean_supply", &valve_clean_supply) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &valve_solution_fill) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &valve_solution_supply) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_irrigation", &valve_irrigation) && ok;
        actuators_ok = ok;
        xSemaphoreGive(s_actuator_mutex);
    }

    if (clean_level_max_ok) {
        cJSON_AddBoolToObject(snapshot, "clean_level_max", clean_level_max);
        cJSON_AddBoolToObject(snapshot, "level_clean_max", clean_level_max);
    }
    if (clean_level_min_ok) {
        cJSON_AddBoolToObject(snapshot, "clean_level_min", clean_level_min);
        cJSON_AddBoolToObject(snapshot, "level_clean_min", clean_level_min);
    }
    if (solution_level_max_ok) {
        cJSON_AddBoolToObject(snapshot, "solution_level_max", solution_level_max);
        cJSON_AddBoolToObject(snapshot, "level_solution_max", solution_level_max);
    }
    if (solution_level_min_ok) {
        cJSON_AddBoolToObject(snapshot, "solution_level_min", solution_level_min);
        cJSON_AddBoolToObject(snapshot, "level_solution_min", solution_level_min);
    }
    if (actuators_ok) {
        cJSON_AddBoolToObject(snapshot, "pump_main", pump_main);
        cJSON_AddBoolToObject(snapshot, "valve_clean_fill", valve_clean_fill);
        cJSON_AddBoolToObject(snapshot, "valve_clean_supply", valve_clean_supply);
        cJSON_AddBoolToObject(snapshot, "valve_solution_fill", valve_solution_fill);
        cJSON_AddBoolToObject(snapshot, "valve_solution_supply", valve_solution_supply);
        cJSON_AddBoolToObject(snapshot, "valve_irrigation", valve_irrigation);
    }
    return snapshot;
}

static cJSON *storage_irrigation_node_build_legacy_state_payload(void) {
    cJSON *legacy = cJSON_CreateObject();
    if (!legacy) {
        return NULL;
    }

    bool clean_level_max = false;
    bool clean_level_min = false;
    bool solution_level_max = false;
    bool solution_level_min = false;
    if (storage_irrigation_node_read_switch_state_by_name("level_clean_max", &clean_level_max)) {
        cJSON_AddBoolToObject(legacy, "level_clean_max", clean_level_max);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_clean_min", &clean_level_min)) {
        cJSON_AddBoolToObject(legacy, "level_clean_min", clean_level_min);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_solution_max", &solution_level_max)) {
        cJSON_AddBoolToObject(legacy, "level_solution_max", solution_level_max);
    }
    if (storage_irrigation_node_read_switch_state_by_name("level_solution_min", &solution_level_min)) {
        cJSON_AddBoolToObject(legacy, "level_solution_min", solution_level_min);
    }
    return legacy;
}

static esp_err_t handle_set_relay(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    if (!channel || !params || !response) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *cmd_id = node_command_handler_get_cmd_id(params);
    const cJSON *state_item = cJSON_GetObjectItem((cJSON *)params, "state");
    const cJSON *duration_ms_item = cJSON_GetObjectItem((cJSON *)params, "duration_ms");
    const cJSON *timeout_ms_item = cJSON_GetObjectItem((cJSON *)params, "timeout_ms");
    const cJSON *stage_item = cJSON_GetObjectItem((cJSON *)params, "stage");
    bool target_state = false;
    uint32_t duration_ms = 0;
    uint32_t timeout_ms = 0;
    char stage_name[32] = {0};
    bool has_duration = storage_irrigation_node_parse_duration_ms(duration_ms_item, &duration_ms);
    bool has_timeout = storage_irrigation_node_parse_timeout_ms(timeout_ms_item, &timeout_ms);
    bool has_stage = storage_irrigation_node_parse_stage_name(stage_item, stage_name, sizeof(stage_name));
    if (!storage_irrigation_node_parse_relay_state(state_item, &target_state)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "Missing or invalid state",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    bool timeout_stage_pair_mismatch = (timeout_ms_item != NULL) != (stage_item != NULL);
    if (target_state && (timeout_stage_pair_mismatch || (timeout_ms_item && !has_timeout) || (stage_item && !has_stage))) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "timeout_ms and stage must be provided together and be valid",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    if (duration_ms_item && (!target_state || !has_duration)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "duration_ms must be a positive number and can be used only with state=true",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    if (target_state && has_duration && has_timeout) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "duration_ms cannot be combined with timeout_ms/stage",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }
    if (target_state && has_timeout && (!has_stage || strcmp(channel, "pump_main") != 0)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "timeout_ms/stage is supported only for pump_main stage-arm command",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_actuator_mutex || xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "actuator_state_busy",
            "Actuator state lock timeout",
            NULL
        );
        return ESP_ERR_TIMEOUT;
    }

    int actuator_index = storage_irrigation_node_find_actuator_index(channel);
    if (actuator_index < 0) {
        xSemaphoreGive(s_actuator_mutex);
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "unsupported_channel",
            "Channel is not supported for set_relay",
            NULL
        );
        return ESP_ERR_NOT_FOUND;
    }

    bool previous_state = false;
    bool allow_pump_main_dry_run = storage_irrigation_node_is_pump_main_dry_run_allowed(
        channel,
        target_state,
        has_duration,
        duration_ms
    );
    (void)storage_irrigation_node_get_actuator_state_locked(channel, &previous_state);
    if (strcmp(channel, "pump_main") == 0
        && target_state
        && !allow_pump_main_dry_run
        && !storage_irrigation_node_is_main_pump_interlock_satisfied_locked()) {
        xSemaphoreGive(s_actuator_mutex);
        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            storage_irrigation_node_append_main_pump_interlock_error(extra);
        }
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "pump_interlock_blocked",
            "pump_main requires open supply valve and open solution_fill or irrigation valve",
            extra
        );
        if (extra) {
            cJSON_Delete(extra);
        }
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t set_err = ESP_OK;
    char completed_stage_cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN] = {0};
    if (previous_state != target_state) {
        set_err = storage_irrigation_node_set_actuator_state_locked((size_t)actuator_index, target_state);
        if (set_err != ESP_OK) {
            xSemaphoreGive(s_actuator_mutex);
            cJSON *extra = cJSON_CreateObject();
            const char *error_code = "actuator_apply_failed";
            const char *error_message = "Failed to apply actuator state";
            if (target_state && set_err == ESP_ERR_INVALID_STATE) {
                uint32_t cooldown_remaining_ms = 0;
                if (pump_driver_get_cooldown_remaining(channel, &cooldown_remaining_ms) == ESP_OK && cooldown_remaining_ms > 0) {
                    error_code = "cooldown_active";
                    error_message = "Actuator is in cooldown";
                    if (extra) {
                        cJSON_AddNumberToObject(extra, "cooldown_remaining_ms", (double)cooldown_remaining_ms);
                    }
                } else {
                    error_code = "actuator_busy";
                    error_message = "Actuator rejected requested state";
                }
            }
            *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                error_code,
                error_message,
                extra
            );
            if (extra) {
                cJSON_Delete(extra);
            }
            return set_err;
        }
    }
    if (target_state && has_duration && previous_state) {
        xSemaphoreGive(s_actuator_mutex);
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "transient_requires_idle_state",
            "Transient set_relay requires actuator to be OFF before start",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    if (!target_state) {
        (void)storage_irrigation_node_complete_stage_guard_for_channel_locked(
            channel,
            completed_stage_cmd_id,
            sizeof(completed_stage_cmd_id)
        );
    } else if (has_timeout) {
        esp_err_t guard_err = storage_irrigation_node_arm_stage_guard_locked(stage_name, cmd_id, timeout_ms);
        if (guard_err != ESP_OK) {
            bool rollback_ok = storage_irrigation_node_stop_stage_path_locked(stage_name);
            if (!rollback_ok) {
                ESP_LOGE(
                    TAG,
                    "Failed to fail-close stage path after guard arm error: stage=%s channel=%s",
                    stage_name,
                    channel
                );
            }
            xSemaphoreGive(s_actuator_mutex);
            *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "stage_guard_arm_failed",
                "Failed to arm stage timeout guard",
                NULL
            );
            return guard_err;
        }
    } else if (has_duration) {
        storage_irrigation_node_schedule_done(
            channel,
            cmd_id,
            duration_ms,
            0.0f,
            false,
            true
        );
    }

    xSemaphoreGive(s_actuator_mutex);

    storage_irrigation_node_update_oled_runtime();

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddBoolToObject(extra, "state", target_state);
        if (previous_state == target_state) {
            cJSON_AddStringToObject(extra, "note", "already_in_requested_state_treated_as_done");
        }
        if (has_duration) {
            cJSON_AddBoolToObject(extra, "transient", true);
            cJSON_AddNumberToObject(extra, "duration_ms", (double)duration_ms);
            if (allow_pump_main_dry_run) {
                cJSON_AddBoolToObject(extra, "dry_run", true);
            }
        }
        if (has_timeout) {
            cJSON_AddNumberToObject(extra, "timeout_ms", (double)timeout_ms);
            cJSON_AddStringToObject(extra, "stage", stage_name);
        }
    }
    *response = node_command_handler_create_response(
        cmd_id,
        (has_timeout || has_duration) ? "ACK" : "DONE",
        NULL,
        NULL,
        extra
    );
    if (extra) {
        cJSON_Delete(extra);
    }
    if (completed_stage_cmd_id[0] != '\0' && (!cmd_id || strcmp(completed_stage_cmd_id, cmd_id) != 0)) {
        cJSON *done_details = cJSON_CreateObject();
        if (done_details) {
            cJSON_AddStringToObject(done_details, "reason_code", "stage_stopped_by_command");
        }
        (void)storage_irrigation_node_publish_terminal_response("pump_main", completed_stage_cmd_id, "DONE", NULL, NULL, done_details);
    }
    return ESP_OK;
}

static esp_err_t handle_storage_state(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    if (!channel || !response) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *cmd_id = node_command_handler_get_cmd_id(params);
    if (strcmp(channel, "storage_state") != 0) {
        *response = node_command_handler_create_response(
            cmd_id,
            "INVALID",
            "unsupported_channel_cmd",
            "state command is supported only for storage_state channel",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *snapshot = storage_irrigation_node_build_irr_state_snapshot();
    cJSON *legacy_state = storage_irrigation_node_build_legacy_state_payload();
    cJSON *details = cJSON_CreateObject();
    if (!details) {
        if (snapshot) {
            cJSON_Delete(snapshot);
        }
        if (legacy_state) {
            cJSON_Delete(legacy_state);
        }
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "memory_error",
            "Failed to allocate state response",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    if (snapshot) {
        cJSON_AddItemToObject(details, "snapshot", snapshot);
    }
    if (legacy_state) {
        cJSON_AddItemToObject(details, "state", legacy_state);
    }
    cJSON_AddNumberToObject(details, "sample_ts", (double)node_utils_get_timestamp_seconds());
    cJSON_AddNumberToObject(details, "age_sec", 0);
    cJSON_AddNumberToObject(details, "max_age_sec", STORAGE_IRRIGATION_NODE_IRR_STATE_MAX_AGE_SEC);
    cJSON_AddBoolToObject(details, "is_fresh", true);

    *response = node_command_handler_create_response(cmd_id, "DONE", NULL, NULL, details);
    cJSON_Delete(details);
    return ESP_OK;
}

static esp_err_t storage_irrigation_node_init_level_switch_inputs(void) {
    bool used_gpio[GPIO_NUM_MAX] = {0};

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        int gpio = STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i].gpio;
        if (gpio < 0 || gpio >= GPIO_NUM_MAX || !GPIO_IS_VALID_GPIO(gpio)) {
            ESP_LOGE(TAG, "Invalid level-switch GPIO for channel %s: %d",
                     STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i].name, gpio);
            return ESP_ERR_INVALID_ARG;
        }
        if (used_gpio[gpio]) {
            ESP_LOGE(TAG, "Duplicate level-switch GPIO for channel %s: %d",
                     STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i].name, gpio);
            return ESP_ERR_INVALID_ARG;
        }
        used_gpio[gpio] = true;
    }

    if (STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        gpio_config_t io_conf = {
            .pin_bit_mask = (1ULL << (uint32_t)sensor->gpio),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = sensor->active_low ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
            .pull_down_en = sensor->active_low ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };

        esp_err_t err = gpio_config(&io_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure level-switch GPIO for channel %s: %s",
                     sensor->name, esp_err_to_name(err));
            return err;
        }
    }

    if (!s_level_switch_mutex) {
        s_level_switch_mutex = xSemaphoreCreateMutex();
        if (!s_level_switch_mutex) {
            ESP_LOGE(TAG, "Failed to create level-switch mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    if (xSemaphoreTake(s_level_switch_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        int64_t now_us = esp_timer_get_time();
        for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
            const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
            int raw = gpio_get_level((gpio_num_t)sensor->gpio);
            bool active = sensor->active_low ? (raw == 0) : (raw != 0);
            storage_irrigation_node_level_switch_debounce_t *state = &s_level_switch_debounce[sensor->gpio];
            state->initialized = true;
            state->stable_state = active;
            state->candidate_state = active;
            state->candidate_since_us = now_us;
        }
        xSemaphoreGive(s_level_switch_mutex);
    } else {
        ESP_LOGW(TAG, "Level-switch debounce init skipped due to mutex timeout");
    }

    s_level_switch_inputs_ready = true;
    return ESP_OK;
}

static float storage_irrigation_node_read_level_switch(
    const storage_irrigation_node_sensor_channel_t *sensor,
    int *raw_out
) {
    int raw = 0;
    bool active = false;
    bool filtered = false;
    int64_t now_us = 0;

    if (!sensor) {
        return 0.0f;
    }

    raw = gpio_get_level((gpio_num_t)sensor->gpio);
    active = sensor->active_low ? (raw == 0) : (raw != 0);
    filtered = active;

    if (s_level_switch_mutex &&
        xSemaphoreTake(s_level_switch_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
        storage_irrigation_node_level_switch_debounce_t *state = &s_level_switch_debounce[sensor->gpio];
        now_us = esp_timer_get_time();

        if (!state->initialized) {
            state->initialized = true;
            state->stable_state = active;
            state->candidate_state = active;
            state->candidate_since_us = now_us;
        } else if (active != state->stable_state) {
            if (active != state->candidate_state) {
                state->candidate_state = active;
                state->candidate_since_us = now_us;
            } else if ((now_us - state->candidate_since_us) >= STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_US) {
                state->stable_state = state->candidate_state;
            }
        } else {
            state->candidate_state = active;
            state->candidate_since_us = now_us;
        }

        filtered = state->stable_state;
        xSemaphoreGive(s_level_switch_mutex);
    }

    if (raw_out) {
        *raw_out = filtered ? 1 : 0;
    }
    return filtered ? 1.0f : 0.0f;
}

static esp_err_t storage_irrigation_node_publish_level_switch_telemetry_snapshot(void) {
    if (!s_level_switch_inputs_ready) {
        esp_err_t init_err = storage_irrigation_node_init_level_switch_inputs();
        if (init_err != ESP_OK) {
            return init_err;
        }
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        int raw = 0;
        float value = storage_irrigation_node_read_level_switch(sensor, &raw);
        bool active = value >= 0.5f;

        if (!s_sensor_log_initialized[sensor->gpio] || s_sensor_logged_state[sensor->gpio] != active) {
            ESP_LOGI(TAG, "sensor %s: raw=%d active=%d", sensor->name, raw, active ? 1 : 0);
            s_sensor_log_initialized[sensor->gpio] = true;
            s_sensor_logged_state[sensor->gpio] = active;
        }

        node_telemetry_publish_custom(sensor->name, sensor->metric, value, raw, false, true);
    }

    return ESP_OK;
}

/**
 * @brief Быстрый цикл опроса датчиков уровня и runtime-логики
 */
esp_err_t storage_irrigation_node_sensor_cycle(bool publish_telemetry) {
    (void)publish_telemetry;

    if (!s_level_switch_inputs_ready) {
        esp_err_t init_err = storage_irrigation_node_init_level_switch_inputs();
        if (init_err != ESP_OK) {
            return init_err;
        }
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        int raw = 0;
        float value = storage_irrigation_node_read_level_switch(sensor, &raw);
        bool active = value >= 0.5f;

        if (!s_sensor_log_initialized[sensor->gpio] || s_sensor_logged_state[sensor->gpio] != active) {
            ESP_LOGI(TAG, "sensor %s: raw=%d active=%d", sensor->name, raw, active ? 1 : 0);
            s_sensor_log_initialized[sensor->gpio] = true;
            s_sensor_logged_state[sensor->gpio] = active;
        }
    }

    storage_irrigation_node_check_fill_completion_events();
    storage_irrigation_node_update_oled_runtime();

    return ESP_OK;
}

esp_err_t storage_irrigation_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;
    return storage_irrigation_node_publish_level_switch_telemetry_snapshot();
}

static esp_err_t storage_irrigation_node_publish_storage_event(const char *event_code, const char *cmd_id) {
    if (!event_code || event_code[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }
    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }

    mqtt_node_info_t node_info = {0};
    esp_err_t info_err = mqtt_manager_get_node_info(&node_info);
    if (info_err != ESP_OK || !node_info.gh_uid || !node_info.zone_uid || !node_info.node_uid) {
        return info_err != ESP_OK ? info_err : ESP_ERR_INVALID_STATE;
    }

    char topic[192] = {0};
    int written = snprintf(
        topic,
        sizeof(topic),
        "hydro/%s/%s/%s/%s/%s",
        node_info.gh_uid,
        node_info.zone_uid,
        node_info.node_uid,
        "storage_state",
        "event"
    );
    if (written <= 0 || (size_t)written >= sizeof(topic)) {
        return ESP_ERR_INVALID_SIZE;
    }

    cJSON *payload = cJSON_CreateObject();
    if (!payload) {
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddStringToObject(payload, "event_code", event_code);
    cJSON_AddNumberToObject(payload, "ts", (double)node_utils_get_timestamp_seconds());
    if (cmd_id && cmd_id[0] != '\0') {
        cJSON_AddStringToObject(payload, "cmd_id", cmd_id);
    }
    cJSON *snapshot = storage_irrigation_node_build_irr_state_snapshot();
    if (snapshot) {
        cJSON_AddItemToObject(payload, "snapshot", snapshot);
    }
    cJSON *legacy_state = storage_irrigation_node_build_legacy_state_payload();
    if (legacy_state) {
        cJSON_AddItemToObject(payload, "state", legacy_state);
    }

    char *json_str = cJSON_PrintUnformatted(payload);
    cJSON_Delete(payload);
    if (!json_str) {
        return ESP_ERR_NO_MEM;
    }
    esp_err_t pub_err = mqtt_manager_publish_raw(topic, json_str, 1, 0);
    free(json_str);
    return pub_err;
}

static esp_err_t storage_irrigation_node_publish_terminal_response(
    const char *channel,
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *error_message,
    cJSON *details
) {
    cJSON *response = node_command_handler_create_response(cmd_id, status, error_code, error_message, details);
    if (details) {
        cJSON_Delete(details);
    }
    if (!response) {
        return ESP_ERR_NO_MEM;
    }
    char *json_str = cJSON_PrintUnformatted(response);
    cJSON_Delete(response);
    if (!json_str) {
        return ESP_ERR_NO_MEM;
    }
    mqtt_manager_publish_command_response(channel ? channel : "default", json_str);
    free(json_str);
    node_command_handler_cache_final_status(cmd_id, channel, status);
    return ESP_OK;
}

static void storage_irrigation_node_check_fill_completion_events(void) {
    bool clean_level_max = false;
    bool solution_level_max = false;
    bool clean_level_max_ok = false;
    bool solution_level_max_ok = false;
    bool emit_clean_completed = false;
    bool emit_solution_completed = false;

    clean_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_clean_max", &clean_level_max);
    solution_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_solution_max", &solution_level_max);

    if (!s_actuator_mutex || xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(200)) != pdTRUE) {
        return;
    }

    bool clean_fill_active = storage_irrigation_node_is_clean_fill_active_locked();
    if (clean_level_max_ok && clean_level_max && clean_fill_active) {
        int valve_clean_fill_idx = storage_irrigation_node_find_actuator_index("valve_clean_fill");
        if (valve_clean_fill_idx >= 0) {
            esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)valve_clean_fill_idx, false);
            if (stop_err == ESP_OK) {
                emit_clean_completed = true;
            } else {
                ESP_LOGE(TAG, "Failed to stop valve_clean_fill on level_clean_max: %s", esp_err_to_name(stop_err));
            }
        }
    }

    bool solution_fill_active = storage_irrigation_node_is_solution_fill_active_locked();
    if (solution_level_max_ok && solution_level_max && solution_fill_active) {
        emit_solution_completed = true;
    }

    xSemaphoreGive(s_actuator_mutex);

    if (emit_clean_completed) {
        (void)storage_irrigation_node_publish_storage_event("clean_fill_completed", NULL);
    }
    if (emit_solution_completed) {
        (void)storage_irrigation_node_publish_storage_event("solution_fill_completed", NULL);
    }
}

static void storage_irrigation_node_stage_guard_timer_cb(TimerHandle_t timer) {
    storage_irrigation_node_stage_guard_t *guard = (storage_irrigation_node_stage_guard_t *)pvTimerGetTimerID(timer);
    if (!guard) {
        return;
    }
    guard->timeout_pending = true;
    storage_irrigation_node_signal_cmd_process();
}

/**
 * @brief Wrapper для обработки config сообщений через node_framework
 */
static void storage_irrigation_node_config_handler_wrapper(const char *topic, const char *data, int data_len, void *user_ctx) {
    if (data == NULL || data_len <= 0) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    bool changed = false;
    char *patched = storage_irrigation_node_build_patched_config(data, (size_t)data_len, true, &changed);
    if (!patched) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        return;
    }

    node_config_handler_process(topic, patched, (int)strlen(patched), user_ctx);
    free(patched);
}

/**
 * @brief Wrapper для обработки command сообщений через node_framework
 */
static void storage_irrigation_node_command_handler_wrapper(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

static cJSON *storage_irrigation_node_channels_callback(void *user_ctx) {
    (void)user_ctx;
    return storage_irrigation_node_build_config_channels();
}

static bool storage_irrigation_node_any_pump_running(void) {
    pump_driver_health_snapshot_t snapshot = {0};
    if (pump_driver_get_health_snapshot(&snapshot) != ESP_OK) {
        return false;
    }
    for (size_t i = 0; i < snapshot.channel_count; i++) {
        if (snapshot.channels[i].is_running) {
            return true;
        }
    }
    return false;
}

static bool storage_irrigation_node_cmd_queue_push(const storage_irrigation_node_cmd_t *cmd) {
    if (!cmd || !s_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(s_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (s_cmd_queue_count >= STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX) {
        xSemaphoreGive(s_cmd_queue_mutex);
        return false;
    }
    s_cmd_queue[s_cmd_queue_tail] = *cmd;
    s_cmd_queue_tail = (s_cmd_queue_tail + 1) % STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX;
    s_cmd_queue_count++;
    xSemaphoreGive(s_cmd_queue_mutex);
    return true;
}

static bool storage_irrigation_node_cmd_queue_pop(storage_irrigation_node_cmd_t *cmd) {
    if (!cmd || !s_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(s_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (s_cmd_queue_count == 0) {
        xSemaphoreGive(s_cmd_queue_mutex);
        return false;
    }
    *cmd = s_cmd_queue[s_cmd_queue_head];
    memset(&s_cmd_queue[s_cmd_queue_head], 0, sizeof(s_cmd_queue[s_cmd_queue_head]));
    s_cmd_queue_head = (s_cmd_queue_head + 1) % STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX;
    s_cmd_queue_count--;
    xSemaphoreGive(s_cmd_queue_mutex);
    return true;
}

static void storage_irrigation_node_signal_cmd_process(void) {
    if (!s_cmd_work_queue) {
        return;
    }
    uint8_t token = 1;
    xQueueSend(s_cmd_work_queue, &token, 0);
}

static storage_irrigation_node_done_entry_t *storage_irrigation_node_get_done_entry(const char *channel, bool create) {
    if (!channel) {
        return NULL;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX; i++) {
        if (s_done_entries[i].channel_name[0] != '\0' &&
            strncmp(s_done_entries[i].channel_name, channel, sizeof(s_done_entries[i].channel_name)) == 0) {
            return &s_done_entries[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX; i++) {
        if (s_done_entries[i].channel_name[0] == '\0') {
            strncpy(s_done_entries[i].channel_name, channel, sizeof(s_done_entries[i].channel_name) - 1);
            s_done_entries[i].timer = xTimerCreate(
                "pump_done",
                pdMS_TO_TICKS(1000),
                pdFALSE,
                &s_done_entries[i],
                storage_irrigation_node_done_timer_cb
            );
            if (!s_done_entries[i].timer) {
                s_done_entries[i].channel_name[0] = '\0';
                return NULL;
            }
            return &s_done_entries[i];
        }
    }
    return NULL;
}

static void storage_irrigation_node_schedule_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
                                    float current_ma, bool current_valid, bool auto_off) {
    storage_irrigation_node_done_entry_t *entry = storage_irrigation_node_get_done_entry(channel, true);
    if (!entry) {
        ESP_LOGW(TAG, "No done entry available for channel %s", channel);
        return;
    }
    if (cmd_id) {
        strncpy(entry->cmd_id, cmd_id, sizeof(entry->cmd_id) - 1);
    } else {
        entry->cmd_id[0] = '\0';
    }
    entry->current_ma = current_ma;
    entry->current_valid = current_valid;
    entry->auto_off = auto_off;
    entry->duration_ms = duration_ms;
    if (duration_ms == 0) {
        duration_ms = 1;
    }
    if (xTimerChangePeriod(entry->timer, pdMS_TO_TICKS(duration_ms), 0) != pdPASS) {
        ESP_LOGW(TAG, "Failed to arm done timer for %s", channel);
        return;
    }
    xTimerStart(entry->timer, 0);
}

static void storage_irrigation_node_done_timer_cb(TimerHandle_t timer) {
    storage_irrigation_node_done_entry_t *entry = (storage_irrigation_node_done_entry_t *)pvTimerGetTimerID(timer);
    if (!entry || entry->cmd_id[0] == '\0' || !s_done_queue) {
        return;
    }
    storage_irrigation_node_done_event_t event = {0};
    strncpy(event.channel_name, entry->channel_name, sizeof(event.channel_name) - 1);
    strncpy(event.cmd_id, entry->cmd_id, sizeof(event.cmd_id) - 1);
    event.current_ma = entry->current_ma;
    event.current_valid = entry->current_valid;
    event.auto_off = entry->auto_off;
    event.duration_ms = entry->duration_ms;
    if (xQueueSend(s_done_queue, &event, 0) != pdTRUE) {
        ESP_LOGW(TAG, "Done queue full for channel %s", entry->channel_name);
    }
}

static void storage_irrigation_node_done_task(void *pvParameters) {
    (void)pvParameters;
    storage_irrigation_node_done_event_t event = {0};
    while (true) {
        if (xQueueReceive(s_done_queue, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (event.auto_off) {
            esp_err_t auto_off_err = ESP_OK;
            if (!s_actuator_mutex || xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
                auto_off_err = ESP_ERR_TIMEOUT;
            } else {
                int actuator_index = storage_irrigation_node_find_actuator_index(event.channel_name);
                if (actuator_index < 0) {
                    auto_off_err = ESP_ERR_NOT_FOUND;
                } else {
                    auto_off_err = storage_irrigation_node_set_actuator_state_locked((size_t)actuator_index, false);
                }
                xSemaphoreGive(s_actuator_mutex);
            }

            if (auto_off_err != ESP_OK) {
                cJSON *error_details = cJSON_CreateObject();
                if (error_details) {
                    cJSON_AddBoolToObject(error_details, "transient", true);
                    cJSON_AddNumberToObject(error_details, "duration_ms", (double)event.duration_ms);
                }
                (void)storage_irrigation_node_publish_terminal_response(
                    event.channel_name,
                    event.cmd_id[0] ? event.cmd_id : NULL,
                    "ERROR",
                    "actuator_release_failed",
                    "Transient actuator command could not restore OFF state",
                    error_details
                );
                storage_irrigation_node_update_oled_runtime();
                continue;
            }
            storage_irrigation_node_update_oled_runtime();
        }

        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "current_ma", event.current_ma);
            cJSON_AddBoolToObject(extra, "current_valid", event.current_valid);
            if (event.auto_off) {
                cJSON_AddBoolToObject(extra, "transient", true);
                cJSON_AddBoolToObject(extra, "state", false);
                cJSON_AddNumberToObject(extra, "duration_ms", (double)event.duration_ms);
                if (strcmp(event.channel_name, "pump_main") == 0
                    && event.duration_ms <= STORAGE_IRRIGATION_NODE_PUMP_MAIN_DRY_RUN_MAX_MS) {
                    cJSON_AddBoolToObject(extra, "dry_run", true);
                }
            }
        }
        cJSON *response = node_command_handler_create_response(
            event.cmd_id[0] ? event.cmd_id : NULL,
            "DONE",
            NULL,
            NULL,
            extra
        );
        if (extra) {
            cJSON_Delete(extra);
        }
        if (response) {
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(event.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        if (event.cmd_id[0]) {
            node_command_handler_cache_final_status(event.cmd_id, event.channel_name, "DONE");
        }
        storage_irrigation_node_signal_cmd_process();
    }
}

static void storage_irrigation_node_retry_timer_cb(TimerHandle_t timer) {
    (void)timer;
    storage_irrigation_node_signal_cmd_process();
}

static void storage_irrigation_node_process_cmd_queue(void) {
    storage_irrigation_node_process_stage_timeouts();
    if (storage_irrigation_node_any_pump_running()) {
        return;
    }

    storage_irrigation_node_cmd_t cmd = {0};
    if (!storage_irrigation_node_cmd_queue_pop(&cmd)) {
        return;
    }

    uint32_t cooldown_ms = 0;
    if (pump_driver_get_cooldown_remaining(cmd.channel_name, &cooldown_ms) == ESP_OK && cooldown_ms > 0) {
        if (!storage_irrigation_node_cmd_queue_push(&cmd)) {
            cJSON *response = node_command_handler_create_response(
                cmd.cmd_id[0] ? cmd.cmd_id : NULL,
                "ERROR",
                "pump_queue_full",
                "Pump queue is full",
                NULL
            );
            if (response) {
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
            if (cmd.cmd_id[0]) {
                node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "ERROR");
            }
        }
        if (s_cmd_retry_timer && cooldown_ms > 0) {
            xTimerChangePeriod(s_cmd_retry_timer, pdMS_TO_TICKS(cooldown_ms), 0);
            xTimerStart(s_cmd_retry_timer, 0);
        }
        return;
    }

    esp_err_t err = pump_driver_run(cmd.channel_name, cmd.duration_ms);
    if (err != ESP_OK) {
        const char *error_code = "pump_driver_failed";
        const char *error_message = esp_err_to_name(err);
        if (err == ESP_ERR_INVALID_RESPONSE) {
            error_code = "current_not_detected";
            error_message = "Pump started but no current detected";
        } else if (err == ESP_ERR_INVALID_SIZE) {
            error_code = "overcurrent";
            error_message = "Pump current exceeds safe limit";
        }
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "pump_driver", err, error_message);
        cJSON *response = node_command_handler_create_response(
            cmd.cmd_id[0] ? cmd.cmd_id : NULL,
            "ERROR",
            error_code,
            error_message,
            NULL
        );
        if (response) {
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(cmd.channel_name, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        if (cmd.cmd_id[0]) {
            node_command_handler_cache_final_status(cmd.cmd_id, cmd.channel_name, "ERROR");
        }
        storage_irrigation_node_signal_cmd_process();
        return;
    }

    ina209_reading_t reading = {0};
    bool current_valid = (ina209_read(&reading) == ESP_OK && reading.valid);
    float current_ma = current_valid ? reading.bus_current_ma : 0.0f;
    storage_irrigation_node_schedule_done(cmd.channel_name, cmd.cmd_id, cmd.duration_ms, current_ma, current_valid, false);
}

static void storage_irrigation_node_process_stage_timeouts(void) {
    for (size_t i = 0; i < sizeof(s_stage_guards) / sizeof(s_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &s_stage_guards[i];
        if (!guard->active || !guard->timeout_pending) {
            continue;
        }

        char stage_name[sizeof(guard->stage)] = {0};
        char cmd_id[sizeof(guard->cmd_id)] = {0};
        uint32_t timeout_ms = guard->timeout_ms;
        strncpy(stage_name, guard->stage, sizeof(stage_name) - 1);
        strncpy(cmd_id, guard->cmd_id, sizeof(cmd_id) - 1);
        guard->timeout_pending = false;
        guard->active = false;
        xTimerStop(guard->timer, 0);
        guard->cmd_id[0] = '\0';

        if (s_actuator_mutex && xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
            (void)storage_irrigation_node_stop_stage_path_locked(stage_name);
            xSemaphoreGive(s_actuator_mutex);
        }
        storage_irrigation_node_update_oled_runtime();

        const char *event_code = storage_irrigation_node_timeout_event_code_for_stage(stage_name);
        cJSON *error_details = cJSON_CreateObject();
        if (error_details) {
            cJSON_AddStringToObject(error_details, "stage", stage_name);
            cJSON_AddNumberToObject(error_details, "timeout_ms", (double)timeout_ms);
            cJSON_AddStringToObject(error_details, "reason_code", "stage_timeout");
        }
        if (cmd_id[0] != '\0') {
            (void)storage_irrigation_node_publish_terminal_response(
                "pump_main",
                cmd_id,
                "ERROR",
                "stage_timeout",
                "Stage timeout reached; flow path stopped by node",
                error_details
            );
        } else if (error_details) {
            cJSON_Delete(error_details);
        }
        if (event_code) {
            (void)storage_irrigation_node_publish_storage_event(event_code, cmd_id);
        }
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "stage_timeout", ESP_ERR_TIMEOUT, "Stage timeout reached; flow path stopped");
    }
}

static void storage_irrigation_node_cmd_queue_task(void *pvParameters) {
    (void)pvParameters;
    uint8_t token = 0;
    while (true) {
        if (xQueueReceive(s_cmd_work_queue, &token, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        storage_irrigation_node_process_cmd_queue();
    }
}


/**
 * @brief Инициализация интеграции storage_irrigation_node с node_framework
 */
esp_err_t storage_irrigation_node_framework_init_integration(void) {
    ESP_LOGD(TAG, "Initializing storage_irrigation_node framework integration...");
    
    // Конфигурация node_framework
    node_framework_config_t config = {
        .node_type = "irrig",
        .default_node_id = STORAGE_IRRIGATION_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = STORAGE_IRRIGATION_NODE_DEFAULT_GH_UID,
        .default_zone_uid = STORAGE_IRRIGATION_NODE_DEFAULT_ZONE_UID,
        .channel_init_cb = storage_irrigation_node_init_channel_callback,
        .command_handler_cb = NULL,  // Регистрация через API
        .telemetry_cb = storage_irrigation_node_publish_telemetry_callback,
        .user_ctx = NULL
    };
    
    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", err, "Node framework initialization failed");
        return err;
    }

    err = storage_irrigation_node_init_level_switch_inputs();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize level-switch inputs: %s", esp_err_to_name(err));
        return err;
    }

    if (!s_actuator_mutex) {
        s_actuator_mutex = xSemaphoreCreateMutex();
        if (!s_actuator_mutex) {
            ESP_LOGE(TAG, "Failed to create actuator mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    err = storage_irrigation_node_init_actuator_outputs();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize actuator outputs: %s", esp_err_to_name(err));
        return err;
    }
    storage_irrigation_node_update_oled_runtime();

    if (!s_cmd_queue_mutex) {
        s_cmd_queue_mutex = xSemaphoreCreateMutex();
        if (!s_cmd_queue_mutex) {
            ESP_LOGE(TAG, "Failed to create pump command queue mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    if (!s_cmd_work_queue) {
        s_cmd_work_queue = xQueueCreate(STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX, sizeof(uint8_t));
        if (!s_cmd_work_queue) {
            ESP_LOGE(TAG, "Failed to create pump command queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(storage_irrigation_node_cmd_queue_task, "pump_cmd_queue", 4096, NULL, 4, NULL);
    }
    if (!s_done_queue) {
        s_done_queue = xQueueCreate(STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX, sizeof(storage_irrigation_node_done_event_t));
        if (!s_done_queue) {
            ESP_LOGE(TAG, "Failed to create pump done queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(storage_irrigation_node_done_task, "pump_done", 4096, NULL, 4, NULL);
    }
    if (!s_cmd_retry_timer) {
        s_cmd_retry_timer = xTimerCreate("pump_retry", pdMS_TO_TICKS(1000), pdFALSE, NULL, storage_irrigation_node_retry_timer_cb);
        if (!s_cmd_retry_timer) {
            ESP_LOGW(TAG, "Failed to create pump retry timer");
        }
    }
    for (size_t i = 0; i < sizeof(s_stage_guards) / sizeof(s_stage_guards[0]); i++) {
        if (!s_stage_guards[i].timer) {
            continue;
        }
        xTimerStop(s_stage_guards[i].timer, 0);
    }
    
    // Регистрация обработчиков команд
    err = node_command_handler_register("set_relay", handle_set_relay, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register set_relay handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("state", handle_storage_state, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register state handler: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(storage_irrigation_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }

    node_config_handler_set_channels_callback(storage_irrigation_node_channels_callback, NULL);
    
    ESP_LOGD(TAG, "storage_irrigation_node framework integration initialized");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t storage_irrigation_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    (void)pump_driver_emergency_stop();

    if (!s_actuator_mutex || xSemaphoreTake(s_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    for (size_t i = 0; i < s_actuator_runtime_count; i++) {
        (void)storage_irrigation_node_set_actuator_state_locked(i, false);
    }
    xSemaphoreGive(s_actuator_mutex);
    storage_irrigation_node_update_oled_runtime();
    return ESP_OK;
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void storage_irrigation_node_framework_register_mqtt_handlers(void) {
    // Регистрация обработчика конфигов
    mqtt_manager_register_config_cb(storage_irrigation_node_config_handler_wrapper, NULL);
    
    // Регистрация обработчика команд
    mqtt_manager_register_command_cb(storage_irrigation_node_command_handler_wrapper, NULL);
    
    // Регистрация MQTT callbacks в node_config_handler для config_apply_mqtt
    // Это позволяет автоматически переподключать MQTT при изменении конфига
    node_config_handler_set_mqtt_callbacks(
        storage_irrigation_node_config_handler_wrapper,
        storage_irrigation_node_command_handler_wrapper,
        storage_irrigation_node_mqtt_connection_cb,  // connection_cb
        NULL,
        STORAGE_IRRIGATION_NODE_DEFAULT_NODE_ID,
        STORAGE_IRRIGATION_NODE_DEFAULT_GH_UID,
        STORAGE_IRRIGATION_NODE_DEFAULT_ZONE_UID
    );
    
    ESP_LOGD(TAG, "MQTT handlers registered via node_framework");
}
