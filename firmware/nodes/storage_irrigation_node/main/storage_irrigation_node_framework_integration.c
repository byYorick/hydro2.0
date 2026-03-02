/**
 * @file storage_irrigation_node_framework_integration.c
 * @brief Интеграция storage_irrigation_node с node_framework
 * 
 * Этот файл связывает storage_irrigation_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "storage_irrigation_node_framework_integration.h"
#include "storage_irrigation_node_defaults.h"
#include "storage_irrigation_node_init.h"
#include "storage_irrigation_node_channel_map.h"
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

// Forward declaration для callback safe_mode
static esp_err_t storage_irrigation_node_disable_actuators_in_safe_mode(void *user_ctx);

#define STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX 8
#define STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX 8
#define STORAGE_IRRIGATION_NODE_CMD_ID_LEN 64
#define STORAGE_IRRIGATION_NODE_IRR_STATE_MAX_AGE_SEC 30
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
    TimerHandle_t timer;
} storage_irrigation_node_done_entry_t;

typedef struct {
    char channel_name[PUMP_DRIVER_MAX_CHANNEL_NAME_LEN];
    char cmd_id[STORAGE_IRRIGATION_NODE_CMD_ID_LEN];
    float current_ma;
    bool current_valid;
} storage_irrigation_node_done_event_t;

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
static QueueHandle_t s_done_queue = NULL;
static SemaphoreHandle_t s_actuator_mutex = NULL;
static SemaphoreHandle_t s_level_switch_mutex = NULL;
static storage_irrigation_node_actuator_runtime_t s_actuator_runtime[PUMP_DRIVER_MAX_CHANNELS] = {0};
static storage_irrigation_node_level_switch_debounce_t s_level_switch_debounce[GPIO_NUM_MAX] = {0};
static size_t s_actuator_runtime_count = 0;

static void storage_irrigation_node_cmd_queue_task(void *pvParameters);
static void storage_irrigation_node_done_task(void *pvParameters);
static void storage_irrigation_node_process_cmd_queue(void);
static void storage_irrigation_node_signal_cmd_process(void);
static void storage_irrigation_node_retry_timer_cb(TimerHandle_t timer);
static void storage_irrigation_node_done_timer_cb(TimerHandle_t timer);
static bool storage_irrigation_node_cmd_queue_push(const storage_irrigation_node_cmd_t *cmd);
static bool storage_irrigation_node_cmd_queue_pop(storage_irrigation_node_cmd_t *cmd);
static bool storage_irrigation_node_any_pump_running(void);
static storage_irrigation_node_done_entry_t *storage_irrigation_node_get_done_entry(const char *channel, bool create);
static cJSON *storage_irrigation_node_channels_callback(void *user_ctx);
static esp_err_t storage_irrigation_node_init_level_switch_inputs(void);
static float storage_irrigation_node_read_level_switch(const storage_irrigation_node_sensor_channel_t *sensor, int *raw_out);
static esp_err_t storage_irrigation_node_init_actuator_outputs(void);
static int storage_irrigation_node_find_actuator_index(const char *channel);
static bool storage_irrigation_node_parse_relay_state(const cJSON *item, bool *state_out);
static esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state);
static bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out);
static bool storage_irrigation_node_is_clean_fill_active_locked(void);
static bool storage_irrigation_node_is_solution_fill_active_locked(void);
static bool storage_irrigation_node_is_main_pump_interlock_satisfied_locked(void);
static void storage_irrigation_node_append_main_pump_interlock_error(cJSON *details);
static bool storage_irrigation_node_read_switch_state_by_name(const char *sensor_name, bool *state_out);
static cJSON *storage_irrigation_node_build_irr_state_snapshot(void);
static cJSON *storage_irrigation_node_build_legacy_state_payload(void);
static esp_err_t handle_set_relay(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
static esp_err_t handle_storage_state(const char *channel, const cJSON *params, cJSON **response, void *user_ctx);
static esp_err_t storage_irrigation_node_publish_storage_event(const char *event_code, const char *cmd_id);
static void storage_irrigation_node_check_fill_completion_events(void);

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

/**
 * @brief Обработчик команды run_pump с командным автоматом
 * 
 * Состояния: ACK -> DONE/ERROR
 */
