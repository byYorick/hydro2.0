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
#include "ina209.h"
#include "pump_driver.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_task_wdt.h"
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
#define PUMP_CURRENT_POLL_INTERVAL_MS 5000  // 5 секунд - опрос тока насосов (по умолчанию)
#define STATUS_PUBLISH_INTERVAL_MS 60000  // 60 секунд - публикация STATUS согласно DEVICE_NODE_PROTOCOL.md

/**
 * @brief Задача опроса сенсоров
 * 
 * Периодически опрашивает pH датчик и публикует телеметрию
 * Согласно NODE_ARCH_FULL.md раздел 6
 */
static void task_sensors(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = esp_task_wdt_add(NULL);
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
            esp_task_wdt_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для опроса сенсора
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            esp_task_wdt_reset();
            
            // Publish pH telemetry только если MQTT подключен
            if (mqtt_manager_is_connected()) {
                ph_node_publish_telemetry();
            } else {
                ESP_LOGW(TAG, "MQTT not connected, skipping sensor poll");
            }
            
            // Update OLED UI with current pH values (pH-специфичная логика)
            // Обновляем OLED независимо от MQTT подключения
            if (ph_node_is_oled_initialized()) {
                // Получение статуса соединений через общий компонент
                connection_status_t conn_status;
                if (connection_status_get(&conn_status) == ESP_OK) {
                    // Обновление модели OLED UI - обновляем только изменяемые поля
                    oled_ui_model_t model = {0};
                    // Инициализируем неиспользуемые поля как NaN, чтобы они не обновлялись
                    model.ph_value = NAN;
                    model.ec_value = NAN;
                    model.temperature_air = NAN;
                    model.temperature_water = NAN;
                    model.humidity = NAN;
                    model.co2 = NAN;
                    
                    // Обновляем соединения
                    model.connections.wifi_connected = conn_status.wifi_connected;
                    model.connections.mqtt_connected = conn_status.mqtt_connected;
                    model.connections.wifi_rssi = conn_status.wifi_rssi;
                    
                    // Get current pH value (pH-специфичная логика)
                    if (ph_node_is_ph_sensor_initialized()) {
                        float ph_value = 0.0f;
                        if (trema_ph_read(&ph_value) && !isnan(ph_value) && isfinite(ph_value)) {
                            model.ph_value = ph_value;
                        }
                        // Если не удалось прочитать, оставляем NaN - старое значение сохранится
                    }
                    
                    // Статус узла
                    model.alert = false;
                    model.paused = false;
                    
                    oled_ui_update_model(&model);
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

/**
 * @brief Задача опроса тока насосов (INA209)
 * 
 * Периодически опрашивает INA209 и публикует телеметрию pump_bus_current
 * Согласно NODE_CHANNELS_REFERENCE.md раздел 3.4
 */
static void task_pump_current(void *pvParameters) {
    ESP_LOGI(TAG, "Pump current task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = esp_task_wdt_add(NULL);
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add pump current task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(PUMP_CURRENT_POLL_INTERVAL_MS);
    
    // Интервал для периодического сброса watchdog (каждые 3 секунды)
    // Это гарантирует, что watchdog будет сброшен даже если задача зависнет
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(3000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // Периодически сбрасываем watchdog во время ожидания
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            esp_task_wdt_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для опроса тока
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            esp_task_wdt_reset();
            
            if (mqtt_manager_is_connected()) {
                // Публикация telemetry тока насосов
                ph_node_publish_pump_current_telemetry();
            }
            
            // Сбрасываем watchdog после выполнения работы
            esp_task_wdt_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/**
 * @brief Задача публикации STATUS сообщений
 * 
 * Публикует status каждые 60 секунд согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 * 
 * Примечание: интервал 60 секунд больше watchdog таймаута (10 сек),
 * поэтому используем периодический сброс watchdog во время ожидания
 */
static void task_status(void *pvParameters) {
    ESP_LOGI(TAG, "Status task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = esp_task_wdt_add(NULL);
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add status task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(STATUS_PUBLISH_INTERVAL_MS);
    
    // Интервал для периодического сброса watchdog (каждые 5 секунд)
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(5000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        // Периодически сбрасываем watchdog во время ожидания
        // (интервал задачи 60 сек > watchdog таймаут 10 сек)
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            esp_task_wdt_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для публикации STATUS
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            esp_task_wdt_reset();
            
            if (mqtt_manager_is_connected()) {
                // Публикация STATUS
                ph_node_publish_status();
            }
            
            // Сбрасываем watchdog после выполнения работы
            esp_task_wdt_reset();
            last_wake_time = current_time;
        }
        
        // Небольшая задержка, чтобы не нагружать CPU
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void ph_node_start_tasks(void) {
    // Задача опроса pH датчика (pH-специфичная)
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Задача опроса тока насосов (INA209)
    xTaskCreate(task_pump_current, "pump_current_task", 3072, NULL, 4, NULL);
    
    // Задача публикации STATUS
    xTaskCreate(task_status, "status_task", 3072, NULL, 3, NULL);
    
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
    if (node_id == NULL) {
        ESP_LOGE(TAG, "Failed to get node_id, skipping telemetry");
        return;
    }
    
    // Format according to MQTT_SPEC_FULL.md section 3.2
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "ph_sensor");
        cJSON_AddStringToObject(telemetry, "metric_type", "PH");
        cJSON_AddNumberToObject(telemetry, "value", ph_value);
        cJSON_AddNumberToObject(telemetry, "raw", (int)(ph_value * 1000));  // Raw value in thousandths
        cJSON_AddBoolToObject(telemetry, "stub", using_stub);  // Stub flag
        cJSON_AddNumberToObject(telemetry, "ts", (double)(esp_timer_get_time() / 1000000));
        
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

/**
 * @brief Publish pump bus current telemetry from INA209
 */
void ph_node_publish_pump_current_telemetry(void) {
    if (!mqtt_manager_is_connected()) {
        return;
    }
    
    // Проверяем, инициализирован ли INA209 через pump_driver
    // INA209 может быть не настроен, если нет конфигурации
    ina209_reading_t reading = {0};
    esp_err_t err = ina209_read(&reading);
    
    if (err != ESP_OK || !reading.valid) {
        // INA209 не инициализирован или ошибка чтения - не публикуем telemetry
        return;
    }
    
    // Get node_id from config
    const char *node_id = ph_node_get_node_id();
    if (node_id == NULL) {
        ESP_LOGE(TAG, "Failed to get node_id, skipping pump current telemetry");
        return;
    }
    
    // Format according to NODE_CHANNELS_REFERENCE.md section 3.4
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "pump_bus_current");
        cJSON_AddStringToObject(telemetry, "metric_type", "CURRENT_MA");
        cJSON_AddNumberToObject(telemetry, "value", reading.bus_current_ma);
        cJSON_AddNumberToObject(telemetry, "ts", (double)(esp_timer_get_time() / 1000000));
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_manager_publish_telemetry("pump_bus_current", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

/**
 * @brief Publish STATUS message
 * 
 * Публикует статус узла согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 */
void ph_node_publish_status(void) {
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
    
    // Получение RSSI
    wifi_ap_record_t ap_info;
    int8_t rssi = -100;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        rssi = ap_info.rssi;
    }
    
    // Версия прошивки (можно взять из IDF_VER или hardcode)
    const char *fw_version = IDF_VER;
    
    // Формат согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
    cJSON *status = cJSON_CreateObject();
    if (status) {
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

