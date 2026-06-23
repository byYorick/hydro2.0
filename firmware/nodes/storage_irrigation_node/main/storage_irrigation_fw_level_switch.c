/**
 * @file storage_irrigation_fw_level_switch.c
 * @brief storage_irrigation_node framework — level_switch module.
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

void storage_irrigation_node_reset_level_switch_event_session(void) {
    memset(g_level_switch_event_initialized, 0, sizeof(g_level_switch_event_initialized));
    memset(g_level_switch_event_published_state, 0, sizeof(g_level_switch_event_published_state));
    g_level_switch_event_time_wait_logged = false;
}

esp_err_t storage_irrigation_node_publish_level_switch_event(
    const storage_irrigation_node_sensor_channel_t *sensor,
    bool state,
    bool initial
) {
    if (!sensor || !sensor->name || sensor->name[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }
    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!node_utils_is_time_synced()) {
        if (!g_level_switch_event_time_wait_logged) {
            ESP_LOGW(TAG, "Level-switch event publish suppressed until time synchronization completes");
            g_level_switch_event_time_wait_logged = true;
        }
        return ESP_ERR_INVALID_STATE;
    }

    g_level_switch_event_time_wait_logged = false;

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
        sensor->name,
        "event"
    );
    if (written <= 0 || (size_t)written >= sizeof(topic)) {
        return ESP_ERR_INVALID_SIZE;
    }

    cJSON *payload = cJSON_CreateObject();
    if (!payload) {
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddStringToObject(payload, "event_code", "level_switch_changed");
    cJSON_AddStringToObject(payload, "channel", sensor->name);
    cJSON_AddBoolToObject(payload, "state", state);
    cJSON_AddBoolToObject(payload, "initial", initial);
    cJSON_AddNumberToObject(payload, "ts", (double)node_utils_get_timestamp_seconds());

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

void storage_irrigation_node_publish_level_switch_events_if_needed(void) {
    bool mqtt_connected = mqtt_manager_is_connected();
    if (!mqtt_connected) {
        if (g_level_switch_event_session_connected) {
            storage_irrigation_node_reset_level_switch_event_session();
            g_level_switch_event_session_connected = false;
        }
        return;
    }

    if (!g_level_switch_event_session_connected) {
        storage_irrigation_node_reset_level_switch_event_session();
        g_level_switch_event_session_connected = true;
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        bool state = storage_irrigation_node_read_level_switch(sensor, NULL) >= 0.5f;
        bool initial = !g_level_switch_event_initialized[sensor->gpio];
        bool changed = initial || (g_level_switch_event_published_state[sensor->gpio] != state);

        if (!changed) {
            continue;
        }

        esp_err_t pub_err = storage_irrigation_node_publish_level_switch_event(sensor, state, initial);
        if (pub_err == ESP_OK) {
            g_level_switch_event_initialized[sensor->gpio] = true;
            g_level_switch_event_published_state[sensor->gpio] = state;
        }
    }
}

esp_err_t storage_irrigation_node_init_level_switch_inputs(void) {
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
            .pull_up_en = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
            .pull_down_en = STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };

        esp_err_t err = gpio_config(&io_conf);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to configure level-switch GPIO for channel %s: %s",
                     sensor->name, esp_err_to_name(err));
            return err;
        }
        ESP_LOGI(
            TAG,
            "level-switch config channel=%s gpio=%d active_low=%d pullup=%d debounce_ms=%lu",
            sensor->name,
            sensor->gpio,
            sensor->active_low ? 1 : 0,
            STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? 1 : 0,
            (unsigned long)STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_MS
        );
    }

    if (!g_level_switch_mutex) {
        g_level_switch_mutex = xSemaphoreCreateMutex();
        if (!g_level_switch_mutex) {
            ESP_LOGE(TAG, "Failed to create level-switch mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    if (xSemaphoreTake(g_level_switch_mutex, pdMS_TO_TICKS(200)) == pdTRUE) {
        int64_t now_us = esp_timer_get_time();
        for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
            const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
            int raw = gpio_get_level((gpio_num_t)sensor->gpio);
            bool active = sensor->active_low ? (raw == 0) : (raw != 0);
            storage_irrigation_node_level_switch_debounce_t *state = &g_level_switch_debounce[sensor->gpio];
            state->initialized = true;
            state->stable_state = active;
            state->candidate_state = active;
            state->candidate_since_us = now_us;
        }
        xSemaphoreGive(g_level_switch_mutex);
    } else {
        ESP_LOGW(TAG, "Level-switch debounce init skipped due to mutex timeout");
    }

    g_level_switch_inputs_ready = true;
    return ESP_OK;
}

float storage_irrigation_node_read_level_switch(
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

    if (g_level_switch_mutex &&
        xSemaphoreTake(g_level_switch_mutex, pdMS_TO_TICKS(20)) == pdTRUE) {
        storage_irrigation_node_level_switch_debounce_t *state = &g_level_switch_debounce[sensor->gpio];
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
        xSemaphoreGive(g_level_switch_mutex);
    }

    if (raw_out) {
        *raw_out = raw;
    }
    return filtered ? 1.0f : 0.0f;
}

esp_err_t storage_irrigation_node_publish_level_switch_telemetry_snapshot(void) {
    if (!g_level_switch_inputs_ready) {
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

        if (!g_sensor_log_initialized[sensor->gpio] || g_sensor_logged_state[sensor->gpio] != active) {
            ESP_LOGI(TAG, "sensor %s: raw=%d active=%d", sensor->name, raw, active ? 1 : 0);
            g_sensor_log_initialized[sensor->gpio] = true;
            g_sensor_logged_state[sensor->gpio] = active;
        }

        esp_err_t pub_err = node_telemetry_publish_custom(sensor->name, sensor->metric,
                                                          value, raw, false, true);
        if (pub_err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to publish level-switch telemetry %s: %s",
                     sensor->name, esp_err_to_name(pub_err));
        }
    }

    return ESP_OK;
}

esp_err_t storage_irrigation_node_sensor_cycle(bool publish_telemetry) {
    (void)publish_telemetry;

    if (!g_level_switch_inputs_ready) {
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

        if (!g_sensor_log_initialized[sensor->gpio] || g_sensor_logged_state[sensor->gpio] != active) {
            ESP_LOGI(TAG, "sensor %s: raw=%d active=%d", sensor->name, raw, active ? 1 : 0);
            g_sensor_log_initialized[sensor->gpio] = true;
            g_sensor_logged_state[sensor->gpio] = active;
        }
    }

    bool estop_pressed = storage_irrigation_node_read_estop_pressed();
    storage_irrigation_node_handle_estop_transition(estop_pressed);
    storage_irrigation_node_publish_level_switch_events_if_needed();
    if (!g_estop_active) {
        storage_irrigation_node_process_fail_safe_guards();
    }
    storage_irrigation_node_update_oled_runtime();

    return ESP_OK;
}

esp_err_t storage_irrigation_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;
    return storage_irrigation_node_publish_level_switch_telemetry_snapshot();
}
