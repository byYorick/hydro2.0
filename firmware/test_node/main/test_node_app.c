/**
 * @file test_node_app.c
 * @brief Тестовая прошивка для проверки форматов сообщений согласно эталону node-sim
 * 
 * Эта прошивка публикует телеметрию, отвечает на команды и отправляет heartbeat
 * в формате, соответствующем эталону node-sim для E2E тестов.
 */

#include "test_node_app.h"
#include "mqtt_manager.h"
#include "node_telemetry_engine.h"
#include "node_framework.h"
#include "node_command_handler.h"
#include "heartbeat_task.h"
#include "config_storage.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "cJSON.h"

static const char *TAG = "test_node";

// Тестовые значения для публикации
static float test_ph_value = 6.5f;
static float test_ec_value = 2.0f;
static float test_temp_value = 24.5f;
static float test_rh_value = 60.0f;

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
        
        // pH телеметрия
        node_telemetry_publish_sensor(
            "ph_sensor",
            METRIC_TYPE_PH,
            test_ph_value,
            "pH",
            0,
            false,
            true
        );
        
        // EC телеметрия
        node_telemetry_publish_sensor(
            "ec_sensor",
            METRIC_TYPE_EC,
            test_ec_value,
            "mS/cm",
            0,
            false,
            true
        );
        
        // Температура воздуха
        node_telemetry_publish_sensor(
            "air_temp_c",
            METRIC_TYPE_TEMPERATURE,
            test_temp_value,
            "°C",
            0,
            false,
            true
        );
        
        // Влажность воздуха
        node_telemetry_publish_sensor(
            "air_rh",
            METRIC_TYPE_HUMIDITY,
            test_rh_value,
            "%",
            0,
            false,
            true
        );
        
        // Принудительная отправка батча
        node_telemetry_flush();
    }
}

/**
 * @brief Callback для обработки команд
 * 
 * Примечание: node_framework передает cmd_name и params отдельно,
 * но cmd_id находится внутри params. Используем node_command_handler_create_response
 * для создания правильного формата ответа.
 */
static esp_err_t test_command_handler(
    const char *channel,
    const char *cmd_name,
    const cJSON *params,
    cJSON **response,
    void *user_ctx
) {
    ESP_LOGI(TAG, "Command received: %s on channel %s", cmd_name, channel);
    
    // Извлекаем cmd_id из params (node_framework передает его там)
    const char *cmd_id = "test-cmd-unknown";
    if (params) {
        cJSON *cmd_id_item = cJSON_GetObjectItem(params, "cmd_id");
        if (cmd_id_item && cJSON_IsString(cmd_id_item)) {
            cmd_id = cmd_id_item->valuestring;
        }
    }
    
    // Используем стандартную функцию для создания ответа
    // Она правильно форматирует ts в миллисекундах
    *response = node_command_handler_create_response(
        cmd_id,
        "DONE",
        NULL,
        "OK",
        NULL
    );
    
    if (!*response) {
        ESP_LOGE(TAG, "Failed to create command response");
        return ESP_ERR_NO_MEM;
    }
    
    ESP_LOGI(TAG, "Command response created: cmd_id=%s, status=DONE", cmd_id);
    
    return ESP_OK;
}

/**
 * @brief Инициализация тестовой ноды
 */
esp_err_t test_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing test node...");
    
    // Инициализация node_framework
    node_framework_config_t config = {
        .node_type = "test",
        .default_node_id = "nd-test-001",
        .default_gh_uid = "gh-test-1",
        .default_zone_uid = "zn-test-1",
        .command_handler_cb = test_command_handler,
        .telemetry_cb = NULL, // Используем задачу напрямую
        .user_ctx = NULL
    };
    
    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
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
    
    // Запуск heartbeat (использует компонент heartbeat_task)
    heartbeat_task_start_default();
    
    ESP_LOGI(TAG, "Test node initialized successfully");
    return ESP_OK;
}

