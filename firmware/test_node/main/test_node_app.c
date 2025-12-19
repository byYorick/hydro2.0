/**
 * @file test_node_app.c
 * @brief Упрощенная тестовая прошивка для проверки форматов сообщений согласно эталону node-sim
 * 
 * Эта прошивка публикует телеметрию, отвечает на команды и отправляет heartbeat
 * в формате, соответствующем эталону node-sim для E2E тестов.
 * 
 * Упрощенная версия без node_framework для уменьшения размера прошивки.
 */

#include "test_node_app.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "node_utils.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "test_node";

// Конфигурация узла
#define DEFAULT_NODE_ID "nd-test-001"
#define DEFAULT_GH_UID "gh-test-1"
#define DEFAULT_ZONE_UID "zn-test-1"

// Тестовые значения для публикации
static float test_ph_value = 6.5f;
static float test_ec_value = 2.0f;
static float test_temp_value = 24.5f;
static float test_rh_value = 60.0f;

// Глобальные переменные для node_info
static mqtt_node_info_t s_node_info = {
    .gh_uid = DEFAULT_GH_UID,
    .zone_uid = DEFAULT_ZONE_UID,
    .node_uid = DEFAULT_NODE_ID
};

// Время старта для расчета uptime
static int64_t s_start_time_seconds = 0;

/**
 * @brief Получить текущее время в секундах
 */
static int64_t get_timestamp_seconds(void) {
    return esp_timer_get_time() / 1000000LL;
}

/**
 * @brief Получить текущее время в миллисекундах
 */
static int64_t get_timestamp_ms(void) {
    return esp_timer_get_time() / 1000LL;
}

/**
 * @brief Публикация телеметрии в формате node-sim
 */
static void publish_telemetry_value(const char *channel, const char *metric_type, float value) {
    if (!mqtt_manager_is_connected()) {
        return;
    }

    cJSON *json = cJSON_CreateObject();
    if (!json) {
        ESP_LOGE(TAG, "Failed to create JSON object");
        return;
    }

    // Формат согласно node-sim: {metric_type, value, ts}
    cJSON_AddStringToObject(json, "metric_type", metric_type);
    cJSON_AddNumberToObject(json, "value", value);
    cJSON_AddNumberToObject(json, "ts", (double)get_timestamp_seconds());

    // Без форматирования, чтобы уменьшить размер строки и аллокации heap
    char *json_str = cJSON_PrintUnformatted(json);
    if (json_str) {
        mqtt_manager_publish_telemetry(channel, json_str);
        free(json_str);
    }

    cJSON_Delete(json);
}

/**
 * @brief Публикация heartbeat в формате node-sim
 */
static void publish_heartbeat(void) {
    if (!mqtt_manager_is_connected()) {
        return;
    }

    cJSON *json = cJSON_CreateObject();
    if (!json) {
        ESP_LOGE(TAG, "Failed to create JSON object for heartbeat");
        return;
    }

    // Формат согласно node-sim: {uptime, free_heap, rssi?}
    // НЕТ поля ts в heartbeat!
    // uptime - это время работы с момента старта в секундах
    int64_t current_time = get_timestamp_seconds();
    int64_t uptime_seconds = s_start_time_seconds > 0 ? (current_time - s_start_time_seconds) : 0;
    cJSON_AddNumberToObject(json, "uptime", (double)uptime_seconds);
    
    uint32_t free_heap = esp_get_free_heap_size();
    cJSON_AddNumberToObject(json, "free_heap", (double)free_heap);
    
    // RSSI опционально
    wifi_ap_record_t ap_info;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        cJSON_AddNumberToObject(json, "rssi", (double)ap_info.rssi);
    }

    // Без форматирования, чтобы сократить размер payload
    char *json_str = cJSON_PrintUnformatted(json);
    if (json_str) {
        mqtt_manager_publish_heartbeat(json_str);
        free(json_str);
    }

    cJSON_Delete(json);
}

/**
 * @brief Задача публикации телеметрии
 */
static void task_publish_telemetry(void *pvParameters) {
    ESP_LOGI(TAG, "Telemetry publishing task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(5000); // 5 секунд
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!mqtt_manager_is_connected()) {
            ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
            continue;
        }
        
        // Публикация телеметрии в формате эталона node-sim
        ESP_LOGI(TAG, "Publishing test telemetry");
        
        publish_telemetry_value("ph_sensor", "ph", test_ph_value);
        publish_telemetry_value("ec_sensor", "ec", test_ec_value);
        publish_telemetry_value("air_temp_c", "temperature", test_temp_value);
        publish_telemetry_value("air_rh", "humidity", test_rh_value);
    }
}

/**
 * @brief Задача публикации heartbeat
 */
static void task_heartbeat(void *pvParameters) {
    ESP_LOGI(TAG, "Heartbeat task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(15000); // 15 секунд
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!mqtt_manager_is_connected()) {
            continue;
        }
        
        publish_heartbeat();
    }
}

/**
 * @brief Callback для обработки команд
 */
