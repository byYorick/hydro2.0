/**
 * @file storage_irrigation_fw_pump_cmd.c
 * @brief storage_irrigation_node framework — pump_cmd module.
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

bool storage_irrigation_node_any_pump_running(void) {
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

bool storage_irrigation_node_cmd_queue_push(const storage_irrigation_node_cmd_t *cmd) {
    if (!cmd || !g_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(g_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (g_cmd_queue_count >= STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX) {
        xSemaphoreGive(g_cmd_queue_mutex);
        return false;
    }
    g_cmd_queue[g_cmd_queue_tail] = *cmd;
    g_cmd_queue_tail = (g_cmd_queue_tail + 1) % STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX;
    g_cmd_queue_count++;
    xSemaphoreGive(g_cmd_queue_mutex);
    return true;
}

bool storage_irrigation_node_cmd_queue_pop(storage_irrigation_node_cmd_t *cmd) {
    if (!cmd || !g_cmd_queue_mutex) {
        return false;
    }
    if (xSemaphoreTake(g_cmd_queue_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return false;
    }
    if (g_cmd_queue_count == 0) {
        xSemaphoreGive(g_cmd_queue_mutex);
        return false;
    }
    *cmd = g_cmd_queue[g_cmd_queue_head];
    memset(&g_cmd_queue[g_cmd_queue_head], 0, sizeof(g_cmd_queue[g_cmd_queue_head]));
    g_cmd_queue_head = (g_cmd_queue_head + 1) % STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX;
    g_cmd_queue_count--;
    xSemaphoreGive(g_cmd_queue_mutex);
    return true;
}

void storage_irrigation_node_signal_cmd_process(void) {
    if (!g_cmd_work_queue) {
        return;
    }
    uint8_t token = 1;
    xQueueSend(g_cmd_work_queue, &token, 0);
}

storage_irrigation_node_done_entry_t *storage_irrigation_node_get_done_entry(const char *channel, bool create) {
    if (!channel) {
        return NULL;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX; i++) {
        if (g_done_entries[i].channel_name[0] != '\0' &&
            strncmp(g_done_entries[i].channel_name, channel, sizeof(g_done_entries[i].channel_name)) == 0) {
            return &g_done_entries[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (size_t i = 0; i < STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX; i++) {
        if (g_done_entries[i].channel_name[0] == '\0') {
            strncpy(g_done_entries[i].channel_name, channel, sizeof(g_done_entries[i].channel_name) - 1);
            g_done_entries[i].timer = xTimerCreate(
                "pump_done",
                pdMS_TO_TICKS(1000),
                pdFALSE,
                &g_done_entries[i],
                storage_irrigation_node_done_timer_cb
            );
            if (!g_done_entries[i].timer) {
                g_done_entries[i].channel_name[0] = '\0';
                return NULL;
            }
            return &g_done_entries[i];
        }
    }
    return NULL;
}

bool storage_irrigation_node_valve_clean_fill_transient_timer_armed(void) {
    storage_irrigation_node_done_entry_t *entry =
        storage_irrigation_node_get_done_entry("valve_clean_fill", false);
    if (!entry || entry->channel_name[0] == '\0' || !entry->timer) {
        return false;
    }
    if (!entry->auto_off) {
        return false;
    }
    return xTimerIsTimerActive(entry->timer) != pdFALSE;
}

void storage_irrigation_node_schedule_done(const char *channel, const char *cmd_id, uint32_t duration_ms,
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

void storage_irrigation_node_done_timer_cb(TimerHandle_t timer) {
    storage_irrigation_node_done_entry_t *entry = (storage_irrigation_node_done_entry_t *)pvTimerGetTimerID(timer);
    if (!entry || entry->cmd_id[0] == '\0' || !g_done_queue) {
        return;
    }
    storage_irrigation_node_done_event_t event = {0};
    strncpy(event.channel_name, entry->channel_name, sizeof(event.channel_name) - 1);
    strncpy(event.cmd_id, entry->cmd_id, sizeof(event.cmd_id) - 1);
    event.current_ma = entry->current_ma;
    event.current_valid = entry->current_valid;
    event.auto_off = entry->auto_off;
    event.duration_ms = entry->duration_ms;
    bool sent = false;
    for (int attempt = 0; attempt < 40; attempt++) {
        if (xQueueSend(g_done_queue, &event, 0) == pdTRUE) {
            sent = true;
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
    if (!sent) {
        ESP_LOGE(TAG, "Done queue full for channel %s after retries", entry->channel_name);
    }
}

void storage_irrigation_node_done_task(void *pvParameters) {
    (void)pvParameters;
    storage_irrigation_node_done_event_t event = {0};
    while (true) {
        if (xQueueReceive(g_done_queue, &event, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (event.auto_off) {
            esp_err_t auto_off_err = ESP_OK;
            if (!g_actuator_mutex || xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
                auto_off_err = ESP_ERR_TIMEOUT;
            } else {
                int actuator_index = storage_irrigation_node_find_actuator_index(event.channel_name);
                if (actuator_index < 0) {
                    auto_off_err = ESP_ERR_NOT_FOUND;
                } else {
                    auto_off_err = storage_irrigation_node_set_actuator_state_locked((size_t)actuator_index, false);
                }
                xSemaphoreGive(g_actuator_mutex);
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
                if (storage_irrigation_node_is_main_pump_channel(event.channel_name)
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

void storage_irrigation_node_retry_timer_cb(TimerHandle_t timer) {
    (void)timer;
    storage_irrigation_node_signal_cmd_process();
}

void storage_irrigation_node_process_cmd_queue(void) {
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
        if (g_cmd_retry_timer && cooldown_ms > 0) {
            xTimerChangePeriod(g_cmd_retry_timer, pdMS_TO_TICKS(cooldown_ms), 0);
            xTimerStart(g_cmd_retry_timer, 0);
        }
        return;
    }

    esp_err_t err = pump_driver_run(cmd.channel_name, cmd.duration_ms);
    if (err != ESP_OK) {
        char detail_buf[256];
        const char *ina_code = NULL;
        const char *error_code = "pump_error";
        const char *error_message = "Failed to run pump";

        if (pump_driver_describe_last_start_fault(
                cmd.channel_name, err, detail_buf, sizeof(detail_buf), &ina_code) == ESP_OK) {
            error_code = ina_code;
            error_message = detail_buf;
        } else if (err == ESP_ERR_INVALID_STATE) {
            uint32_t cooldown_remaining_ms = 0;
            if (pump_driver_get_cooldown_remaining(cmd.channel_name, &cooldown_remaining_ms) == ESP_OK
                && cooldown_remaining_ms > 0) {
                error_code = "cooldown_active";
                error_message = "Pump is in cooldown";
            } else if (pump_driver_is_running(cmd.channel_name)) {
                error_code = "pump_busy";
                error_message = "Pump is already running";
            } else {
                error_code = "current_unavailable";
                error_message = "Pump current is unavailable";
            }
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

void storage_irrigation_node_cmd_queue_task(void *pvParameters) {
    (void)pvParameters;
    uint8_t token = 0;
    while (true) {
        if (xQueueReceive(g_cmd_work_queue, &token, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        storage_irrigation_node_process_cmd_queue();
    }
}
