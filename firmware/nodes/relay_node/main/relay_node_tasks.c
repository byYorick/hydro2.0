/**
 * @file relay_node_tasks.c
 * @brief FreeRTOS задачи для relay_node
 * 
 * Реализует периодические задачи:
 * - task_status - публикация STATUS сообщений
 * 
 * Примечание: heartbeat задача вынесена в компонент heartbeat_task
 */

#include "relay_node_app.h"
#include "mqtt_manager.h"
#include "connection_status.h"
#include "heartbeat_task.h"
#include "node_utils.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "node_watchdog.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>

static const char *TAG = "relay_node_tasks";

#define STATUS_PUBLISH_INTERVAL_MS 60000  // 60 секунд - публикация STATUS

/**
 * @brief Задача публикации STATUS сообщений
 * 
 * Публикует status каждые 60 секунд согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 */
static void task_status(void *pvParameters) {
    ESP_LOGI(TAG, "Status task started");
    
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add status task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(STATUS_PUBLISH_INTERVAL_MS);
    
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(1000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            node_watchdog_reset();
            
            if (mqtt_manager_is_connected()) {
                relay_node_publish_status();
            }
            
            node_watchdog_reset();
            last_wake_time = current_time;
        }
        
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void relay_node_start_tasks(void) {
    // Задача публикации STATUS
    xTaskCreate(task_status, "status_task", 3072, NULL, 3, NULL);
    
    // Задача heartbeat (общая логика через компонент)
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}

/**
 * @brief Publish STATUS message
 * 
 * Публикует статус узла согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 */
void relay_node_publish_status(void) {
    if (!mqtt_manager_is_connected()) {
        return;
    }
    
    // Получение IP адреса
    esp_netif_ip_info_t ip_info;
    char ip_str[16] = "0.0.0.0";
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (netif != NULL) {
        if (esp_netif_get_ip_info(netif, &ip_info) == ESP_OK) {
            snprintf(ip_str, sizeof(ip_str), IPSTR, IP2STR(&ip_info.ip));
        }
    }
    
    // Получение RSSI через connection_status
    connection_status_t conn_status;
    int8_t rssi = -100;
    if (connection_status_get(&conn_status) == ESP_OK) {
        rssi = conn_status.wifi_rssi;
    }
    
    // Версия прошивки
    const char *fw_version = IDF_VER;
    
    // Формат согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
    cJSON *status = cJSON_CreateObject();
    if (status) {
        cJSON_AddStringToObject(status, "status", "ONLINE");
        cJSON_AddNumberToObject(status, "ts", (double)node_utils_get_timestamp_seconds());
        cJSON_AddBoolToObject(status, "online", true);
        cJSON_AddStringToObject(status, "ip", ip_str);
        cJSON_AddNumberToObject(status, "rssi", rssi);
        cJSON_AddStringToObject(status, "fw", fw_version);
        
        char *json_str = cJSON_PrintUnformatted(status);
        if (json_str) {
            mqtt_manager_publish_status(json_str);
            free(json_str);
        }
        cJSON_Delete(status);
    }
}