static void command_callback(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Command received on topic: %s, channel: %s", topic, channel);
    
    // Парсим команду
    cJSON *cmd_json = cJSON_ParseWithLength(data, data_len);
    if (!cmd_json) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    cJSON *cmd_id_item = cJSON_GetObjectItem(cmd_json, "cmd_id");
    const char *cmd_id = cmd_id_item && cJSON_IsString(cmd_id_item) 
        ? cmd_id_item->valuestring 
        : "unknown";
    
    ESP_LOGI(TAG, "Processing command: cmd_id=%s, channel=%s", cmd_id, channel);
    
    // Создаем ответ в формате node-sim: {cmd_id, status, details?, ts}
    cJSON *response = cJSON_CreateObject();
    cJSON_AddStringToObject(response, "cmd_id", cmd_id);
    cJSON_AddStringToObject(response, "status", "DONE");
    cJSON_AddStringToObject(response, "details", "OK");
    cJSON_AddNumberToObject(response, "ts", (double)get_timestamp_ms());
    
    // Без форматирования, чтобы уменьшить аллокации
    char *response_str = cJSON_PrintUnformatted(response);
    if (response_str) {
        mqtt_manager_publish_command_response(channel, response_str);
        free(response_str);
    }
    
    cJSON_Delete(response);
    cJSON_Delete(cmd_json);
}

/**
 * @brief Callback при подключении к MQTT
 */
static void mqtt_connected_callback(bool connected, void *user_ctx) {
    if (!connected) {
        return;
    }
    
    ESP_LOGI(TAG, "MQTT connected, publishing ONLINE status");
    
    // Публикуем статус ONLINE согласно спецификации
    cJSON *status_json = cJSON_CreateObject();
    cJSON_AddStringToObject(status_json, "status", "ONLINE");
    cJSON_AddNumberToObject(status_json, "ts", (double)get_timestamp_seconds());
    
    // Без форматирования, чтобы сократить payload
    char *status_str = cJSON_PrintUnformatted(status_json);
    if (status_str) {
        mqtt_manager_publish_status(status_str);
        free(status_str);
    }
    
    cJSON_Delete(status_json);
}

/**
 * @brief Инициализация тестовой ноды
 */
esp_err_t test_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing simplified test node...");
    
    // Сохраняем время старта для расчета uptime
    s_start_time_seconds = get_timestamp_seconds();
    
    // Инициализация config_storage
    esp_err_t err = config_storage_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize config_storage: %s", esp_err_to_name(err));
        return err;
    }
    
    // Инициализация WiFi
    err = wifi_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize wifi_manager: %s", esp_err_to_name(err));
        return err;
    }
    
    // Загружаем WiFi конфигурацию из config_storage
    char wifi_ssid[64];
    char wifi_password[64];
    wifi_manager_config_t wifi_config = {0};
    err = node_utils_init_wifi_config(&wifi_config, wifi_ssid, wifi_password);
    if (err == ESP_OK) {
        err = wifi_manager_connect(&wifi_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to connect wifi: %s", esp_err_to_name(err));
            return err;
        }
    } else {
        ESP_LOGW(TAG, "WiFi config not found, skipping WiFi connection");
    }
    
    // Загружаем MQTT конфигурацию из config_storage
    char mqtt_host[128];
    char mqtt_username[64];
    char mqtt_password[64];
    char node_id[64];
    char gh_uid[64];
    char zone_uid[64];
    mqtt_manager_config_t mqtt_config = {0};
    mqtt_node_info_t node_info = {0};
    
    err = node_utils_init_mqtt_config(
        &mqtt_config, &node_info,
        mqtt_host, mqtt_username, mqtt_password,
        node_id, gh_uid, zone_uid,
        DEFAULT_GH_UID, DEFAULT_ZONE_UID, DEFAULT_NODE_ID
    );
    
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load MQTT config: %s", esp_err_to_name(err));
        // Используем дефолтные значения
        mqtt_config = (mqtt_manager_config_t){
            .host = "localhost",
            .port = 1883,
            .keepalive = 60,
            .client_id = NULL,
            .username = NULL,
            .password = NULL,
            .use_tls = false
        };
        node_info = s_node_info;
    }
    
    // Инициализация MQTT
    err = mqtt_manager_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize mqtt_manager: %s", esp_err_to_name(err));
        return err;
    }
    
    // Регистрируем callback для команд
    mqtt_manager_register_command_cb(command_callback, NULL);
    
    // Регистрируем callback для подключения
    mqtt_manager_register_connection_cb(mqtt_connected_callback, NULL);
    
    // Запускаем MQTT
    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start mqtt_manager: %s", esp_err_to_name(err));
        return err;
    }
    
    // Запуск задачи публикации телеметрии
    xTaskCreate(
        task_publish_telemetry,
        "telemetry_task",
        4096,
        NULL,
        5,
        NULL
    );
    
    // Запуск задачи heartbeat
    xTaskCreate(
        task_heartbeat,
        "heartbeat_task",
        3072,
        NULL,
        3,
        NULL
    );
    
    ESP_LOGI(TAG, "Simplified test node initialized successfully");
    return ESP_OK;
}
