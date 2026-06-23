/**
 * @file storage_irrigation_fw_events.c
 * @brief storage_irrigation_node framework — events module.
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

esp_err_t storage_irrigation_node_publish_storage_event(const char *event_code, const char *cmd_id) {
    return storage_irrigation_node_publish_storage_event_with_details(event_code, cmd_id, NULL);
}

esp_err_t storage_irrigation_node_publish_storage_event_with_details(const char *event_code, const char *cmd_id, cJSON *details) {
    if (!event_code || event_code[0] == '\0') {
        if (details) {
            cJSON_Delete(details);
        }
        return ESP_ERR_INVALID_ARG;
    }
    if (!mqtt_manager_is_connected()) {
        if (details) {
            cJSON_Delete(details);
        }
        return ESP_ERR_INVALID_STATE;
    }
    if (!node_utils_is_time_synced()) {
        if (details) {
            cJSON_Delete(details);
        }
        if (!g_storage_event_time_wait_logged) {
            ESP_LOGW(TAG, "Storage event publish suppressed until time synchronization completes");
            g_storage_event_time_wait_logged = true;
        }
        return ESP_ERR_INVALID_STATE;
    }

    g_storage_event_time_wait_logged = false;

    mqtt_node_info_t node_info = {0};
    esp_err_t info_err = mqtt_manager_get_node_info(&node_info);
    if (info_err != ESP_OK || !node_info.gh_uid || !node_info.zone_uid || !node_info.node_uid) {
        if (details) {
            cJSON_Delete(details);
        }
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
        if (details) {
            cJSON_Delete(details);
        }
        return ESP_ERR_INVALID_SIZE;
    }

    cJSON *payload = cJSON_CreateObject();
    if (!payload) {
        if (details) {
            cJSON_Delete(details);
        }
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddStringToObject(payload, "event_code", event_code);
    cJSON_AddNumberToObject(payload, "ts", (double)node_utils_get_timestamp_seconds());
    if (cmd_id && cmd_id[0] != '\0') {
        cJSON_AddStringToObject(payload, "cmd_id", cmd_id);
    }
    if (details) {
        cJSON_AddItemToObject(payload, "details", details);
        details = NULL;
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

esp_err_t storage_irrigation_node_publish_terminal_response(
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
