/**
 * @file storage_irrigation_fw_stage_guards.c
 * @brief storage_irrigation_node framework — stage_guards module.
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

storage_irrigation_node_stage_guard_t *storage_irrigation_node_get_stage_guard(const char *stage, bool create) {
    if (!stage || stage[0] == '\0') {
        return NULL;
    }
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        if (g_stage_guards[i].stage[0] != '\0' && strcmp(g_stage_guards[i].stage, stage) == 0) {
            return &g_stage_guards[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        if (g_stage_guards[i].stage[0] != '\0') {
            continue;
        }
        strncpy(g_stage_guards[i].stage, stage, sizeof(g_stage_guards[i].stage) - 1);
        g_stage_guards[i].timer = xTimerCreate(
            "irr_stage_guard",
            pdMS_TO_TICKS(1000),
            pdFALSE,
            &g_stage_guards[i],
            storage_irrigation_node_stage_guard_timer_cb
        );
        if (!g_stage_guards[i].timer) {
            g_stage_guards[i].stage[0] = '\0';
            return NULL;
        }
        return &g_stage_guards[i];
    }
    return NULL;
}

esp_err_t storage_irrigation_node_arm_stage_guard_locked(const char *stage, const char *cmd_id, uint32_t timeout_ms) {
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

bool storage_irrigation_node_complete_stage_guard_for_channel_locked(const char *channel, char *cmd_id_out, size_t cmd_id_out_size) {
    if (cmd_id_out && cmd_id_out_size > 0) {
        cmd_id_out[0] = '\0';
    }
    if (!channel || !storage_irrigation_node_is_main_pump_channel(channel)) {
        return false;
    }
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &g_stage_guards[i];
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

bool storage_irrigation_node_complete_stage_guard_for_stage_locked(const char *stage, char *cmd_id_out, size_t cmd_id_out_size) {
    if (cmd_id_out && cmd_id_out_size > 0) {
        cmd_id_out[0] = '\0';
    }
    if (!stage || stage[0] == '\0') {
        return false;
    }
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &g_stage_guards[i];
        if (!guard->active || strcmp(guard->stage, stage) != 0) {
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

bool storage_irrigation_node_stop_stage_path_locked(const char *stage) {
    const char *channels[3] = {0};
    size_t count = 0;
    if (!stage) {
        return false;
    }
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
    if (all_ok) {
        (void)storage_irrigation_node_complete_stage_guard_for_stage_locked(stage, NULL, 0);
    }
    return all_ok;
}

bool storage_irrigation_node_stop_clean_fill_path_locked(void) {
    int idx = storage_irrigation_node_find_actuator_index("valve_clean_fill");
    if (idx < 0) {
        return false;
    }
    esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)idx, false);
    if (stop_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to stop clean fill path: %s", esp_err_to_name(stop_err));
        return false;
    }
    (void)storage_irrigation_node_complete_stage_guard_for_stage_locked("clean_fill", NULL, 0);
    return true;
}

bool storage_irrigation_node_stop_irrigation_path_locked(void) {
    const char *channels[] = {"pump_main", "valve_irrigation", "valve_solution_supply"};
    bool all_ok = true;
    for (size_t i = 0; i < sizeof(channels) / sizeof(channels[0]); i++) {
        int idx = storage_irrigation_node_find_actuator_index(channels[i]);
        if (idx < 0) {
            all_ok = false;
            continue;
        }
        esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked((size_t)idx, false);
        if (stop_err != ESP_OK) {
            all_ok = false;
            ESP_LOGE(TAG, "Failed to stop irrigation path %s: %s", channels[i], esp_err_to_name(stop_err));
        }
    }
    if (all_ok) {
        (void)storage_irrigation_node_complete_stage_guard_for_stage_locked("irrigation", NULL, 0);
    }
    return all_ok;
}

bool storage_irrigation_node_stop_all_paths_locked(void) {
    bool all_ok = true;
    for (size_t i = 0; i < g_actuator_runtime_count; i++) {
        esp_err_t stop_err = storage_irrigation_node_set_actuator_state_locked(i, false);
        if (stop_err != ESP_OK) {
            all_ok = false;
            const char *channel = g_actuator_runtime[i].cfg ? g_actuator_runtime[i].cfg->name : "unknown";
            ESP_LOGE(TAG, "Failed to stop actuator %s during e-stop: %s", channel, esp_err_to_name(stop_err));
        }
    }
    return all_ok;
}

void storage_irrigation_node_pause_stage_guards_locked(void) {
    int64_t now_us = esp_timer_get_time();
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &g_stage_guards[i];
        if (!guard->active) {
            continue;
        }
        uint32_t elapsed_ms = 0;
        if (guard->timeout_ms > 0 && guard->timeout_pending == false && now_us > 0 && guard->active) {
            if (guard->timeout_ms > 0 && guard->timeout_ms <= UINT32_MAX) {
                if (guard->timer && xTimerIsTimerActive(guard->timer) != pdFALSE) {
                    TickType_t expiry_tick = xTimerGetExpiryTime(guard->timer);
                    TickType_t now_tick = xTaskGetTickCount();
                    if (expiry_tick > now_tick) {
                        guard->timeout_ms = (uint32_t)pdTICKS_TO_MS(expiry_tick - now_tick);
                    } else {
                        guard->timeout_ms = 1;
                    }
                }
            }
            (void)elapsed_ms;
        }
        xTimerStop(guard->timer, 0);
    }
}

void storage_irrigation_node_resume_stage_guards_locked(void) {
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &g_stage_guards[i];
        if (!guard->active || guard->timeout_pending || guard->timeout_ms == 0) {
            continue;
        }
        if (xTimerChangePeriod(guard->timer, pdMS_TO_TICKS(guard->timeout_ms), 0) != pdPASS) {
            ESP_LOGE(TAG, "Failed to resume paused stage guard %s", guard->stage);
            guard->timeout_pending = true;
            continue;
        }
        if (xTimerStart(guard->timer, 0) != pdPASS) {
            ESP_LOGE(TAG, "Failed to start resumed stage guard %s", guard->stage);
            guard->timeout_pending = true;
        }
    }
}

const char *storage_irrigation_node_timeout_event_code_for_stage(const char *stage) {
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

void storage_irrigation_node_process_stage_timeouts(void) {
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        storage_irrigation_node_stage_guard_t *guard = &g_stage_guards[i];
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

        if (g_actuator_mutex && xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
            (void)storage_irrigation_node_stop_stage_path_locked(stage_name);
            xSemaphoreGive(g_actuator_mutex);
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

void storage_irrigation_node_stage_guard_timer_cb(TimerHandle_t timer) {
    storage_irrigation_node_stage_guard_t *guard = (storage_irrigation_node_stage_guard_t *)pvTimerGetTimerID(timer);
    if (!guard) {
        return;
    }
    guard->timeout_pending = true;
    storage_irrigation_node_signal_cmd_process();
}
