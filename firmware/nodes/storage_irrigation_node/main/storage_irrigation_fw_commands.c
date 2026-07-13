/**
 * @file storage_irrigation_fw_commands.c
 * @brief storage_irrigation_node framework — commands module.
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

esp_err_t handle_set_relay(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
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
    if (target_state && has_timeout && (!has_stage || !storage_irrigation_node_is_main_pump_channel(channel))) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "timeout_ms/stage is supported only for pump_main stage-arm command",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    if (!g_actuator_mutex || xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
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
        xSemaphoreGive(g_actuator_mutex);
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "unsupported_channel",
            "Channel is not supported for set_relay",
            NULL
        );
        return ESP_ERR_NOT_FOUND;
    }
    if (target_state && storage_irrigation_node_is_estop_active()) {
        xSemaphoreGive(g_actuator_mutex);
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "estop_active",
            "E-Stop is active; actuator ON commands are rejected",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    bool previous_state = false;
    bool allow_pump_main_dry_run = storage_irrigation_node_is_pump_main_dry_run_allowed(
        channel,
        target_state,
        has_duration,
        duration_ms
    );
    (void)storage_irrigation_node_get_actuator_state_locked(channel, &previous_state);
    if (storage_irrigation_node_is_main_pump_channel(channel)
        && target_state
        && !allow_pump_main_dry_run
        && !storage_irrigation_node_is_main_pump_interlock_satisfied_locked()) {
        xSemaphoreGive(g_actuator_mutex);
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
            xSemaphoreGive(g_actuator_mutex);
            cJSON *extra = cJSON_CreateObject();
            const char *error_code = "actuator_apply_failed";
            const char *error_message = "Failed to apply actuator state";
            if (target_state && set_err == ESP_ERR_INVALID_STATE) {
                uint32_t cooldown_remaining_ms = 0;
                const char *drv_ch = storage_irrigation_node_canonical_actuator_channel(channel);
                if (pump_driver_get_cooldown_remaining(drv_ch ? drv_ch : channel, &cooldown_remaining_ms) == ESP_OK && cooldown_remaining_ms > 0) {
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
        xSemaphoreGive(g_actuator_mutex);
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
            xSemaphoreGive(g_actuator_mutex);
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

    xSemaphoreGive(g_actuator_mutex);

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
    /* Stage-arm (timeout_ms/stage): terminal DONE сразу — AE3 ждёт DONE (complete_on_ack deprecated).
     * Guard остаётся armed для fail-safe/timeout events. Transient duration_ms: ACK → DONE. */
    *response = node_command_handler_create_response(
        cmd_id,
        has_duration ? "ACK" : "DONE",
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

esp_err_t handle_run_pump(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    if (!channel || !params || !response) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *cmd_id = node_command_handler_get_cmd_id(params);
    if (!storage_irrigation_node_is_main_pump_channel(channel)) {
        *response = node_command_handler_create_response(
            cmd_id,
            "INVALID",
            "unsupported_channel_cmd",
            "run_pump is supported only for pump_main",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    const cJSON *duration_ms_item = cJSON_GetObjectItem((cJSON *)params, "duration_ms");
    uint32_t duration_ms = 0;
    if (!storage_irrigation_node_parse_duration_ms(duration_ms_item, &duration_ms)
        || duration_ms > STORAGE_IRRIGATION_NODE_PUMP_MAIN_MAX_DURATION_MS) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "invalid_params",
            "Missing or invalid duration_ms for run_pump",
            NULL
        );
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *relay_params = cJSON_CreateObject();
    if (!relay_params) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "memory_error",
            "Failed to allocate run_pump params",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    if (cmd_id) {
        cJSON_AddStringToObject(relay_params, "cmd_id", cmd_id);
    }
    cJSON_AddBoolToObject(relay_params, "state", true);
    cJSON_AddNumberToObject(relay_params, "duration_ms", (double)duration_ms);

    esp_err_t err = handle_set_relay(channel, relay_params, response, NULL);
    cJSON_Delete(relay_params);
    return err;
}

esp_err_t handle_storage_state(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
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

esp_err_t handle_test_sensor(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    (void)user_ctx;
    if (!channel || !response) {
        return ESP_ERR_INVALID_ARG;
    }

    const storage_irrigation_node_sensor_channel_t *sensor_cfg = storage_irrigation_node_find_sensor_cfg(channel);
    if (!sensor_cfg) {
        *response = node_command_handler_create_response(
            node_command_handler_get_cmd_id(params),
            "ERROR",
            "invalid_channel",
            "test_sensor is supported only on level_* WATER_LEVEL_SWITCH channels",
            NULL
        );
        return ESP_ERR_NOT_SUPPORTED;
    }

    if (!g_level_switch_inputs_ready && storage_irrigation_node_init_level_switch_inputs() != ESP_OK) {
        *response = node_command_handler_create_response(
            node_command_handler_get_cmd_id(params),
            "ERROR",
            "sensor_init_failed",
            "Level-switch inputs are not ready",
            NULL
        );
        return ESP_ERR_INVALID_STATE;
    }

    int raw = 0;
    float value = storage_irrigation_node_read_level_switch(sensor_cfg, &raw);

    const char *cmd_id = node_command_handler_get_cmd_id(params);
    cJSON *extra = cJSON_CreateObject();
    if (!extra) {
        *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "memory_error",
            "Failed to allocate test_sensor details",
            NULL
        );
        return ESP_ERR_NO_MEM;
    }

    cJSON_AddNumberToObject(extra, "value", (double)value);
    if (sensor_cfg->unit && sensor_cfg->unit[0] != '\0') {
        cJSON_AddStringToObject(extra, "unit", sensor_cfg->unit);
    }
    if (sensor_cfg->metric && sensor_cfg->metric[0] != '\0') {
        cJSON_AddStringToObject(extra, "metric_type", sensor_cfg->metric);
    }
    cJSON_AddNumberToObject(extra, "raw_value", (double)raw);

    *response = node_command_handler_create_response(cmd_id, "DONE", NULL, NULL, extra);
    cJSON_Delete(extra);
    return ESP_OK;
}

esp_err_t handle_probe_sensor(
    const char *channel,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    return handle_test_sensor(channel, params, response, user_ctx);
}
