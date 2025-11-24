/**
 * @file heartbeat_task.c
 * @brief Реализация компонента heartbeat_task
 */

#include "heartbeat_task.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <stdlib.h>

static const char *TAG = "heartbeat_task";

// Параметры по умолчанию
#define DEFAULT_INTERVAL_MS    15000
#define DEFAULT_TASK_PRIORITY   3
#define DEFAULT_TASK_STACK_SIZE 3072

static TaskHandle_t s_heartbeat_task_handle = NULL;

/**
 * @brief Задача публикации heartbeat
 */
static void task_heartbeat(void *pvParameters) {
    uint32_t interval_ms = (uint32_t)(uintptr_t)pvParameters;
    
    ESP_LOGI(TAG, "Heartbeat task started (interval: %lu ms)", (unsigned long)interval_ms);
    
    // Добавляем задачу в watchdog
    esp_task_wdt_add(NULL);
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(interval_ms);
    
    // Интервал для периодического сброса watchdog (каждые 5 секунд)
    // Это необходимо, так как интервал heartbeat (15 сек) может быть больше watchdog таймаута (10 сек)
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(5000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        // Периодически сбрасываем watchdog во время ожидания
        // (интервал задачи может быть больше watchdog таймаута)
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            esp_task_wdt_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для публикации heartbeat
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            esp_task_wdt_reset();
            
            if (mqtt_manager_is_connected()) {
                // Получение RSSI
                wifi_ap_record_t ap_info;
                int8_t rssi = -100;
                if (wifi_manager_is_connected() && esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                    rssi = ap_info.rssi;
                }
                
                // Формат согласно MQTT_SPEC_FULL.md раздел 9.2
                cJSON *heartbeat = cJSON_CreateObject();
                if (heartbeat) {
                    cJSON_AddNumberToObject(heartbeat, "uptime", (double)(esp_timer_get_time() / 1000));
                    cJSON_AddNumberToObject(heartbeat, "free_heap", (double)esp_get_free_heap_size());
                    cJSON_AddNumberToObject(heartbeat, "rssi", rssi);
                    
                    char *json_str = cJSON_PrintUnformatted(heartbeat);
                    if (json_str) {
                        mqtt_manager_publish_heartbeat(json_str);
                        free(json_str);
                    }
                    cJSON_Delete(heartbeat);
                }
            }
            
            // Сбрасываем watchdog после выполнения работы
            esp_task_wdt_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

esp_err_t heartbeat_task_start(uint32_t interval_ms, uint8_t task_priority, uint32_t task_stack_size) {
    if (s_heartbeat_task_handle != NULL) {
        ESP_LOGW(TAG, "Heartbeat task already running");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (interval_ms == 0) {
        interval_ms = DEFAULT_INTERVAL_MS;
    }
    if (task_priority == 0) {
        task_priority = DEFAULT_TASK_PRIORITY;
    }
    if (task_stack_size == 0) {
        task_stack_size = DEFAULT_TASK_STACK_SIZE;
    }
    
    BaseType_t ret = xTaskCreate(
        task_heartbeat,
        "heartbeat_task",
        task_stack_size,
        (void *)(uintptr_t)interval_ms,
        task_priority,
        &s_heartbeat_task_handle
    );
    
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create heartbeat task");
        return ESP_ERR_NO_MEM;
    }
    
    ESP_LOGI(TAG, "Heartbeat task created successfully");
    return ESP_OK;
}

esp_err_t heartbeat_task_start_default(void) {
    return heartbeat_task_start(DEFAULT_INTERVAL_MS, DEFAULT_TASK_PRIORITY, DEFAULT_TASK_STACK_SIZE);
}

esp_err_t heartbeat_task_stop(void) {
    if (s_heartbeat_task_handle == NULL) {
        return ESP_OK;
    }
    
    vTaskDelete(s_heartbeat_task_handle);
    s_heartbeat_task_handle = NULL;
    
    ESP_LOGI(TAG, "Heartbeat task stopped");
    return ESP_OK;
}

