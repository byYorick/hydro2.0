/**
 * @file climate_node_tasks.c
 * @brief FreeRTOS задачи для climate_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - heartbeat_task_start_default - публикация heartbeat через общий компонент
 */

#include "climate_node_app.h"
#include "climate_node_framework_integration.h"
#include "node_watchdog.h"
#include "mqtt_manager.h"
#include "heartbeat_task.h"
#include "oled_ui.h"
#include "sht3x.h"
#include "ccs811.h"
#include "connection_status.h"
#include "config_storage.h"
#include "esp_log.h"
#include "freertos/task.h"
#include <math.h>
#include <string.h>

static const char *TAG = "climate_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    5000  // 5 секунд - опрос климатических датчиков

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

                // GH/Zone идентификаторы
                char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN] = {0};
                char zone_uid[CONFIG_STORAGE_MAX_STRING_LEN] = {0};
                if (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK) {
                    strncpy(model.gh_name, gh_uid, sizeof(model.gh_name) - 1);
                }
                if (config_storage_get_zone_uid(zone_uid, sizeof(zone_uid)) == ESP_OK) {
                    strncpy(model.zone_name, zone_uid, sizeof(model.zone_name) - 1);
                }
                config_storage_wifi_t wifi_cfg = {0};
                if (config_storage_get_wifi(&wifi_cfg) == ESP_OK) {
                    strncpy(model.wifi_ssid, wifi_cfg.ssid, sizeof(model.wifi_ssid) - 1);
                }
                config_storage_mqtt_t mqtt_cfg = {0};
                if (config_storage_get_mqtt(&mqtt_cfg) == ESP_OK) {
                    strncpy(model.mqtt_host, mqtt_cfg.host, sizeof(model.mqtt_host) - 1);
                    model.mqtt_port = mqtt_cfg.port;
                }
                
                // Базовый статус сенсоров
                model.sensor_status.i2c_connected = true;
                model.sensor_status.has_error = false;
                model.sensor_status.using_stub = false;
                model.sensor_status.error_msg[0] = '\0';

                // Чтение температуры и влажности (SHT3x)
                sht3x_reading_t sht_reading = {0};
                esp_err_t sht_err = sht3x_read(&sht_reading);
                
                if (sht_err == ESP_OK && sht_reading.valid) {
                    model.temperature_air = sht_reading.temperature;
                    model.humidity = sht_reading.humidity;
                } else {
                    model.temperature_air = NAN;
                    model.humidity = NAN;
                    model.sensor_status.has_error = true;
                    // Проверяем доступность I2C BUS1 для SHT3x
                    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
                        model.sensor_status.i2c_connected = false;
                        strncpy(model.sensor_status.error_msg, "I2C BUS1", sizeof(model.sensor_status.error_msg) - 1);
                    } else {
                        strncpy(model.sensor_status.error_msg, "SHT3x", sizeof(model.sensor_status.error_msg) - 1);
                    }
                }
                
                // Чтение CO₂ (CCS811)
                ccs811_reading_t ccs_reading = {0};
                esp_err_t ccs_err = ccs811_read(&ccs_reading);
                
                if (ccs_err == ESP_OK && ccs_reading.valid) {
                    model.co2 = (float)ccs_reading.co2_ppm;
                } else {
                    model.co2 = NAN;
                    // Не затираем ошибку SHT3x, только дополняем если еще не установлена
                    if (!model.sensor_status.has_error) {
                        model.sensor_status.has_error = true;
                        model.sensor_status.using_stub = (ccs_err != ESP_OK);
                        if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
                            model.sensor_status.i2c_connected = false;
                            strncpy(model.sensor_status.error_msg, "I2C BUS0", sizeof(model.sensor_status.error_msg) - 1);
                        } else {
                            model.sensor_status.i2c_connected = (ccs_err != ESP_ERR_INVALID_STATE);
                            strncpy(model.sensor_status.error_msg, "CCS811", sizeof(model.sensor_status.error_msg) - 1);
                        }
                        model.sensor_status.error_msg[sizeof(model.sensor_status.error_msg) - 1] = '\0';
                    }
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
 * @brief Запуск FreeRTOS задач
 */
void climate_node_start_tasks(void) {
    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);

    // Общая задача heartbeat из компонента
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}
