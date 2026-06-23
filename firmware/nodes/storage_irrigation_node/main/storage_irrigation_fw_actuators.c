/**
 * @file storage_irrigation_fw_actuators.c
 * @brief storage_irrigation_node framework — actuators module.
 */

#include "storage_irrigation_fw_internal.h"
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
#include "config_storage.h"
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
#include <stdio.h>
#include <math.h>


static const char *TAG = STORAGE_IRRIGATION_FW_TAG;

esp_err_t storage_irrigation_node_init_channel_callback(const char *channel_name, const cJSON *channel_config, void *user_ctx) {
    (void)user_ctx;
    
    if (channel_config == NULL || channel_name == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Инициализация насосов обрабатывается через config_apply_channels_pump
    // Этот callback вызывается для каждого канала, но насосы инициализируются централизованно
    ESP_LOGD(TAG, "Channel init callback for: %s", channel_name);
    
    return ESP_OK;
}

esp_err_t storage_irrigation_node_init_actuator_outputs(void) {
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

    g_actuator_runtime_count = STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT;
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS_COUNT; i++) {
        g_actuator_runtime[i].cfg = &STORAGE_IRRIGATION_NODE_ACTUATOR_CHANNELS[i];
        g_actuator_runtime[i].state = false;
        (void)storage_irrigation_node_refresh_actuator_state_locked(i);
    }
    return ESP_OK;
}

bool storage_irrigation_node_refresh_actuator_state_locked(size_t index) {
    if (index >= g_actuator_runtime_count || !g_actuator_runtime[index].cfg) {
        return false;
    }

    pump_driver_state_t driver_state = PUMP_STATE_OFF;
    if (pump_driver_get_state(g_actuator_runtime[index].cfg->name, &driver_state) != ESP_OK) {
        return false;
    }

    g_actuator_runtime[index].state = (driver_state == PUMP_STATE_ON);
    return true;
}

const char *storage_irrigation_node_canonical_actuator_channel(const char *name) {
    if (!name) {
        return NULL;
    }
    if (strcmp(name, "main_pump") == 0) {
        return "pump_main";
    }
    return name;
}

bool storage_irrigation_node_is_main_pump_channel(const char *channel) {
    const char *c = storage_irrigation_node_canonical_actuator_channel(channel);
    return c != NULL && strcmp(c, "pump_main") == 0;
}

int storage_irrigation_node_find_actuator_index(const char *channel) {
    if (!channel || channel[0] == '\0') {
        return -1;
    }
    const char *canonical = storage_irrigation_node_canonical_actuator_channel(channel);
    for (size_t i = 0; i < g_actuator_runtime_count; i++) {
        const storage_irrigation_node_actuator_channel_t *cfg = g_actuator_runtime[i].cfg;
        if (cfg && cfg->name && strcmp(cfg->name, canonical) == 0) {
            return (int)i;
        }
    }
    return -1;
}

