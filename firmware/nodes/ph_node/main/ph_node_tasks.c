/**
 * @file ph_node_tasks.c
 * @brief FreeRTOS задачи и телеметрия для ph_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors — ph_node_ph_poll_sensor_once + MQTT/OLED из снимка trema_ph
 * - ph_node_publish_telemetry — публикация pH только из очереди (после poll)
 * 
 * Примечание: heartbeat задача вынесена в компонент heartbeat_task
 */

#include "ph_node_app.h"
#include "ph_node_defaults.h"
#include "correction_node_contract.h"
#include "ph_node_framework_integration.h"
#include "mqtt_manager.h"
#include "oled_ui.h"
#include "trema_ph.h"
#include "connection_status.h"
#include "heartbeat_task.h"
#include "config_storage.h"
#include "i2c_bus.h"
#include "ina209.h"
#include "pump_driver.h"
#include "node_telemetry_engine.h"
#include "node_state_manager.h"
#include "node_utils.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_idf_version.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "node_watchdog.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "cJSON.h"
#include <math.h>
#include <float.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

static const char *TAG = "ph_node_tasks";

/** Очередь глубины 1: снимок pH после ph_node_ph_poll_sensor_once → trema_ph_read (см. trema_ph_bind_sample_queue). */
static QueueHandle_t s_ph_meas_queue;

// Период опроса датчика (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS PH_NODE_PH_SENSOR_POLL_INTERVAL_MS
#define PUMP_CURRENT_POLL_INTERVAL_MS 5000  // 5 секунд - опрос тока насосов (по умолчанию)
#define STATUS_PUBLISH_INTERVAL_MS CORRECTION_NODE_STATUS_PUBLISH_INTERVAL_MS

