/**
 * @file ph_node_tasks.c
 * @brief FreeRTOS задачи для ph_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - task_heartbeat - публикация heartbeat
 */

#include "ph_node_app.h"
#include "mqtt_client.h"
#include "oled_ui.h"
#include "wifi_manager.h"
#include "trema_ph.h"

// Объявление функций и переменных из ph_node_app.c
extern void ph_node_publish_telemetry_example(void);
extern bool oled_ui_initialized;
extern bool ph_sensor_initialized;

#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>
#include <math.h>

static const char *TAG = "ph_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    3000  // 3 секунды - опрос pH датчика
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat

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
        
        if (!mqtt_client_is_connected()) {
            ESP_LOGW(TAG, "MQTT not connected, skipping sensor poll");
            continue;
        }
        
        // Публикация телеметрии pH
        ph_node_publish_telemetry_example();
        
        // Обновление OLED UI с текущими значениями
        if (oled_ui_initialized) {
            // Получение текущего значения pH (через функцию из ph_node_app.c)
            // Для упрощения используем публикацию телеметрии, которая уже читает pH
            // В реальности можно добавить функцию получения текущего значения
            
            // Получение статуса соединений
            wifi_ap_record_t ap_info;
            int8_t rssi = -100;
            bool wifi_connected = wifi_manager_is_connected();
            if (wifi_connected && esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                rssi = ap_info.rssi;
            }
            
            bool mqtt_connected = mqtt_client_is_connected();
            
            // Обновление модели OLED UI
            oled_ui_model_t model = {0};
            model.connections.wifi_connected = wifi_connected;
            model.connections.mqtt_connected = mqtt_connected;
            model.connections.wifi_rssi = rssi;
            
            // Получение текущего значения pH (используем функцию из trema_ph)
            if (ph_sensor_initialized) {
                float ph_value = NAN;
                if (trema_ph_read(&ph_value) && !isnan(ph_value)) {
                    model.ph_value = ph_value;
                } else {
                    model.ph_value = 0.0f; // Неизвестно
                }
            }
            
            model.alert = false;
            model.paused = false;
            
            oled_ui_update_model(&model);
        }
    }
}

/**
 * @brief Задача публикации heartbeat
 * 
 * Публикует heartbeat каждые 15 секунд согласно NODE_ARCH_FULL.md раздел 9
 */
static void task_heartbeat(void *pvParameters) {
    ESP_LOGI(TAG, "Heartbeat task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(HEARTBEAT_INTERVAL_MS);
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!mqtt_client_is_connected()) {
            continue;
        }
        
        // Получение RSSI
        wifi_ap_record_t ap_info;
        int8_t rssi = -100;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            rssi = ap_info.rssi;
        }
        
        // Формат согласно MQTT_SPEC_FULL.md раздел 9.1
        cJSON *heartbeat = cJSON_CreateObject();
        if (heartbeat) {
            cJSON_AddNumberToObject(heartbeat, "uptime", (double)(esp_timer_get_time() / 1000));
            cJSON_AddNumberToObject(heartbeat, "free_heap", (double)esp_get_free_heap_size());
            cJSON_AddNumberToObject(heartbeat, "rssi", rssi);
            
            char *json_str = cJSON_PrintUnformatted(heartbeat);
            if (json_str) {
                mqtt_client_publish_heartbeat(json_str);
                free(json_str);
            }
            cJSON_Delete(heartbeat);
        }
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void ph_node_start_tasks(void) {
    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Задача heartbeat
    xTaskCreate(task_heartbeat, "heartbeat_task", 3072, NULL, 3, NULL);
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}