bool storage_irrigation_node_parse_relay_state(const cJSON *item, bool *state_out) {
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

bool storage_irrigation_node_parse_timeout_ms(const cJSON *item, uint32_t *timeout_ms_out) {
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

bool storage_irrigation_node_parse_duration_ms(const cJSON *item, uint32_t *duration_ms_out) {
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

bool storage_irrigation_node_parse_stage_name(const cJSON *item, char *stage_out, size_t stage_out_size) {
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

esp_err_t storage_irrigation_node_set_actuator_state_locked(size_t index, bool state) {
    if (index >= g_actuator_runtime_count || !g_actuator_runtime[index].cfg) {
        return ESP_ERR_NOT_FOUND;
    }

    const storage_irrigation_node_actuator_channel_t *cfg = g_actuator_runtime[index].cfg;
    esp_err_t err = state
        ? pump_driver_set_state(cfg->name, true)
        : pump_driver_stop(cfg->name);

    if (err == ESP_OK) {
        (void)storage_irrigation_node_refresh_actuator_state_locked(index);
        return ESP_OK;
    }

    if (!state && err == ESP_ERR_INVALID_STATE) {
        bool refreshed = storage_irrigation_node_refresh_actuator_state_locked(index);
        if (refreshed && !g_actuator_runtime[index].state) {
            return ESP_OK;
        }
    }

    return err;
}

bool storage_irrigation_node_get_actuator_state_locked(const char *channel, bool *state_out) {
    if (!channel || !state_out) {
        return false;
    }
    int index = storage_irrigation_node_find_actuator_index(channel);
    if (index < 0) {
        return false;
    }
    (void)storage_irrigation_node_refresh_actuator_state_locked((size_t)index);
    *state_out = g_actuator_runtime[index].state;
    return true;
}

bool storage_irrigation_node_is_pump_main_dry_run_allowed(const char *channel, bool target_state, bool has_duration, uint32_t duration_ms) {
    return channel
        && storage_irrigation_node_is_main_pump_channel(channel)
        && target_state
        && has_duration
        && duration_ms > 0
        && duration_ms <= STORAGE_IRRIGATION_NODE_PUMP_MAIN_DRY_RUN_MAX_MS;
}

bool storage_irrigation_node_is_clean_fill_active_locked(void) {
    bool valve_clean_fill = false;
    if (!storage_irrigation_node_get_actuator_state_locked("valve_clean_fill", &valve_clean_fill)) {
        return false;
    }
    return valve_clean_fill;
}

bool storage_irrigation_node_is_solution_fill_active_locked(void) {
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

bool storage_irrigation_node_is_prepare_recirculation_active_locked(void) {
    bool pump_main = false;
    bool valve_solution_supply = false;
    bool valve_solution_fill = false;
    if (!storage_irrigation_node_get_actuator_state_locked("pump_main", &pump_main)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &valve_solution_supply)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &valve_solution_fill)) {
        return false;
    }
    return pump_main && valve_solution_supply && valve_solution_fill;
}

bool storage_irrigation_node_is_irrigation_active_locked(void) {
    bool pump_main = false;
    bool valve_solution_supply = false;
    bool valve_irrigation = false;
    if (!storage_irrigation_node_get_actuator_state_locked("pump_main", &pump_main)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &valve_solution_supply)) {
        return false;
    }
    if (!storage_irrigation_node_get_actuator_state_locked("valve_irrigation", &valve_irrigation)) {
        return false;
    }
    return pump_main && valve_solution_supply && valve_irrigation;
}

uint32_t storage_irrigation_node_clean_fill_elapsed_ms(void) {
    uint32_t elapsed_ms = g_clean_fill_guard.elapsed_before_pause_ms;
    if (!g_clean_fill_guard.active || g_clean_fill_guard.paused_by_estop || g_clean_fill_guard.started_at_us <= 0) {
        return elapsed_ms;
    }
    int64_t delta_us = esp_timer_get_time() - g_clean_fill_guard.started_at_us;
    if (delta_us <= 0) {
        return elapsed_ms;
    }
    uint64_t total_ms = (uint64_t)elapsed_ms + (uint64_t)(delta_us / 1000LL);
    return total_ms > UINT32_MAX ? UINT32_MAX : (uint32_t)total_ms;
}

uint32_t storage_irrigation_node_solution_fill_elapsed_ms(void) {
    uint32_t elapsed_ms = g_solution_fill_guard.elapsed_before_pause_ms;
    if (!g_solution_fill_guard.active || g_solution_fill_guard.paused_by_estop || g_solution_fill_guard.started_at_us <= 0) {
        return elapsed_ms;
    }
    int64_t delta_us = esp_timer_get_time() - g_solution_fill_guard.started_at_us;
    if (delta_us <= 0) {
        return elapsed_ms;
    }
    uint64_t total_ms = (uint64_t)elapsed_ms + (uint64_t)(delta_us / 1000LL);
    return total_ms > UINT32_MAX ? UINT32_MAX : (uint32_t)total_ms;
}

bool storage_irrigation_node_is_main_pump_interlock_satisfied_locked(void) {
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

void storage_irrigation_node_append_main_pump_interlock_error(cJSON *details) {
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

bool storage_irrigation_node_read_switch_state_by_name(const char *sensor_name, bool *state_out) {
    if (!sensor_name || !state_out) {
        return false;
    }

    if (!g_level_switch_inputs_ready) {
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

void storage_irrigation_node_oled_push_bool_channel(
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

void storage_irrigation_node_update_oled_runtime(void) {
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

    if (g_actuator_mutex && xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
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
        xSemaphoreGive(g_actuator_mutex);
    }

    if (channel_index == 0) {
        return;
    }

    model.channel_count = channel_index;
    (void)oled_ui_update_model(&model);
}

cJSON *storage_irrigation_node_build_irr_state_snapshot(void) {
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

    if (g_actuator_mutex && xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        bool ok = true;
        ok = storage_irrigation_node_get_actuator_state_locked("pump_main", &pump_main) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_clean_fill", &valve_clean_fill) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_clean_supply", &valve_clean_supply) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_solution_fill", &valve_solution_fill) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_solution_supply", &valve_solution_supply) && ok;
        ok = storage_irrigation_node_get_actuator_state_locked("valve_irrigation", &valve_irrigation) && ok;
        actuators_ok = ok;
        xSemaphoreGive(g_actuator_mutex);
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

cJSON *storage_irrigation_node_build_legacy_state_payload(void) {
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

const storage_irrigation_node_sensor_channel_t *storage_irrigation_node_find_sensor_cfg(const char *channel) {
    if (!channel || channel[0] == '\0') {
        return NULL;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        if (strcmp(STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i].name, channel) == 0) {
            return &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        }
    }
    return NULL;
}
