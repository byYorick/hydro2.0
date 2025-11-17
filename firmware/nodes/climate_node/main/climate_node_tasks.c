/**
 * @file climate_node_tasks.c
 * @brief FreeRTOS задачи для climate_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - task_heartbeat - публикация heartbeat
 */

#include "climate_node_app.h"
#include "mqtt_client.h"

// Объявления функций из climate_node_app.c
extern void climate_node_publish_temperature_example(void);
extern void climate_node_publish_humidity_example(void);
extern void climate_node_publish_co2_example(void);
extern void climate_node_publish_heartbeat_example(void);
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "climate_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    5000  // 5 секунд - опрос климатических датчиков
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat

/**
 * @brief Задача опроса сенсоров
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
        
        // Публикация телеметрии температуры, влажности, CO₂
        climate_node_publish_temperature_example();
        vTaskDelay(pdMS_TO_TICKS(100)); // Небольшая задержка между публикациями
        climate_node_publish_humidity_example();
        vTaskDelay(pdMS_TO_TICKS(100));
        climate_node_publish_co2_example();
    }
}

/**
 * @brief Задача публикации heartbeat
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
        
        // Используем готовую функцию из climate_node_app
        climate_node_publish_heartbeat_example();
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void climate_node_start_tasks(void) {
    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Задача heartbeat
    xTaskCreate(task_heartbeat, "heartbeat_task", 3072, NULL, 3, NULL);
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}

