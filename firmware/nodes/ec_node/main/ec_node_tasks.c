/**
 * @file ec_node_tasks.c
 * @brief FreeRTOS задачи для ec_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - heartbeat_task_start_default - публикация heartbeat через общий компонент
 */

#include "ec_node_app.h"
#include "ec_node_defaults.h"
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
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <string.h>
#include <math.h>
#include <stdbool.h>

static const char *TAG = "ec_node_tasks";

/** Очередь глубины 1: снимок EC после телеметрии (`trema_ec_push_telemetry_snapshot` в publish callback). */
static QueueHandle_t s_ec_meas_queue;

/**
 * Стек sensor_task: publish callback держит на стеке `pump_driver_health_snapshot_t` (~2 КБ) + OLED-модель
 * и буферы config_storage в этой же задаче — 4096 недостаточно (см. climate_node SENSOR_TASK_STACK_SIZE).
 */
#define EC_NODE_SENSOR_TASK_STACK_SIZE 8192

// Периоды задач (в миллисекундах) — согласовано с EC_NODE_EC_SENSOR_POLL_INTERVAL_MS
#define SENSOR_POLL_INTERVAL_MS    EC_NODE_EC_SENSOR_POLL_INTERVAL_MS

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
            
            // Один trema_ec_read в ec_node_ec_poll_sensor_once → очередь; MQTT и OLED только из кэша.
            ec_node_ec_poll_sensor_once();

            if (mqtt_manager_is_connected()) {
                ec_node_publish_telemetry_callback(NULL);
            } else {
                connection_status_t cs = {0};
                bool wifi_up = (connection_status_get(&cs) == ESP_OK && cs.wifi_connected);
                if (wifi_up) {
                    ESP_LOGD(TAG, "MQTT ещё не подключён, пропуск опроса сенсора (Wi-Fi есть)");
                } else {
                    ESP_LOGW(TAG, "MQTT not connected, skipping sensor poll");
                }
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
                    char mqtt_host_buf[sizeof(model.mqtt_host)] = {0};
                    uint16_t mqtt_port_val = 0;
                    if (mqtt_manager_get_broker(mqtt_host_buf, sizeof(mqtt_host_buf), &mqtt_port_val) == ESP_OK) {
                        strncpy(model.mqtt_host, mqtt_host_buf, sizeof(model.mqtt_host) - 1);
                        model.mqtt_port = mqtt_port_val;
                    }
                    
                    // Get current EC value and sensor status (EC-специфичная логика)
                    bool sensor_initialized = ec_node_is_ec_sensor_initialized();
                    bool i2c_ec_bus_ok = i2c_bus_is_initialized_bus(I2C_BUS_1);
                    
                    // Инициализируем статус датчика
                    model.sensor_status.i2c_connected = false;
                    model.sensor_status.using_stub = false;
                    model.sensor_status.has_error = false;
                    model.sensor_status.error_msg[0] = '\0';
                    // Инициализируем EC как NaN, чтобы не показывать 0.00
                    model.ec_value = NAN;
                    
                    if (i2c_ec_bus_ok) {
                        const bool chip_on_wire = trema_ec_probe_present();

                        if (chip_on_wire) {
                            model.sensor_status.i2c_connected = true;

                            if (sensor_initialized) {
                                float ec_value = 0.0f;
                                bool read_success = false;
                                bool using_stub = false;
                                trema_ec_measurement_t snap;
                                if (trema_ec_try_cached_measurement(&snap, EC_NODE_EC_CACHE_MAX_AGE_MS) && snap.valid &&
                                    !isnan(snap.ec_mScm) && isfinite(snap.ec_mScm) &&
                                    snap.ec_mScm >= 0.0f && snap.ec_mScm <= 20.0f && snap.ec_mScm != 0.0f) {
                                    ec_value = snap.ec_mScm;
                                    read_success = true;
                                    using_stub = snap.using_stub;
                                } else {
                                    read_success = false;
                                }

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
                            /* Нет ответа Trema по текущему адресу (до/вне init) — без прямого I²C в обход драйвера. */
                            model.sensor_status.i2c_connected = false;
                            model.sensor_status.has_error = true;
                            model.sensor_status.using_stub = true;
                            model.ec_value = NAN;
                            strncpy(model.sensor_status.error_msg, "No device", sizeof(model.sensor_status.error_msg) - 1);
                        }
                    } else {
                        // I2C шина не инициализирована
                        model.sensor_status.i2c_connected = false;
                        model.sensor_status.has_error = true;
                        model.sensor_status.using_stub = true;
                        model.ec_value = NAN;  // Устанавливаем NaN
                        strncpy(model.sensor_status.error_msg, "EC bus1 down", sizeof(model.sensor_status.error_msg) - 1);
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
    s_ec_meas_queue = xQueueCreate(1, sizeof(trema_ec_measurement_t));
    if (s_ec_meas_queue == NULL) {
        ESP_LOGE(TAG, "xQueueCreate ec_meas failed — OLED без снимка из очереди телеметрии");
    } else {
        trema_ec_bind_sample_queue(s_ec_meas_queue);
    }

    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", EC_NODE_SENSOR_TASK_STACK_SIZE, NULL, 5, NULL);
    
    // Общая задача heartbeat из компонента
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}
