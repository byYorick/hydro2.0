/**
 * @file light_node_tasks.c
 * @brief FreeRTOS задачи для light_node
 * 
 * Реализует периодические задачи:
 * - task_sensors - опрос датчика освещенности
 * - heartbeat_task_start_default - публикация heartbeat через общий компонент
 */

#include "light_node_app.h"
#include "light_node_framework_integration.h"
#include "node_watchdog.h"
#include "mqtt_manager.h"
#include "heartbeat_task.h"
#include "oled_ui.h"
#include "trema_light.h"
#include "connection_status.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "freertos/task.h"
#include <math.h>
#include <string.h>

static const char *TAG = "light_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    5000  // 5 секунд - опрос датчика освещенности

/**
 * @brief Задача опроса сенсоров
 */
static void task_sensors(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor task started");

    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add sensor task to watchdog: %s", esp_err_to_name(wdt_err));
    }

    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(2000);
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

            // Публикация телеметрии через node_framework
            if (mqtt_manager_is_connected()) {
                light_node_publish_telemetry_callback(NULL);
            }
            
            // Обновление OLED UI с данными датчика
            if (oled_ui_is_initialized()) {
                connection_status_t conn_status;
                if (connection_status_get(&conn_status) == ESP_OK) {
                    oled_ui_model_t model = {0};
                    
                    // Инициализируем неиспользуемые поля как NaN
                           model.ph_value = NAN;
                           model.ec_value = NAN;
                           model.temperature_air = NAN;
                           model.temperature_water = NAN;
                           model.humidity = NAN;
                           model.co2 = NAN;
                           model.lux_value = NAN;
                    
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
                    
                    // Чтение освещенности (Trema light sensor)
                    bool i2c_bus_ok = i2c_bus_is_initialized_bus(I2C_BUS_0);
                    
                    model.sensor_status.i2c_connected = false;
                    model.sensor_status.using_stub = false;
                    model.sensor_status.has_error = false;
                    model.sensor_status.error_msg[0] = '\0';
                    
                    float light_lux = NAN;
                    
                    if (i2c_bus_ok) {
                        uint8_t reg_model = REG_MODEL;
                        uint8_t model_id = 0;
                        esp_err_t i2c_err = i2c_bus_read_bus(I2C_BUS_0, TREMA_LIGHT_ADDR, &reg_model, 1, &model_id, 1, 200);
                        
                        // Принимаем как 0x06, так и 0x1B (разные версии датчика)
                        if (i2c_err == ESP_OK && (model_id == TREMA_LIGHT_MODEL_ID || model_id == 0x1B)) {
                            ESP_LOGI(TAG, "Light sensor detected: model_id=0x%02X, address=0x%02X", model_id, TREMA_LIGHT_ADDR);
                            model.sensor_status.i2c_connected = true;
                            
                            bool read_success = trema_light_read(&light_lux);
                            bool using_stub = trema_light_is_using_stub_values();
                            
                            if (read_success && !isnan(light_lux) && isfinite(light_lux) && light_lux >= 0.0f) {
                                ESP_LOGI(TAG, "Light sensor value: %.0f lux", light_lux);
                                model.lux_value = light_lux;  // Используем правильное поле lux_value
                                model.sensor_status.using_stub = using_stub;
                                model.sensor_status.has_error = false;  // Нет ошибки, если значение валидное
                                model.sensor_status.error_msg[0] = '\0';  // Очищаем сообщение об ошибке
                                if (using_stub) {
                                    ESP_LOGW(TAG, "Sensor returned stub value, marking as error");
                                    model.sensor_status.has_error = true;
                                    model.lux_value = NAN;
                                    strncpy(model.sensor_status.error_msg, "No sensor", sizeof(model.sensor_status.error_msg) - 1);
                                    model.sensor_status.error_msg[sizeof(model.sensor_status.error_msg) - 1] = '\0';
                                }
                            } else {
                                model.sensor_status.has_error = true;
                                model.sensor_status.using_stub = true;
                                model.lux_value = NAN;
                                strncpy(model.sensor_status.error_msg, "Read failed", sizeof(model.sensor_status.error_msg) - 1);
                                model.sensor_status.error_msg[sizeof(model.sensor_status.error_msg) - 1] = '\0';
                            }
                        } else {
                            ESP_LOGW(TAG, "Light sensor not detected: i2c_err=%s (code=%d), model_id=0x%02X (expected 0x%02X or 0x1B)", 
                                     esp_err_to_name(i2c_err), i2c_err, model_id, TREMA_LIGHT_MODEL_ID);
                            model.sensor_status.i2c_connected = false;
                            model.sensor_status.has_error = true;
                            model.sensor_status.using_stub = true;
                            model.lux_value = NAN;
                            if (i2c_err == ESP_ERR_INVALID_STATE || i2c_err == ESP_ERR_TIMEOUT) {
                                strncpy(model.sensor_status.error_msg, "I2C NACK", sizeof(model.sensor_status.error_msg) - 1);
                            } else if (i2c_err == ESP_ERR_NOT_FOUND) {
                                strncpy(model.sensor_status.error_msg, "No device", sizeof(model.sensor_status.error_msg) - 1);
                            } else {
                                strncpy(model.sensor_status.error_msg, "I2C Error", sizeof(model.sensor_status.error_msg) - 1);
                            }
                            model.sensor_status.error_msg[sizeof(model.sensor_status.error_msg) - 1] = '\0';
                        }
                    } else {
                        model.sensor_status.i2c_connected = false;
                        model.sensor_status.has_error = true;
                        model.sensor_status.using_stub = true;
                        model.lux_value = NAN;
                        strncpy(model.sensor_status.error_msg, "I2C bus down", sizeof(model.sensor_status.error_msg) - 1);
                        model.sensor_status.error_msg[sizeof(model.sensor_status.error_msg) - 1] = '\0';
                    }
                    
                    model.alert = false;
                    model.paused = false;
                    
                    oled_ui_update_model(&model);
                }
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
void light_node_start_tasks(void) {
    ESP_LOGI(TAG, "Starting FreeRTOS tasks...");
    
    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);
    
    // Общая задача heartbeat из компонента
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}
