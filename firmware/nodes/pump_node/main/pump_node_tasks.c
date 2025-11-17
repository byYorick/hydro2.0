/**
 * @file pump_node_tasks.c
 * @brief FreeRTOS задачи для pump_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_heartbeat - публикация heartbeat
 * 
 * Примечание: pump_node не имеет периодических сенсоров,
 * телеметрия публикуется только при выполнении команд (ток насоса)
 */

#include "mqtt_client.h"

// Объявление функции из pump_node_app.c (если нужна)
// extern void pump_node_publish_telemetry_example(void);
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "pump_node_tasks";

// Периоды задач (в миллисекундах)
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat

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
void pump_node_start_tasks(void) {
    // Задача heartbeat
    xTaskCreate(task_heartbeat, "heartbeat_task", 3072, NULL, 3, NULL);
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}


