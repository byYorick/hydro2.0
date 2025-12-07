/**
 * @file ec_node_tasks.c
 * @brief FreeRTOS задачи для ec_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - heartbeat_task_start_default - публикация heartbeat через общий компонент
 */

#include "ec_node_app.h"
#include "ec_node_framework_integration.h"
#include "node_watchdog.h"
#include "mqtt_manager.h"
#include "heartbeat_task.h"
#include "oled_ui.h"
#include "trema_ec.h"
#include "connection_status.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "freertos/task.h"
#include <string.h>
#include <math.h>
#include <stdbool.h>

static const char *TAG = "ec_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    3000  // 3 секунды - опрос EC датчика

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
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(2000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // Периодически сбрасываем watchdog во время ожидания
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для опроса сенсора
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();
            
            // Publish EC telemetry только если MQTT подключен
            if (mqtt_manager_is_connected()) {
                // Публикация телеметрии EC через node_framework
                // Используем callback из ec_node_framework_integration
                extern esp_err_t ec_node_publish_telemetry_callback(void *);
                ec_node_publish_telemetry_callback(NULL);
            } else {
                ESP_LOGW(TAG, "MQTT not connected, skipping sensor poll");
            }
            
            // Update OLED UI with current EC values (EC-специфичная логика)
            // Обновляем OLED независимо от MQTT подключения
            if (ec_node_is_oled_initialized()) {
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
                    
                    // Get current EC value and sensor status (EC-специфичная логика)
                    // trema_ec использует дефолтную шину (I2C_BUS_0)
                    bool sensor_initialized = ec_node_is_ec_sensor_initialized();
                    bool i2c_bus_ok = i2c_bus_is_initialized_bus(I2C_BUS_0);
                    
                    // Инициализируем статус датчика
                    model.sensor_status.i2c_connected = false;
                    model.sensor_status.using_stub = false;
                    model.sensor_status.has_error = false;
                    model.sensor_status.error_msg[0] = '\0';
                    // Инициализируем EC как NaN, чтобы не показывать 0.00
                    model.ec_value = NAN;
                    
                    if (i2c_bus_ok) {
                        // Проверяем подключение I2C - пытаемся прочитать model ID
                        uint8_t reg_model = 0x04;  // REG_MODEL для Trema EC
                        uint8_t model_id = 0;
                        esp_err_t i2c_err = i2c_bus_read_bus(I2C_BUS_0, 0x08, &reg_model, 1, &model_id, 1, 200);  // TREMA_EC_ADDR = 0x08
                        
                        if (i2c_err == ESP_OK && model_id == 0x19) {  // EC sensor model ID = 0x19
                            model.sensor_status.i2c_connected = true;
                            
                            // Если датчик подключен, пытаемся прочитать значение
                            if (sensor_initialized) {
                                float ec_value = 0.0f;
                                bool read_success = trema_ec_read(&ec_value);
                                bool using_stub = trema_ec_is_using_stub_values();
                                
                                // Проверяем валидность значения: EC должен быть в диапазоне 0-20 mS/cm
                                if (read_success && !isnan(ec_value) && isfinite(ec_value) && 
                                    ec_value >= 0.0f && ec_value <= 20.0f && ec_value != 0.0f) {
                                    model.ec_value = ec_value;
                                    model.sensor_status.using_stub = using_stub;
                                    if (using_stub) {
                                        model.sensor_status.has_error = true;
                                        model.ec_value = NAN;  // Не показываем stub значение
                                        strncpy(model.sensor_status.error_msg, "No sensor", sizeof(model.sensor_status.error_msg) - 1);
                                    }
                                } else {
                                    // Невалидное значение или ошибка чтения
                                    model.sensor_status.has_error = true;
                                    model.sensor_status.using_stub = true;
                                    model.ec_value = NAN;  // Устанавливаем NaN, чтобы не показывать 0.00
                                    strncpy(model.sensor_status.error_msg, "Read failed", sizeof(model.sensor_status.error_msg) - 1);
                                }
                            } else {
                                // Датчик подключен, но не инициализирован
                                model.sensor_status.has_error = true;
                                model.ec_value = NAN;
                                strncpy(model.sensor_status.error_msg, "Not init", sizeof(model.sensor_status.error_msg) - 1);
                            }
                        } else {
                            // I2C ошибка - датчик не отвечает
                            model.sensor_status.i2c_connected = false;
                            model.sensor_status.has_error = true;
                            model.sensor_status.using_stub = true;
                            model.ec_value = NAN;  // Устанавливаем NaN
                            if (i2c_err == ESP_ERR_INVALID_STATE || i2c_err == ESP_ERR_TIMEOUT) {
                                strncpy(model.sensor_status.error_msg, "I2C NACK", sizeof(model.sensor_status.error_msg) - 1);
                            } else if (i2c_err == ESP_ERR_NOT_FOUND) {
                                strncpy(model.sensor_status.error_msg, "No device", sizeof(model.sensor_status.error_msg) - 1);
                            } else {
                                strncpy(model.sensor_status.error_msg, "I2C Error", sizeof(model.sensor_status.error_msg) - 1);
                            }
                        }
                    } else {
                        // I2C шина не инициализирована
                        model.sensor_status.i2c_connected = false;
                        model.sensor_status.has_error = true;
                        model.sensor_status.using_stub = true;
                        model.ec_value = NAN;  // Устанавливаем NaN
                        strncpy(model.sensor_status.error_msg, "I2C bus down", sizeof(model.sensor_status.error_msg) - 1);
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
void ec_node_start_tasks(void) {
    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Общая задача heartbeat из компонента
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}
