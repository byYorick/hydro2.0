/**
 * @file storage_irrigation_fw_fail_safe.c
 * @brief storage_irrigation_node framework — fail_safe module.
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

void storage_irrigation_node_update_clean_fill_guard_state(bool flow_active, bool paused) {
    if (paused) {
        if (flow_active && g_clean_fill_guard.active && !g_clean_fill_guard.paused_by_estop && g_clean_fill_guard.started_at_us > 0) {
            int64_t delta_us = esp_timer_get_time() - g_clean_fill_guard.started_at_us;
            if (delta_us > 0) {
                uint64_t total_ms = (uint64_t)g_clean_fill_guard.elapsed_before_pause_ms + (uint64_t)(delta_us / 1000LL);
                g_clean_fill_guard.elapsed_before_pause_ms = total_ms > UINT32_MAX ? UINT32_MAX : (uint32_t)total_ms;
            }
            g_clean_fill_guard.started_at_us = 0;
            g_clean_fill_guard.paused_by_estop = true;
        }
        return;
    }

    if (flow_active) {
        if (!g_clean_fill_guard.active) {
            memset(&g_clean_fill_guard, 0, sizeof(g_clean_fill_guard));
            g_clean_fill_guard.active = true;
            g_clean_fill_guard.started_at_us = esp_timer_get_time();
            return;
        }
        if (g_clean_fill_guard.paused_by_estop) {
            g_clean_fill_guard.paused_by_estop = false;
            g_clean_fill_guard.started_at_us = esp_timer_get_time();
        }
        return;
    }

    if (!g_clean_fill_guard.paused_by_estop) {
        memset(&g_clean_fill_guard, 0, sizeof(g_clean_fill_guard));
    }
}

void storage_irrigation_node_update_solution_fill_guard_state(bool flow_active, bool paused) {
    if (paused) {
        if (flow_active && g_solution_fill_guard.active && !g_solution_fill_guard.paused_by_estop && g_solution_fill_guard.started_at_us > 0) {
            int64_t delta_us = esp_timer_get_time() - g_solution_fill_guard.started_at_us;
            if (delta_us > 0) {
                uint64_t total_ms = (uint64_t)g_solution_fill_guard.elapsed_before_pause_ms + (uint64_t)(delta_us / 1000LL);
                g_solution_fill_guard.elapsed_before_pause_ms = total_ms > UINT32_MAX ? UINT32_MAX : (uint32_t)total_ms;
            }
            g_solution_fill_guard.started_at_us = 0;
            g_solution_fill_guard.paused_by_estop = true;
        }
        return;
    }

    if (flow_active) {
        if (!g_solution_fill_guard.active) {
            memset(&g_solution_fill_guard, 0, sizeof(g_solution_fill_guard));
            g_solution_fill_guard.active = true;
            g_solution_fill_guard.started_at_us = esp_timer_get_time();
            return;
        }
        if (g_solution_fill_guard.paused_by_estop) {
            g_solution_fill_guard.paused_by_estop = false;
            g_solution_fill_guard.started_at_us = esp_timer_get_time();
        }
        return;
    }

    if (!g_solution_fill_guard.paused_by_estop) {
        memset(&g_solution_fill_guard, 0, sizeof(g_solution_fill_guard));
    }
}

void storage_irrigation_node_update_binary_guard_state(
    storage_irrigation_node_binary_guard_state_t *state,
    bool flow_active,
    bool paused
) {
    if (!state) {
        return;
    }
    if (paused) {
        if (flow_active && state->active) {
            state->paused_by_estop = true;
        }
        return;
    }
    if (flow_active) {
        if (!state->active) {
            state->active = true;
            state->low_event_emitted = false;
        }
        state->paused_by_estop = false;
        return;
    }
    if (!state->paused_by_estop) {
        memset(state, 0, sizeof(*state));
    }
}

storage_irrigation_node_level_reading_t storage_irrigation_node_read_level_debug_by_name(const char *sensor_name) {
    storage_irrigation_node_level_reading_t reading = {
        .ok = false,
        .raw = -1,
        .active = false,
    };
    if (!sensor_name) {
        return reading;
    }

    if (!g_level_switch_inputs_ready) {
        if (storage_irrigation_node_init_level_switch_inputs() != ESP_OK) {
            return reading;
        }
    }

    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS_COUNT; i++) {
        const storage_irrigation_node_sensor_channel_t *sensor = &STORAGE_IRRIGATION_NODE_SENSOR_CHANNELS[i];
        if (strcmp(sensor->name, sensor_name) != 0) {
            continue;
        }
        int raw = gpio_get_level((gpio_num_t)sensor->gpio);
        reading.raw = raw;
        reading.active = storage_irrigation_node_read_level_switch(sensor, NULL) >= 0.5f;
        reading.ok = true;
        return reading;
    }

    return reading;
}

storage_irrigation_node_level_debug_snapshot_t storage_irrigation_node_read_level_debug_snapshot(void) {
    storage_irrigation_node_level_debug_snapshot_t levels = {
        .clean_min = storage_irrigation_node_read_level_debug_by_name("level_clean_min"),
        .clean_max = storage_irrigation_node_read_level_debug_by_name("level_clean_max"),
        .solution_min = storage_irrigation_node_read_level_debug_by_name("level_solution_min"),
        .solution_max = storage_irrigation_node_read_level_debug_by_name("level_solution_max"),
    };
    return levels;
}

void storage_irrigation_node_add_level_debug(cJSON *levels, const char *name, storage_irrigation_node_level_reading_t reading) {
    if (!levels || !name) {
        return;
    }
    cJSON *entry = cJSON_CreateObject();
    if (!entry) {
        return;
    }
    cJSON_AddBoolToObject(entry, "ok", reading.ok);
    cJSON_AddNumberToObject(entry, "raw_gpio", reading.raw);
    cJSON_AddBoolToObject(entry, "active", reading.active);
    cJSON_AddItemToObject(levels, name, entry);
}

cJSON *storage_irrigation_node_build_fail_safe_details(
    const char *guard_name,
    const char *trigger,
    const storage_irrigation_node_level_debug_snapshot_t *levels,
    uint32_t elapsed_ms,
    uint32_t delay_ms,
    bool clean_fill_active,
    bool solution_fill_active,
    bool recirculation_active,
    bool irrigation_active
) {
    cJSON *details = cJSON_CreateObject();
    if (!details) {
        return NULL;
    }

    cJSON_AddStringToObject(details, "source", "firmware_fail_safe_guard");
    cJSON_AddStringToObject(details, "guard", guard_name ? guard_name : "unknown");
    cJSON_AddStringToObject(details, "trigger", trigger ? trigger : "unknown");
    cJSON_AddNumberToObject(details, "elapsed_ms", (double)elapsed_ms);
    cJSON_AddNumberToObject(details, "delay_ms", (double)delay_ms);
    cJSON_AddBoolToObject(details, "level_switch_active_low", STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW ? true : false);
    cJSON_AddBoolToObject(details, "level_switch_pullup", STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? true : false);

    cJSON *flow = cJSON_CreateObject();
    if (flow) {
        cJSON_AddBoolToObject(flow, "clean_fill_active", clean_fill_active);
        cJSON_AddBoolToObject(flow, "solution_fill_active", solution_fill_active);
        cJSON_AddBoolToObject(flow, "recirculation_active", recirculation_active);
        cJSON_AddBoolToObject(flow, "irrigation_active", irrigation_active);
        cJSON_AddItemToObject(details, "flow", flow);
    }

    if (levels) {
        cJSON *level_json = cJSON_CreateObject();
        if (level_json) {
            storage_irrigation_node_add_level_debug(level_json, "level_clean_min", levels->clean_min);
            storage_irrigation_node_add_level_debug(level_json, "level_clean_max", levels->clean_max);
            storage_irrigation_node_add_level_debug(level_json, "level_solution_min", levels->solution_min);
            storage_irrigation_node_add_level_debug(level_json, "level_solution_max", levels->solution_max);
            cJSON_AddItemToObject(details, "levels", level_json);
        }
    }

    return details;
}

void storage_irrigation_node_log_fail_safe_trip(
    const char *event_code,
    const char *trigger,
    const storage_irrigation_node_level_debug_snapshot_t *levels,
    uint32_t elapsed_ms,
    uint32_t delay_ms
) {
    if (!levels) {
        return;
    }
    ESP_LOGW(
        TAG,
        "fail-safe trip event=%s trigger=%s elapsed_ms=%lu delay_ms=%lu "
        "active_low=%d pullup=%d "
        "clean_min(raw=%d active=%d ok=%d) clean_max(raw=%d active=%d ok=%d) "
        "solution_min(raw=%d active=%d ok=%d) solution_max(raw=%d active=%d ok=%d)",
        event_code ? event_code : "unknown",
        trigger ? trigger : "unknown",
        (unsigned long)elapsed_ms,
        (unsigned long)delay_ms,
        STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW ? 1 : 0,
        STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? 1 : 0,
        levels->clean_min.raw,
        levels->clean_min.active ? 1 : 0,
        levels->clean_min.ok ? 1 : 0,
        levels->clean_max.raw,
        levels->clean_max.active ? 1 : 0,
        levels->clean_max.ok ? 1 : 0,
        levels->solution_min.raw,
        levels->solution_min.active ? 1 : 0,
        levels->solution_min.ok ? 1 : 0,
        levels->solution_max.raw,
        levels->solution_max.active ? 1 : 0,
        levels->solution_max.ok ? 1 : 0
    );
}

void storage_irrigation_node_log_fail_safe_config(void) {
    ESP_LOGI(
        TAG,
        "fail-safe config: clean_fill_min_check_delay_ms=%lu "
        "solution_fill_clean_min_check_delay_ms=%lu "
        "solution_fill_solution_min_check_delay_ms=%lu "
        "recirculation_solution_min_guard_enabled=%d "
        "irrigation_solution_min_guard_enabled=%d estop_debounce_ms=%lu "
        "level_switch_active_low=%d level_switch_pullup=%d debounce_ms=%lu",
        (unsigned long)g_fail_safe_config.clean_fill_min_check_delay_ms,
        (unsigned long)g_fail_safe_config.solution_fill_clean_min_check_delay_ms,
        (unsigned long)g_fail_safe_config.solution_fill_solution_min_check_delay_ms,
        g_fail_safe_config.recirculation_solution_min_guard_enabled ? 1 : 0,
        g_fail_safe_config.irrigation_solution_min_guard_enabled ? 1 : 0,
        (unsigned long)g_fail_safe_config.estop_debounce_ms,
        STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_ACTIVE_LOW ? 1 : 0,
        STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_PULLUP ? 1 : 0,
        (unsigned long)STORAGE_IRRIGATION_NODE_LEVEL_SWITCH_DEBOUNCE_MS
    );
}

void storage_irrigation_node_reload_fail_safe_config_from_storage(void) {
    storage_irrigation_node_fail_safe_config_t next = {
        .clean_fill_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_CLEAN_FILL_MIN_CHECK_DELAY_MS,
        .solution_fill_clean_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_SOLUTION_FILL_CLEAN_MIN_CHECK_DELAY_MS,
        .solution_fill_solution_min_check_delay_ms = STORAGE_IRRIGATION_NODE_FAIL_SAFE_SOLUTION_FILL_SOLUTION_MIN_CHECK_DELAY_MS,
        .recirculation_solution_min_guard_enabled = STORAGE_IRRIGATION_NODE_FAIL_SAFE_RECIRCULATION_STOP_ON_SOLUTION_MIN,
        .irrigation_solution_min_guard_enabled = STORAGE_IRRIGATION_NODE_FAIL_SAFE_IRRIGATION_STOP_ON_SOLUTION_MIN,
        .estop_debounce_ms = STORAGE_IRRIGATION_NODE_ESTOP_DEBOUNCE_MS,
    };

    char config_json[CONFIG_STORAGE_MAX_JSON_SIZE] = {0};
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        g_fail_safe_config = next;
        return;
    }

    cJSON *root = cJSON_Parse(config_json);
    if (!root) {
        g_fail_safe_config = next;
        return;
    }

    const cJSON *guards = cJSON_GetObjectItem(root, "fail_safe_guards");
    if (guards && cJSON_IsObject(guards)) {
        const cJSON *item = cJSON_GetObjectItem(guards, "clean_fill_min_check_delay_ms");
        if (item && cJSON_IsNumber(item)) {
            double value = cJSON_GetNumberValue(item);
            if (value >= 0.0 && value <= 3600000.0) {
                next.clean_fill_min_check_delay_ms = (uint32_t)value;
            }
        }
        item = cJSON_GetObjectItem(guards, "solution_fill_clean_min_check_delay_ms");
        if (item && cJSON_IsNumber(item)) {
            double value = cJSON_GetNumberValue(item);
            if (value >= 0.0 && value <= 3600000.0) {
                next.solution_fill_clean_min_check_delay_ms = (uint32_t)value;
            }
        }
        item = cJSON_GetObjectItem(guards, "solution_fill_solution_min_check_delay_ms");
        if (item && cJSON_IsNumber(item)) {
            double value = cJSON_GetNumberValue(item);
            if (value >= 0.0 && value <= 3600000.0) {
                next.solution_fill_solution_min_check_delay_ms = (uint32_t)value;
            }
        }
        item = cJSON_GetObjectItem(guards, "recirculation_solution_min_guard_enabled");
        if (item && cJSON_IsBool(item)) {
            next.recirculation_solution_min_guard_enabled = cJSON_IsTrue(item);
        }
        item = cJSON_GetObjectItem(guards, "irrigation_solution_min_guard_enabled");
        if (item && cJSON_IsBool(item)) {
            next.irrigation_solution_min_guard_enabled = cJSON_IsTrue(item);
        }
        item = cJSON_GetObjectItem(guards, "estop_debounce_ms");
        if (item && cJSON_IsNumber(item)) {
            double value = cJSON_GetNumberValue(item);
            if (value >= 20.0 && value <= 5000.0) {
                next.estop_debounce_ms = (uint32_t)value;
            }
        }
    }

    cJSON_Delete(root);
    g_fail_safe_config = next;
}

esp_err_t storage_irrigation_node_init_estop_input(void) {
    if (g_estop_input_ready) {
        return ESP_OK;
    }

    if (!GPIO_IS_VALID_GPIO(STORAGE_IRRIGATION_NODE_ESTOP_GPIO)) {
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << (uint32_t)STORAGE_IRRIGATION_NODE_ESTOP_GPIO),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = STORAGE_IRRIGATION_NODE_ESTOP_ACTIVE_LOW ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = STORAGE_IRRIGATION_NODE_ESTOP_ACTIVE_LOW ? GPIO_PULLDOWN_DISABLE : GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        return err;
    }

    int raw = gpio_get_level((gpio_num_t)STORAGE_IRRIGATION_NODE_ESTOP_GPIO);
    bool pressed = STORAGE_IRRIGATION_NODE_ESTOP_ACTIVE_LOW ? (raw == 0) : (raw != 0);
    g_estop_debounce.initialized = true;
    g_estop_debounce.pressed = pressed;
    g_estop_debounce.candidate_pressed = pressed;
    g_estop_debounce.candidate_since_us = esp_timer_get_time();
    g_estop_input_ready = true;
    return ESP_OK;
}

bool storage_irrigation_node_read_estop_pressed(void) {
    if (!g_estop_input_ready && storage_irrigation_node_init_estop_input() != ESP_OK) {
        return false;
    }

    int raw = gpio_get_level((gpio_num_t)STORAGE_IRRIGATION_NODE_ESTOP_GPIO);
    bool pressed = STORAGE_IRRIGATION_NODE_ESTOP_ACTIVE_LOW ? (raw == 0) : (raw != 0);
    int64_t now_us = esp_timer_get_time();
    int64_t debounce_us = (int64_t)(g_fail_safe_config.estop_debounce_ms > 0 ? g_fail_safe_config.estop_debounce_ms : STORAGE_IRRIGATION_NODE_ESTOP_DEBOUNCE_MS) * 1000LL;

    if (!g_estop_debounce.initialized) {
        g_estop_debounce.initialized = true;
        g_estop_debounce.pressed = pressed;
        g_estop_debounce.candidate_pressed = pressed;
        g_estop_debounce.candidate_since_us = now_us;
        return pressed;
    }

    if (pressed != g_estop_debounce.pressed) {
        if (pressed != g_estop_debounce.candidate_pressed) {
            g_estop_debounce.candidate_pressed = pressed;
            g_estop_debounce.candidate_since_us = now_us;
        } else if ((now_us - g_estop_debounce.candidate_since_us) >= debounce_us) {
            g_estop_debounce.pressed = g_estop_debounce.candidate_pressed;
        }
    } else {
        g_estop_debounce.candidate_pressed = pressed;
        g_estop_debounce.candidate_since_us = now_us;
    }

    return g_estop_debounce.pressed;
}

bool storage_irrigation_node_restore_estop_snapshot_locked(void) {
    if (!g_estop_restore_valid) {
        return true;
    }

    static const char *restore_order[] = {
        "valve_clean_fill",
        "valve_clean_supply",
        "valve_solution_fill",
        "valve_solution_supply",
        "valve_irrigation",
        "pump_main",
    };

    bool all_ok = true;
    for (size_t i = 0; i < sizeof(restore_order) / sizeof(restore_order[0]); i++) {
        int idx = storage_irrigation_node_find_actuator_index(restore_order[i]);
        if (idx < 0) {
            all_ok = false;
            continue;
        }
        if (!g_estop_restore_states[idx]) {
            continue;
        }
        esp_err_t set_err = storage_irrigation_node_set_actuator_state_locked((size_t)idx, true);
        if (set_err != ESP_OK) {
            all_ok = false;
            ESP_LOGE(TAG, "Failed to restore actuator after e-stop: %s (%s)", restore_order[i], esp_err_to_name(set_err));
        }
    }
    return all_ok;
}

void storage_irrigation_node_handle_estop_transition(bool pressed) {
    if (pressed == g_estop_active) {
        if (pressed && g_actuator_mutex && xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            (void)storage_irrigation_node_stop_all_paths_locked();
            xSemaphoreGive(g_actuator_mutex);
        }
        return;
    }

    if (!g_actuator_mutex || xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to acquire actuator lock for e-stop transition");
        return;
    }

    if (pressed) {
        memset(g_estop_restore_states, 0, sizeof(g_estop_restore_states));
        for (size_t i = 0; i < g_actuator_runtime_count; i++) {
            const storage_irrigation_node_actuator_channel_t *cfg = g_actuator_runtime[i].cfg;
            bool state = false;
            if (cfg && storage_irrigation_node_get_actuator_state_locked(cfg->name, &state)) {
                g_estop_restore_states[i] = state;
            }
        }
        g_estop_restore_valid = true;
        storage_irrigation_node_pause_stage_guards_locked();
        storage_irrigation_node_update_clean_fill_guard_state(storage_irrigation_node_is_clean_fill_active_locked(), true);
        storage_irrigation_node_update_solution_fill_guard_state(storage_irrigation_node_is_solution_fill_active_locked(), true);
        storage_irrigation_node_update_binary_guard_state(&g_recirculation_guard, storage_irrigation_node_is_prepare_recirculation_active_locked(), true);
        storage_irrigation_node_update_binary_guard_state(&g_irrigation_guard, storage_irrigation_node_is_irrigation_active_locked(), true);
        (void)storage_irrigation_node_stop_all_paths_locked();
        g_estop_active = true;
        xSemaphoreGive(g_actuator_mutex);
        storage_irrigation_node_update_oled_runtime();
        (void)storage_irrigation_node_publish_storage_event("emergency_stop_activated", NULL);
        return;
    }

    g_estop_active = false;
    bool restored = storage_irrigation_node_restore_estop_snapshot_locked();
    storage_irrigation_node_resume_stage_guards_locked();
    bool clean_fill_active = storage_irrigation_node_is_clean_fill_active_locked();
    bool solution_fill_active = storage_irrigation_node_is_solution_fill_active_locked();
    bool recirculation_active = storage_irrigation_node_is_prepare_recirculation_active_locked();
    bool irrigation_active = storage_irrigation_node_is_irrigation_active_locked();
    storage_irrigation_node_update_clean_fill_guard_state(clean_fill_active, false);
    storage_irrigation_node_update_solution_fill_guard_state(solution_fill_active, false);
    storage_irrigation_node_update_binary_guard_state(&g_recirculation_guard, recirculation_active, false);
    storage_irrigation_node_update_binary_guard_state(&g_irrigation_guard, irrigation_active, false);
    g_estop_restore_valid = false;
    xSemaphoreGive(g_actuator_mutex);

    if (!restored) {
        node_state_manager_report_error(ERROR_LEVEL_WARNING, "emergency_stop", ESP_FAIL, "Failed to restore one or more actuators after e-stop release");
    }
    storage_irrigation_node_update_oled_runtime();
}

void storage_irrigation_node_process_fail_safe_guards(void) {
    const char *events[5] = {0};
    cJSON *event_details[5] = {0};
    size_t event_count = 0;
    bool clean_level_min = false;
    bool clean_level_max = false;
    bool solution_level_min = false;
    bool solution_level_max = false;
    bool clean_level_min_ok = storage_irrigation_node_read_switch_state_by_name("level_clean_min", &clean_level_min);
    bool clean_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_clean_max", &clean_level_max);
    bool solution_level_min_ok = storage_irrigation_node_read_switch_state_by_name("level_solution_min", &solution_level_min);
    bool solution_level_max_ok = storage_irrigation_node_read_switch_state_by_name("level_solution_max", &solution_level_max);
    storage_irrigation_node_level_debug_snapshot_t level_debug = storage_irrigation_node_read_level_debug_snapshot();

    if (!g_actuator_mutex || xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(200)) != pdTRUE) {
        return;
    }

    bool clean_fill_active = storage_irrigation_node_is_clean_fill_active_locked();
    bool solution_fill_active = storage_irrigation_node_is_solution_fill_active_locked();
    bool recirculation_active = storage_irrigation_node_is_prepare_recirculation_active_locked();
    bool irrigation_active = storage_irrigation_node_is_irrigation_active_locked();

    storage_irrigation_node_update_clean_fill_guard_state(clean_fill_active, false);
    storage_irrigation_node_update_solution_fill_guard_state(solution_fill_active, false);
    storage_irrigation_node_update_binary_guard_state(&g_recirculation_guard, recirculation_active, false);
    storage_irrigation_node_update_binary_guard_state(&g_irrigation_guard, irrigation_active, false);

    const bool clean_fill_fs_suppressed = storage_irrigation_node_valve_clean_fill_transient_timer_armed();

    /* clean_fill: не останавливаем по level_clean_min=0 — при пустом баке min активируется
     * только после подъёма уровня; ранний guard давал ложный clean_fill_source_empty и цикл
     * 5с ON / 5с OFF. Завершение только по level_clean_max; пустой источник — через AE3 timeout. */
    if (clean_fill_active && !g_clean_fill_guard.terminal_event_emitted && !clean_fill_fs_suppressed) {
        if (clean_fill_active &&
            clean_level_max_ok &&
            clean_level_max &&
            storage_irrigation_node_stop_clean_fill_path_locked()) {
            g_clean_fill_guard.terminal_event_emitted = true;
            uint32_t elapsed_ms = storage_irrigation_node_clean_fill_elapsed_ms();
            storage_irrigation_node_log_fail_safe_trip(
                "clean_fill_completed",
                "level_clean_max",
                &level_debug,
                elapsed_ms,
                0
            );
            event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
                "clean_fill",
                "level_clean_max",
                &level_debug,
                elapsed_ms,
                0,
                clean_fill_active,
                solution_fill_active,
                recirculation_active,
                irrigation_active
            );
            events[event_count++] = "clean_fill_completed";
        }
    }

    if (solution_fill_active && !g_solution_fill_guard.terminal_event_emitted) {
        if (!g_solution_fill_guard.clean_min_check_completed &&
            storage_irrigation_node_solution_fill_elapsed_ms() >= g_fail_safe_config.solution_fill_clean_min_check_delay_ms) {
            uint32_t elapsed_ms = storage_irrigation_node_solution_fill_elapsed_ms();
            g_solution_fill_guard.clean_min_check_completed = true;
            if (clean_level_min_ok && !clean_level_min && storage_irrigation_node_stop_stage_path_locked("solution_fill")) {
                g_solution_fill_guard.terminal_event_emitted = true;
                storage_irrigation_node_log_fail_safe_trip(
                    "solution_fill_source_empty",
                    "level_clean_min",
                    &level_debug,
                    elapsed_ms,
                    g_fail_safe_config.solution_fill_clean_min_check_delay_ms
                );
                event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
                    "solution_fill",
                    "level_clean_min",
                    &level_debug,
                    elapsed_ms,
                    g_fail_safe_config.solution_fill_clean_min_check_delay_ms,
                    clean_fill_active,
                    solution_fill_active,
                    recirculation_active,
                    irrigation_active
                );
                events[event_count++] = "solution_fill_source_empty";
                solution_fill_active = false;
            }
        }

        if (solution_fill_active &&
            !g_solution_fill_guard.solution_min_check_completed &&
            storage_irrigation_node_solution_fill_elapsed_ms() >= g_fail_safe_config.solution_fill_solution_min_check_delay_ms) {
            uint32_t elapsed_ms = storage_irrigation_node_solution_fill_elapsed_ms();
            g_solution_fill_guard.solution_min_check_completed = true;
            if (solution_level_min_ok && !solution_level_min && storage_irrigation_node_stop_stage_path_locked("solution_fill")) {
                g_solution_fill_guard.terminal_event_emitted = true;
                storage_irrigation_node_log_fail_safe_trip(
                    "solution_fill_leak_detected",
                    "level_solution_min",
                    &level_debug,
                    elapsed_ms,
                    g_fail_safe_config.solution_fill_solution_min_check_delay_ms
                );
                event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
                    "solution_fill",
                    "level_solution_min",
                    &level_debug,
                    elapsed_ms,
                    g_fail_safe_config.solution_fill_solution_min_check_delay_ms,
                    clean_fill_active,
                    solution_fill_active,
                    recirculation_active,
                    irrigation_active
                );
                events[event_count++] = "solution_fill_leak_detected";
                solution_fill_active = false;
            }
        }

        if (solution_fill_active &&
            solution_level_max_ok &&
            solution_level_max &&
            storage_irrigation_node_stop_stage_path_locked("solution_fill")) {
            g_solution_fill_guard.terminal_event_emitted = true;
            uint32_t elapsed_ms = storage_irrigation_node_solution_fill_elapsed_ms();
            storage_irrigation_node_log_fail_safe_trip(
                "solution_fill_completed",
                "level_solution_max",
                &level_debug,
                elapsed_ms,
                0
            );
            event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
                "solution_fill",
                "level_solution_max",
                &level_debug,
                elapsed_ms,
                0,
                clean_fill_active,
                solution_fill_active,
                recirculation_active,
                irrigation_active
            );
            events[event_count++] = "solution_fill_completed";
        }
    }

    if (recirculation_active &&
        g_fail_safe_config.recirculation_solution_min_guard_enabled &&
        !g_recirculation_guard.low_event_emitted &&
        solution_level_min_ok &&
        !solution_level_min &&
        storage_irrigation_node_stop_stage_path_locked("prepare_recirculation")) {
        g_recirculation_guard.low_event_emitted = true;
        storage_irrigation_node_log_fail_safe_trip(
            "recirculation_solution_low",
            "level_solution_min",
            &level_debug,
            0,
            0
        );
        event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
            "prepare_recirculation",
            "level_solution_min",
            &level_debug,
            0,
            0,
            clean_fill_active,
            solution_fill_active,
            recirculation_active,
            irrigation_active
        );
        events[event_count++] = "recirculation_solution_low";
    }

    if (irrigation_active &&
        g_fail_safe_config.irrigation_solution_min_guard_enabled &&
        !g_irrigation_guard.low_event_emitted &&
        solution_level_min_ok &&
        !solution_level_min &&
        storage_irrigation_node_stop_irrigation_path_locked()) {
        g_irrigation_guard.low_event_emitted = true;
        storage_irrigation_node_log_fail_safe_trip(
            "irrigation_solution_low",
            "level_solution_min",
            &level_debug,
            0,
            0
        );
        event_details[event_count] = storage_irrigation_node_build_fail_safe_details(
            "irrigation",
            "level_solution_min",
            &level_debug,
            0,
            0,
            clean_fill_active,
            solution_fill_active,
            recirculation_active,
            irrigation_active
        );
        events[event_count++] = "irrigation_solution_low";
    }

    xSemaphoreGive(g_actuator_mutex);

    for (size_t i = 0; i < event_count; i++) {
        (void)storage_irrigation_node_publish_storage_event_with_details(events[i], NULL, event_details[i]);
        event_details[i] = NULL;
    }
}
