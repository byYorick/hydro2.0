/**
 * @file climate_node_tasks.c
 * @brief FreeRTOS задачи для climate_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - task_heartbeat - публикация heartbeat
 */

#include "climate_node_app.h"
#include "climate_node_framework_integration.h"
#include "node_watchdog.h"
#include "mqtt_manager.h"
#include "oled_ui.h"
#include "sht3x.h"
#include "ccs811.h"
#include "connection_status.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <math.h>

static const char *TAG = "climate_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    5000  // 5 секунд - опрос климатических датчиков
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat

/**
 * @brief Задача опроса сенсоров
 */
static void task_sensors(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor task started");

    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add sensor task to watchdog: %s", esp_err_to_name(wdt_err));
    }

    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    
    // Интервал для периодического сброса watchdog (каждые 2 секунды)
    // Это гарантирует, что watchdog будет сброшен даже если задача зависнет
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(2000);
    TickType_t last_wdt_reset = xTaskGetTickCount();

    while (1) {
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // Периодически сбрасываем watchdog во время ожидания
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для опроса сенсора
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();

        // Публикация телеметрии через node_framework
        if (mqtt_manager_is_connected()) {
            climate_node_publish_telemetry_callback(NULL);
        }
        
        // Обновление OLED UI с данными датчиков
        if (oled_ui_is_initialized()) {
            // Получение статуса соединений
            connection_status_t conn_status;
            if (connection_status_get(&conn_status) == ESP_OK) {
                // Обновление модели OLED UI
                oled_ui_model_t model = {0};
                
                // Инициализируем неиспользуемые поля как NaN
                model.ph_value = NAN;
                model.ec_value = NAN;
                model.temperature_water = NAN;
                
                // Обновляем соединения
                model.connections.wifi_connected = conn_status.wifi_connected;
                model.connections.mqtt_connected = conn_status.mqtt_connected;
                model.connections.wifi_rssi = conn_status.wifi_rssi;
                
                // Чтение температуры и влажности (SHT3x)
                sht3x_reading_t sht_reading = {0};
                esp_err_t sht_err = sht3x_read(&sht_reading);
                
                if (sht_err == ESP_OK && sht_reading.valid) {
                    model.temperature_air = sht_reading.temperature;
                    model.humidity = sht_reading.humidity;
                } else {
                    model.temperature_air = NAN;
                    model.humidity = NAN;
                }
                
                // Чтение CO₂ (CCS811)
                ccs811_reading_t ccs_reading = {0};
                esp_err_t ccs_err = ccs811_read(&ccs_reading);
                
                if (ccs_err == ESP_OK && ccs_reading.valid) {
                    model.co2 = (float)ccs_reading.co2_ppm;
                } else {
                    model.co2 = NAN;
                }
                
                // Статус узла
                model.alert = false;
                model.paused = false;
                
                oled_ui_update_model(&model);
            }
        }
        
            // Сбрасываем watchdog после выполнения работы
            node_watchdog_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/**
 * @brief Задача публикации heartbeat
 * 
 * Примечание: интервал 15 секунд больше watchdog таймаута (10 сек),
 * поэтому используем периодический сброс watchdog во время ожидания
 */
static void task_heartbeat(void *pvParameters) {
    ESP_LOGI(TAG, "Heartbeat task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add heartbeat task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(HEARTBEAT_INTERVAL_MS);
    
    // Сбрасываем watchdog каждую секунду, чтобы иметь запас к системному таймауту
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(1000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        // Периодически сбрасываем watchdog во время ожидания
        // (интервал задачи 15 сек > watchdog таймаут 10 сек)
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для публикации heartbeat
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();
            
            if (!mqtt_manager_is_connected()) {
                last_wake_time = current_time;
                vTaskDelay(pdMS_TO_TICKS(100));  // Небольшая задержка, чтобы не нагружать CPU
                continue;
            }

            wifi_ap_record_t ap_info;
            int8_t rssi = -100;
            if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                rssi = ap_info.rssi;
            }

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
            
            // Сбрасываем watchdog после выполнения работы
            node_watchdog_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
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

