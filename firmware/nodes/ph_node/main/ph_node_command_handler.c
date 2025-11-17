/**
 * @file ph_node_command_handler.c
 * @brief Command message handler implementation
 */

#include "ph_node_command_handler.h"
#include "ph_node_app.h"
#include "mqtt_manager.h"
#include "pump_control.h"
#include "trema_ph.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_err.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "ph_node_cmd";

// Helper function to send error response
static void send_error_response(const char *channel, const char *cmd_id, 
                                const char *error_code, const char *error_message) {
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
        cJSON_AddStringToObject(response, "status", "ERROR");
        cJSON_AddStringToObject(response, "error_code", error_code);
        cJSON_AddStringToObject(response, "error_message", error_message);
        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
        
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            mqtt_manager_publish_command_response(channel, json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }
}

// Helper function to send success response
static void send_success_response(const char *channel, const char *cmd_id, cJSON *extra_data) {
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
        cJSON_AddStringToObject(response, "status", "ACK");
        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
        
        if (extra_data) {
            // Copy extra fields from extra_data
            cJSON *item = extra_data->child;
            while (item) {
                cJSON *next = item->next;
                cJSON_DetachItemViaPointer(extra_data, item);
                cJSON_AddItemToObject(response, item->string, item);
                item = next;
            }
        }
        
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            mqtt_manager_publish_command_response(channel, json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }
    if (extra_data) {
        cJSON_Delete(extra_data);
    }
}

// Handle pump commands
static void handle_pump_command(const char *channel, const char *cmd, const char *cmd_id, cJSON *json) {
    pump_id_t pump_id = (strcmp(channel, "pump_acid") == 0) ? PUMP_ACID : PUMP_BASE;
    
    if (!ph_node_is_pump_control_initialized()) {
        send_error_response(channel, cmd_id, "not_initialized", "Pump control not initialized");
        return;
    }
    
    if (strcmp(cmd, "DOSE") == 0) {
        cJSON *ml_item = cJSON_GetObjectItem(json, "ml");
        if (!cJSON_IsNumber(ml_item)) {
            send_error_response(channel, cmd_id, "invalid_format", "Missing ml parameter");
            return;
        }
        
        float dose_ml = (float)cJSON_GetNumberValue(ml_item);
        ESP_LOGI(TAG, "Dosing %s: %.2f ml", channel, dose_ml);
        
        esp_err_t ret = pump_control_dose(pump_id, dose_ml);
        if (ret == ESP_OK) {
            cJSON *data = cJSON_CreateObject();
            cJSON_AddNumberToObject(data, "dose_ml", dose_ml);
            send_success_response(channel, cmd_id, data);
        } else {
            send_error_response(channel, cmd_id, "pump_error", esp_err_to_name(ret));
        }
        
    } else if (strcmp(cmd, "SET_STATE") == 0) {
        cJSON *state_item = cJSON_GetObjectItem(json, "state");
        if (!cJSON_IsNumber(state_item)) {
            send_error_response(channel, cmd_id, "invalid_format", "Missing state parameter");
            return;
        }
        
        int state = (int)cJSON_GetNumberValue(state_item);
        ESP_LOGI(TAG, "Setting %s state to %d", channel, state);
        
        esp_err_t ret = pump_control_set_state(pump_id, state);
        if (ret == ESP_OK) {
            cJSON *data = cJSON_CreateObject();
            cJSON_AddNumberToObject(data, "state", state);
            send_success_response(channel, cmd_id, data);
        } else {
            send_error_response(channel, cmd_id, "pump_error", esp_err_to_name(ret));
        }
        
    } else {
        send_error_response(channel, cmd_id, "unknown_command", "Unknown command for pump");
    }
}

// Handle calibration command
static void handle_calibration_command(const char *channel, const char *cmd_id, cJSON *json) {
    cJSON *stage_item = cJSON_GetObjectItem(json, "stage");
    cJSON *ph_value_item = cJSON_GetObjectItem(json, "ph_value");
    
    if (!cJSON_IsNumber(stage_item) || !cJSON_IsNumber(ph_value_item)) {
        send_error_response(channel, cmd_id, "invalid_format", "Missing stage or ph_value");
        return;
    }
    
    uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
    float known_ph = (float)cJSON_GetNumberValue(ph_value_item);
    
    if (stage != 1 && stage != 2) {
        send_error_response(channel, cmd_id, "invalid_stage", "Stage must be 1 or 2");
        return;
    }
    
    ESP_LOGI(TAG, "Starting pH calibration: stage=%d, known_pH=%.2f", stage, known_ph);
    
    bool cal_success = trema_ph_calibrate(stage, known_ph);
    if (cal_success) {
        cJSON *data = cJSON_CreateObject();
        cJSON_AddNumberToObject(data, "stage", stage);
        cJSON_AddNumberToObject(data, "known_ph", known_ph);
        send_success_response(channel, cmd_id, data);
    } else {
        send_error_response(channel, cmd_id, "calibration_failed", "Failed to start calibration");
    }
}

void ph_node_command_handler(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Command received on %s (channel: %s): %.*s", topic, channel, data_len, data);
    
    cJSON *json = cJSON_ParseWithLength(data, data_len);
    if (!json) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    cJSON *cmd_item = cJSON_GetObjectItem(json, "cmd");
    cJSON *cmd_id_item = cJSON_GetObjectItem(json, "cmd_id");
    
    if (!cJSON_IsString(cmd_item) || !cJSON_IsString(cmd_id_item)) {
        ESP_LOGE(TAG, "Invalid command format");
        cJSON_Delete(json);
        return;
    }
    
    const char *cmd = cmd_item->valuestring;
    const char *cmd_id = cmd_id_item->valuestring;
    
    ESP_LOGI(TAG, "Processing command: %s (id: %s) on channel: %s", cmd, cmd_id, channel);
    
    // Route command to appropriate handler
    if (strcmp(channel, "pump_acid") == 0 || strcmp(channel, "pump_base") == 0) {
        handle_pump_command(channel, cmd, cmd_id, json);
    } else if (strcmp(cmd, "calibrate") == 0) {
        handle_calibration_command(channel, cmd_id, json);
    } else {
        send_error_response(channel, cmd_id, "unknown_command", "Unknown command");
    }
    
    cJSON_Delete(json);
}