static esp_err_t handle_run_pump(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    
    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Извлекаем cmd_id из params (он будет добавлен позже в node_command_handler_process)
    // Но для промежуточного ответа нам нужен cmd_id, поэтому получаем его из params
    const char *cmd_id = node_command_handler_get_cmd_id(params);
    
    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    if (!cJSON_IsNumber(duration_item)) {
        *response = node_command_handler_create_response(cmd_id, "ERROR", "missing_duration", "duration_ms is required", NULL);
        return ESP_ERR_INVALID_ARG;
    }
    
    int duration_ms = (int)cJSON_GetNumberValue(duration_item);
    ESP_LOGI(TAG, "Running pump on channel %s for %d ms", channel, duration_ms);
    
    storage_irrigation_node_cmd_t queued_cmd = {0};
    strncpy(queued_cmd.channel_name, channel, sizeof(queued_cmd.channel_name) - 1);
    if (cmd_id) {
        strncpy(queued_cmd.cmd_id, cmd_id, sizeof(queued_cmd.cmd_id) - 1);
    }
    queued_cmd.duration_ms = (uint32_t)duration_ms;

    if (!storage_irrigation_node_cmd_queue_push(&queued_cmd)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "pump_queue_full",
            "Pump queue is full",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    bool queued = storage_irrigation_node_any_pump_running();
    uint32_t cooldown_remaining_ms = 0;
    bool cooldown_active = (pump_driver_get_cooldown_remaining(channel, &cooldown_remaining_ms) == ESP_OK &&
                            cooldown_remaining_ms > 0);
    if (cooldown_active) {
        queued = true;
    }

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddNumberToObject(extra, "duration_ms", duration_ms);
        cJSON_AddBoolToObject(extra, "queued", queued);
        if (cooldown_active) {
            cJSON_AddNumberToObject(extra, "cooldown_ms", cooldown_remaining_ms);
        }
    }
    *response = node_command_handler_create_response(
        cmd_id,
        "ACK",
        NULL,
        NULL,
        extra
    );
    if (extra) {
        cJSON_Delete(extra);
    }

    if (cooldown_active) {
        storage_irrigation_node_signal_cmd_process();
    } else {
        storage_irrigation_node_signal_cmd_process();
    }
    return ESP_OK;
}

static esp_err_t storage_irrigation_node_init_actuator_outputs(void) {
    uint64_t mask = 0;
    bool used_gpio[GPIO_NUM_MAX] = {0};

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
        mask |= (1ULL << (uint32_t)cfg->gpio);
    }

    if (mask == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure actuator GPIOs: %s", esp_err_to_name(err));
        return err;
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        s_actuator_runtime[i].cfg = &STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[i];
        s_actuator_runtime[i].state = false;
        gpio_set_level((gpio_num_t)s_actuator_runtime[i].cfg->gpio, 0);
    }
    s_actuator_runtime_count = STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT;
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

static esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state) {
    if (index >= s_actuator_runtime_count || !s_actuator_runtime[index].cfg) {
        return ESP_ERR_NOT_FOUND;
    }
    const storage_irrigation_node_actuator_channel_t *cfg = s_actuator_runtime[index].cfg;
    int level = state ? 1 : 0;
    esp_err_t err = gpio_set_level((gpio_num_t)cfg->gpio, level);
    if (err != ESP_OK) {
        return err;
    }
    s_actuator_runtime[index].state = state;
    return ESP_OK;
}

static bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out) {
    if (!channel || !state_out) {
        return false;
    }
    int index = storage_irrigation_node_find_actuator_index(channel);
    if (index < 0) {
        return false;
    }
    *state_out = s_actuator_runtime[index].state;
    return true;
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
    bool target_state = false;
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

    bool previous_state = s_actuator_runtime[(size_t)actuator_index].state;
    if (strcmp(channel, "pump_main") == 0 && target_state && !storage_irrigation_node_is_main_pump_interlock_satisfied_locked()) {
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
    if (previous_state != target_state) {
        set_err = storage_irrigation_node_set_actuator_state_locked((size_t)actuator_index, target_state);
        if (set_err != ESP_OK) {
            xSemaphoreGive(s_actuator_mutex);
            *response = node_command_handler_create_response(
                cmd_id,
                "ERROR",
                "gpio_write_failed",
                "Failed to set actuator state",
                NULL
            );
            return set_err;
        }
    }

    xSemaphoreGive(s_actuator_mutex);

    cJSON *extra = cJSON_CreateObject();
    if (extra) {
        cJSON_AddBoolToObject(extra, "state", target_state);
        if (previous_state == target_state) {
            cJSON_AddStringToObject(extra, "note", "already_in_requested_state_treated_as_done");
        }
    }
    *response = node_command_handler_create_response(cmd_id, "DONE", NULL, NULL, extra);
    if (extra) {
        cJSON_Delete(extra);
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
    uint64_t mask = 0;
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
        mask |= (1ULL << (uint32_t)gpio);
    }

    if (mask == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = mask,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure level-switch GPIOs: %s", esp_err_to_name(err));
        return err;
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

/**
 * @brief Callback для публикации телеметрии level-switch каналов
 */
esp_err_t storage_irrigation_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;

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
        node_telemetry_publish_custom(sensor->name, sensor->metric, value, raw, false, true);
    }

    storage_irrigation_node_check_fill_completion_events();

    return ESP_OK;
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

    char *json_str = cJSON_PrintUnformatted(payload);
    cJSON_Delete(payload);
    if (!json_str) {
        return ESP_ERR_NO_MEM;
    }
    esp_err_t pub_err = mqtt_manager_publish_raw(topic, json_str, 1, 0);
    free(json_str);
    return pub_err;
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
        bool shutdown_ok = true;
        int valve_solution_fill_idx = storage_irrigation_node_find_actuator_index("valve_solution_fill");
        int valve_clean_supply_idx = storage_irrigation_node_find_actuator_index("valve_clean_supply");
        int pump_main_idx = storage_irrigation_node_find_actuator_index("pump_main");

        if (valve_solution_fill_idx >= 0) {
            esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)valve_solution_fill_idx, false);
            if (stop_err != ESP_OK) {
                shutdown_ok = false;
                ESP_LOGE(TAG, "Failed to stop valve_solution_fill on level_solution_max: %s", esp_err_to_name(stop_err));
            }
        } else {
            shutdown_ok = false;
        }

        if (valve_clean_supply_idx >= 0 && s_actuator_runtime[(size_t)valve_clean_supply_idx].state) {
            esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)valve_clean_supply_idx, false);
            if (stop_err != ESP_OK) {
                shutdown_ok = false;
                ESP_LOGE(TAG, "Failed to stop valve_clean_supply on level_solution_max: %s", esp_err_to_name(stop_err));
            }
        }
        if (pump_main_idx >= 0 && s_actuator_runtime[(size_t)pump_main_idx].state) {
            esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)pump_main_idx, false);
            if (stop_err != ESP_OK) {
                shutdown_ok = false;
                ESP_LOGE(TAG, "Failed to stop pump_main on level_solution_max: %s", esp_err_to_name(stop_err));
            }
        }

        if (shutdown_ok) {
            emit_solution_completed = true;
        }
    }

    xSemaphoreGive(s_actuator_mutex);

    if (emit_clean_completed) {
        (void)storage_irrigation_node_publish_storage_event("clean_fill_completed", NULL);
    }
    if (emit_solution_completed) {
        (void)storage_irrigation_node_publish_storage_event("solution_fill_completed", NULL);
    }
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
                                    float current_ma, bool current_valid) {
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
        cJSON *extra = cJSON_CreateObject();
        if (extra) {
            cJSON_AddNumberToObject(extra, "current_ma", event.current_ma);
            cJSON_AddBoolToObject(extra, "current_valid", event.current_valid);
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
    storage_irrigation_node_schedule_done(cmd.channel_name, cmd.cmd_id, cmd.duration_ms, current_ma, current_valid);
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
    ESP_LOGI(TAG, "Initializing storage_irrigation_node framework integration...");
    
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
    
    // Регистрация обработчиков команд
    err = node_command_handler_register("run_pump", handle_run_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
        return err;
    }

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
    
    ESP_LOGI(TAG, "storage_irrigation_node framework integration initialized");
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
    
    ESP_LOGI(TAG, "MQTT handlers registered via node_framework");
}