/**
 * @brief Задача опроса сенсоров
 * 
 * Периодически опрашивает pH датчик и публикует телеметрию
 * Согласно NODE_ARCH_FULL.md раздел 6
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

            /* Один poll за тик (как ec_node): I²C в trema_ph; MQTT/OLED — только из очереди снимка. */
            ph_node_ph_poll_sensor_once();

            if (mqtt_manager_is_connected()) {
                ph_node_publish_telemetry();
            } else {
                connection_status_t cs = {0};
                bool wifi_up = (connection_status_get(&cs) == ESP_OK && cs.wifi_connected);
                if (wifi_up) {
                    ESP_LOGD(TAG, "MQTT ещё не подключён, опрос pH выполнен для OLED (Wi-Fi есть)");
                } else {
                    ESP_LOGW(TAG, "MQTT not connected, sensor poll done for OLED only");
                }
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
                    
                    // Get current pH value and sensor status (pH-специфичная логика)
                    bool sensor_initialized = ph_node_is_ph_sensor_initialized();
                    bool i2c_bus_ok = i2c_bus_is_initialized_bus(I2C_BUS_1);
                    
                    // Инициализируем статус датчика
                    model.sensor_status.i2c_connected = false;
                    model.sensor_status.using_stub = false;
                    model.sensor_status.has_error = false;
                    model.sensor_status.error_msg[0] = '\0';
                    // Инициализируем pH как NaN, чтобы не показывать 0.00
                    model.ph_value = NAN;
                    
                    if (i2c_bus_ok) {
                        if (ph_node_ph_last_poll_chip_present()) {
                            model.sensor_status.i2c_connected = true;

                            // Значение только из снимка очереди (без повторного trema_ph_read)
                            if (sensor_initialized) {
                                float ph_value = 0.0f;
                                bool read_success = false;
                                bool using_stub = false;
                                trema_ph_measurement_t snap;
                                if (trema_ph_try_cached_measurement(&snap, PH_NODE_PH_TELEMETRY_CACHE_MAX_AGE_MS) &&
                                    snap.valid && !isnan(snap.ph) && isfinite(snap.ph) && snap.ph >= 0.0f &&
                                    snap.ph <= 14.0f) {
                                    ph_value = snap.ph;
                                    read_success = true;
                                    using_stub = false;
                                } else {
                                    read_success = false;
                                }

                                // Проверяем валидность значения: pH должен быть в диапазоне 0-14
                                if (read_success && !isnan(ph_value) && isfinite(ph_value) && 
                                    ph_value >= 0.0f && ph_value <= 14.0f && ph_value != 0.0f) {
                                    model.ph_value = ph_value;
                                    model.sensor_status.using_stub = using_stub;
                                    if (using_stub) {
                                        model.sensor_status.has_error = true;
                                        model.ph_value = NAN;  // Не показываем stub значение
                                        strncpy(model.sensor_status.error_msg, "No sensor", sizeof(model.sensor_status.error_msg) - 1);
                                    }
                                } else {
                                    // Невалидное значение или ошибка чтения
                                    model.sensor_status.has_error = true;
                                    model.sensor_status.using_stub = true;
                                    model.ph_value = NAN;  // Устанавливаем NaN, чтобы не показывать 0.00
                                    strncpy(model.sensor_status.error_msg, "Read failed", sizeof(model.sensor_status.error_msg) - 1);
                                }
                            } else {
                                // Датчик подключен, но не инициализирован
                                model.sensor_status.has_error = true;
                                model.ph_value = NAN;
                                strncpy(model.sensor_status.error_msg, "Not init", sizeof(model.sensor_status.error_msg) - 1);
                            }
                        } else {
                            model.sensor_status.i2c_connected = false;
                            model.sensor_status.has_error = true;
                            model.sensor_status.using_stub = true;
                            model.ph_value = NAN;
                            strncpy(
                                model.sensor_status.error_msg,
                                "pH module probe fail",
                                sizeof(model.sensor_status.error_msg) - 1
                            );
                        }
                    } else {
                        // I2C шина не инициализирована
                        model.sensor_status.i2c_connected = false;
                        model.sensor_status.has_error = true;
                        model.sensor_status.using_stub = true;
                        model.ph_value = NAN;  // Устанавливаем NaN
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
 * @brief Задача опроса тока насосов (INA209)
 * 
 * Периодически опрашивает INA209 и публикует телеметрию pump_bus_current
 * Согласно NODE_CHANNELS_REFERENCE.md раздел 3.4
 */
static void task_pump_current(void *pvParameters) {
    ESP_LOGI(TAG, "Pump current task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
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
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для опроса тока
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();
            
            if (mqtt_manager_is_connected()) {
                // Публикация telemetry тока насосов
                ph_node_publish_pump_current_telemetry();
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
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add status task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(STATUS_PUBLISH_INTERVAL_MS);
    
    // Сбрасываем watchdog каждую секунду, чтобы иметь запас к системному таймауту
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(1000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        // Периодически сбрасываем watchdog во время ожидания
        // (интервал задачи 60 сек > watchdog таймаут 10 сек)
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        // TickType_t - беззнаковый тип, переполнение работает по модулю, поэтому
        // разница всегда корректна и не может быть отрицательной
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        // Проверяем, наступило ли время для публикации STATUS
        TickType_t elapsed_since_wake = current_time - last_wake_time;
        if (elapsed_since_wake >= interval) {
            // Сбрасываем watchdog перед выполнением работы
            node_watchdog_reset();
            
            if (mqtt_manager_is_connected()) {
                // Публикация STATUS
                ph_node_publish_status();
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
void ph_node_start_tasks(void) {
    s_ph_meas_queue = xQueueCreate(1, sizeof(trema_ph_measurement_t));
    if (s_ph_meas_queue == NULL) {
        ESP_LOGE(TAG, "xQueueCreate ph_meas failed — телеметрия только через trema_ph_read");
    } else {
        trema_ph_bind_sample_queue(s_ph_meas_queue);
    }

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
 * 
 * Использует node_telemetry_engine для унифицированной публикации телеметрии
 */
void ph_node_publish_telemetry(void) {
    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }

    float ph_value = NAN;
    bool using_stub = false;
    bool is_stable = true;
    int32_t raw_value = 0;

    trema_ph_measurement_t cached;
    if (trema_ph_try_cached_measurement(&cached, PH_NODE_PH_TELEMETRY_CACHE_MAX_AGE_MS) && cached.valid &&
        !isnan(cached.ph) && isfinite(cached.ph) && cached.ph >= 0.0f && cached.ph <= 14.0f) {
        ph_value = cached.ph;
        using_stub = false;
        raw_value = (int32_t)cached.raw_thousandths;
        is_stable = cached.stable;
    } else {
        ESP_LOGW(TAG, "pH telemetry skipped: cache miss or stale (no placeholder publish)");
        node_state_manager_report_error(
            ERROR_LEVEL_ERROR,
            "ph_sensor",
            ESP_ERR_INVALID_RESPONSE,
            "pH telemetry cache empty or stale"
        );
        return;
    }

    ESP_LOGI(
        TAG,
        "pH update: %.3f pH (raw=%ld, stub=%s, stable=%s)",
        (double)ph_value,
        (long)raw_value,
        using_stub ? "yes" : "no",
        is_stable ? "yes" : "no"
    );

    // Публикация через node_telemetry_engine (унифицированный API)
    const bool mode_active = ph_node_is_sensor_mode_active();
    const bool publish_stable = mode_active ? is_stable : false;
    esp_err_t err = node_telemetry_publish_sensor_with_flow_flags(
        "ph_sensor",
        METRIC_TYPE_PH,
        ph_value,
        "pH",
        raw_value,
        using_stub,
        publish_stable,
        mode_active,
        mode_active
    );
    
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish telemetry via node_telemetry_engine: %s", esp_err_to_name(err));
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
    
    // Публикация через node_telemetry_engine (унифицированный API)
    err = node_telemetry_publish_sensor(
        "pump_bus_current",
        METRIC_TYPE_CURRENT,
        reading.bus_current_ma,
        "mA",
        0,  // raw value не используется
        false,  // not stub
        true     // is_stable
    );
    
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish pump current telemetry: %s", esp_err_to_name(err));
    }
}

/**
 * @brief Publish STATUS message
 * 
 * Публикует статус узла согласно DEVICE_NODE_PROTOCOL.md раздел 4.2
 */
void ph_node_publish_status(void) {
    (void)node_utils_publish_device_status_extended();
}
