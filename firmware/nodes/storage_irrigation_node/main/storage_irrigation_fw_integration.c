/**
 * @file storage_irrigation_fw_integration.c
 * @brief storage_irrigation_node framework — integration module.
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

esp_err_t storage_irrigation_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    (void)pump_driver_emergency_stop();

    if (!g_actuator_mutex || xSemaphoreTake(g_actuator_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    for (size_t i = 0; i < g_actuator_runtime_count; i++) {
        (void)storage_irrigation_node_set_actuator_state_locked(i, false);
    }
    xSemaphoreGive(g_actuator_mutex);
    storage_irrigation_node_update_oled_runtime();
    return ESP_OK;
}

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
    storage_irrigation_node_reload_fail_safe_config_from_storage();
    storage_irrigation_node_log_fail_safe_config();
    err = storage_irrigation_node_init_estop_input();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize e-stop input: %s", esp_err_to_name(err));
        return err;
    }

    if (!g_actuator_mutex) {
        g_actuator_mutex = xSemaphoreCreateMutex();
        if (!g_actuator_mutex) {
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

    if (!g_cmd_queue_mutex) {
        g_cmd_queue_mutex = xSemaphoreCreateMutex();
        if (!g_cmd_queue_mutex) {
            ESP_LOGE(TAG, "Failed to create pump command queue mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    if (!g_cmd_work_queue) {
        g_cmd_work_queue = xQueueCreate(STORAGE_IRRIGATION_NODE_CMD_QUEUE_MAX, sizeof(uint8_t));
        if (!g_cmd_work_queue) {
            ESP_LOGE(TAG, "Failed to create pump command queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(storage_irrigation_node_cmd_queue_task, "pump_cmd_queue", 4096, NULL, 4, NULL);
    }
    if (!g_done_queue) {
        g_done_queue = xQueueCreate(STORAGE_IRRIGATION_NODE_DONE_QUEUE_MAX, sizeof(storage_irrigation_node_done_event_t));
        if (!g_done_queue) {
            ESP_LOGE(TAG, "Failed to create pump done queue");
            return ESP_ERR_NO_MEM;
        }
        xTaskCreate(storage_irrigation_node_done_task, "pump_done", 4096, NULL, 4, NULL);
    }
    if (!g_cmd_retry_timer) {
        g_cmd_retry_timer = xTimerCreate("pump_retry", pdMS_TO_TICKS(1000), pdFALSE, NULL, storage_irrigation_node_retry_timer_cb);
        if (!g_cmd_retry_timer) {
            ESP_LOGW(TAG, "Failed to create pump retry timer");
        }
    }
    for (size_t i = 0; i < sizeof(g_stage_guards) / sizeof(g_stage_guards[0]); i++) {
        if (!g_stage_guards[i].timer) {
            continue;
        }
        xTimerStop(g_stage_guards[i].timer, 0);
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

    err = node_command_handler_register("test_sensor", handle_test_sensor, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register test_sensor handler: %s", esp_err_to_name(err));
        return err;
    }

    err = node_command_handler_register("probe_sensor", handle_probe_sensor, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register probe_sensor handler: %s", esp_err_to_name(err));
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

void storage_irrigation_node_config_handler_wrapper(const char *topic, const char *data, int data_len, void *user_ctx) {
    if (data == NULL || data_len <= 0) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        storage_irrigation_node_reload_fail_safe_config_from_storage();
        return;
    }

    bool changed = false;
    char *patched = storage_irrigation_node_build_patched_config(data, (size_t)data_len, true, &changed);
    if (!patched) {
        node_config_handler_process(topic, data, data_len, user_ctx);
        storage_irrigation_node_reload_fail_safe_config_from_storage();
        return;
    }

    node_config_handler_process(topic, patched, (int)strlen(patched), user_ctx);
    storage_irrigation_node_reload_fail_safe_config_from_storage();
    free(patched);
}

void storage_irrigation_node_command_handler_wrapper(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

cJSON *storage_irrigation_node_channels_callback(void *user_ctx) {
    (void)user_ctx;
    return storage_irrigation_node_build_config_channels();
}
