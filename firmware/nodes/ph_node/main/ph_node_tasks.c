/**
 * @file ph_node_tasks.c
 * @brief FreeRTOS задачи и телеметрия для ph_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос pH датчика и публикация телеметрии
 * - ph_node_publish_telemetry - публикация телеметрии pH
 * 
 * Примечание: heartbeat задача вынесена в компонент heartbeat_task
 */

#include "ph_node_app.h"
#include "mqtt_manager.h"
#include "oled_ui.h"
#include "trema_ph.h"
#include "connection_status.h"
#include "heartbeat_task.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <math.h>
#include <float.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

static const char *TAG = "ph_node_tasks";

// Период опроса датчика (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    3000  // 3 секунды - опрос pH датчика

/**
 * @brief Задача опроса сенсоров
 * 
 * Периодически опрашивает pH датчик и публикует телеметрию
 * Согласно NODE_ARCH_FULL.md раздел 6
 */
static void task_sensors(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!mqtt_manager_is_connected()) {
            ESP_LOGW(TAG, "MQTT not connected, skipping sensor poll");
            continue;
        }
        
        // Publish pH telemetry (pH-специфичная логика)
        ph_node_publish_telemetry();
        
        // Update OLED UI with current pH values (pH-специфичная логика)
        if (ph_node_is_oled_initialized()) {
            // Получение статуса соединений через общий компонент
            connection_status_t conn_status;
            if (connection_status_get(&conn_status) == ESP_OK) {
                // Обновление модели OLED UI
                oled_ui_model_t model = {0};
                model.connections.wifi_connected = conn_status.wifi_connected;
                model.connections.mqtt_connected = conn_status.mqtt_connected;
                model.connections.wifi_rssi = conn_status.wifi_rssi;
                
                // Get current pH value (pH-специфичная логика)
                if (ph_node_is_ph_sensor_initialized()) {
                    float ph_value = 0.0f;
                    if (trema_ph_read(&ph_value) && !isnan(ph_value) && isfinite(ph_value)) {
                        model.ph_value = ph_value;
                    } else {
                        model.ph_value = 0.0f; // Unknown
                    }
                }
                
                model.alert = false;
                model.paused = false;
                
                oled_ui_update_model(&model);
            }
        }
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void ph_node_start_tasks(void) {
    // Задача опроса pH датчика (pH-специфичная)
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Задача heartbeat (общая логика через компонент)
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}

/**
 * @brief Publish pH telemetry with real values from Trema pH sensor
 */
void ph_node_publish_telemetry(void) {
    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }
    
    // Initialize sensor if not initialized
    if (!trema_ph_is_initialized() && i2c_bus_is_initialized()) {
        if (trema_ph_init()) {
            ESP_LOGI(TAG, "Trema pH sensor initialized");
        }
    }
    
    // Read pH value
    float ph_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    
    if (trema_ph_is_initialized()) {
        read_success = trema_ph_read(&ph_value);
        using_stub = trema_ph_is_using_stub_values();
        
        if (!read_success || isnan(ph_value)) {
            ESP_LOGW(TAG, "Failed to read pH value, using stub");
            ph_value = 6.5f;  // Neutral value
            using_stub = true;
        }
    } else {
        ESP_LOGW(TAG, "pH sensor not initialized, using stub value");
        ph_value = 6.5f;
        using_stub = true;
    }
    
    // Get node_id from config (через геттер, который использует config_storage)
    const char *node_id = ph_node_get_node_id();
    
    // Format according to MQTT_SPEC_FULL.md section 3.2
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "ph_sensor");
        cJSON_AddStringToObject(telemetry, "metric_type", "PH");
        cJSON_AddNumberToObject(telemetry, "value", ph_value);
        cJSON_AddNumberToObject(telemetry, "raw", (int)(ph_value * 1000));  // Raw value in thousandths
        cJSON_AddBoolToObject(telemetry, "stub", using_stub);  // Stub flag
        cJSON_AddNumberToObject(telemetry, "timestamp", (double)(esp_timer_get_time() / 1000000));
        
        // Add stability information if available
        if (trema_ph_is_initialized() && !using_stub) {
            bool is_stable = trema_ph_get_stability();
            cJSON_AddBoolToObject(telemetry, "stable", is_stable);
        }
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_manager_publish_telemetry("ph_sensor", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

