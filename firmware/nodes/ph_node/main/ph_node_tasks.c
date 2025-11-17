/**
 * @file ph_node_tasks.c
 * @brief FreeRTOS задачи для ph_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос pH датчика и публикация телеметрии
 * 
 * Примечание: heartbeat задача вынесена в компонент heartbeat_task
 */

#include "ph_node_app.h"
#include "mqtt_manager.h"
#include "oled_ui.h"
#include "trema_ph.h"
#include "connection_status.h"
#include "heartbeat_task.h"

#include "ph_node_telemetry.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>
#include <float.h>
#include <stdbool.h>

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

