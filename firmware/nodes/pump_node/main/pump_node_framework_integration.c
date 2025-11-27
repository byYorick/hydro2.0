/**
 * @file pump_node_framework_integration.c
 * @brief Интеграция pump_node с node_framework
 * 
 * Этот файл связывает pump_node с унифицированным фреймворком node_framework,
 * заменяя дублирующуюся логику обработки конфигов, команд и телеметрии.
 */

#include "pump_node_framework_integration.h"
#include "node_framework.h"
#include "node_state_manager.h"
#include "node_config_handler.h"
#include "node_command_handler.h"
#include "node_telemetry_engine.h"
#include "pump_driver.h"
#include "ina209.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "cJSON.h"
#include <string.h>

static const char *TAG = "pump_node_framework";

// Forward declaration для callback safe_mode
static esp_err_t pump_node_disable_actuators_in_safe_mode(void *user_ctx);

/**
 * @brief Callback для инициализации каналов при применении конфигурации
 */
static esp_err_t pump_node_init_channel_callback(const char *channel_name, const cJSON *channel_config, void *user_ctx) {
    (void)user_ctx;
    
    if (channel_config == NULL || channel_name == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Инициализация насосов обрабатывается через config_apply_channels_pump
    // Этот callback вызывается для каждого канала, но насосы инициализируются централизованно
    ESP_LOGD(TAG, "Channel init callback for: %s", channel_name);
    
    return ESP_OK;
}

/**
 * @brief Обработчик команды run_pump
 */
static esp_err_t handle_run_pump(const char *channel, const cJSON *params, cJSON **response, void *user_ctx) {
    (void)user_ctx;
    
    if (channel == NULL || params == NULL || response == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    cJSON *duration_item = cJSON_GetObjectItem(params, "duration_ms");
    if (!cJSON_IsNumber(duration_item)) {
        *response = node_command_handler_create_response(NULL, "ERROR", "missing_duration", "duration_ms is required", NULL);
        return ESP_ERR_INVALID_ARG;
    }
    
    int duration_ms = (int)cJSON_GetNumberValue(duration_item);
    ESP_LOGI(TAG, "Running pump on channel %s for %d ms", channel, duration_ms);
    
    // Реальная логика управления насосом через pump_driver
    // pump_driver автоматически проверяет ток через INA209 при запуске
    esp_err_t err = pump_driver_run(channel, duration_ms);
    
    // cmd_id будет добавлен автоматически в node_command_handler_process
    if (err == ESP_OK) {
        *response = node_command_handler_create_response(NULL, "ACK", NULL, NULL, NULL);
    } else {
        const char *error_code = "pump_driver_failed";
        const char *error_message = esp_err_to_name(err);
        
        // Определяем тип ошибки на основе кода ошибки
        if (err == ESP_ERR_INVALID_RESPONSE) {
            error_code = "current_not_detected";
            error_message = "Pump started but no current detected";
        } else if (err == ESP_ERR_INVALID_SIZE) {
            error_code = "overcurrent";
            error_message = "Pump current exceeds safe limit";
        }
        
        *response = node_command_handler_create_response(NULL, "ERROR", error_code, error_message, NULL);
    }
    
    // Добавляем health информацию в ответ
    if (*response != NULL) {
        pump_driver_channel_health_t stats;
        if (pump_driver_get_channel_health(channel, &stats) == ESP_OK) {
            cJSON *health = cJSON_CreateObject();
            if (health) {
                cJSON_AddStringToObject(health, "channel", stats.channel_name);
                cJSON_AddBoolToObject(health, "running", stats.is_running);
                cJSON_AddBoolToObject(health, "last_run_success", stats.last_run_success);
                cJSON_AddNumberToObject(health, "last_run_ms", (double)stats.last_run_duration_ms);
                cJSON_AddNumberToObject(health, "run_count", (double)stats.run_count);
                cJSON_AddNumberToObject(health, "failure_count", (double)stats.failure_count);
                cJSON_AddNumberToObject(health, "overcurrent_events", (double)stats.overcurrent_events);
                cJSON_AddNumberToObject(health, "no_current_events", (double)stats.no_current_events);
                cJSON_AddNumberToObject(health, "last_start_ts", (double)stats.last_start_timestamp_ms);
                cJSON_AddNumberToObject(health, "last_stop_ts", (double)stats.last_stop_timestamp_ms);
                cJSON_AddItemToObject(*response, "health", health);
            }
        }
    }
    
    return err;
}

/**
 * @brief Callback для публикации телеметрии pump
 */
esp_err_t pump_node_publish_telemetry_callback(void *user_ctx) {
    (void)user_ctx;
    
    // Убрана проверка mqtt_manager_is_connected - батч телеметрии работает даже при оффлайне
    // Данные будут сохранены в батч и отправлены после восстановления связи
    
    // Чтение тока из INA209
    ina209_reading_t reading;
    esp_err_t err = ina209_read(&reading);
    
    if (err == ESP_OK && reading.valid) {
        // Публикация телеметрии тока насоса
        // Используем батч телеметрии, который работает даже при оффлайне
        // unit передается корректно, raw поддерживает отрицательные значения
        // stable=true, так как reading.valid=true означает валидное значение
        node_telemetry_publish_sensor("pump_bus_current", METRIC_TYPE_CURRENT, 
                                      reading.bus_current_ma, "mA", 
                                      (int32_t)reading.bus_current_ma, false, true);
        
        // Дополнительные поля можно добавить через расширенный API, если нужно
        // Пока публикуем только основное значение
    } else {
        ESP_LOGW(TAG, "Failed to read INA209: %s", esp_err_to_name(err));
        // Не возвращаем ошибку - продолжаем работу даже при ошибке чтения INA209
        // Это позволяет не терять другие данные телеметрии
    }
    
    return ESP_OK;
}

/**
 * @brief Wrapper для обработки config сообщений через node_framework
 */
static void pump_node_config_handler_wrapper(const char *topic, const char *data, int data_len, void *user_ctx) {
    node_config_handler_process(topic, data, data_len, user_ctx);
}

/**
 * @brief Wrapper для обработки command сообщений через node_framework
 */
static void pump_node_command_handler_wrapper(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    node_command_handler_process(topic, channel, data, data_len, user_ctx);
}

/**
 * @brief Инициализация интеграции pump_node с node_framework
 */
esp_err_t pump_node_framework_init_integration(void) {
    ESP_LOGI(TAG, "Initializing pump_node framework integration...");
    
    // Конфигурация node_framework
    node_framework_config_t config = {
        .node_type = "pump",
        .channel_init_cb = pump_node_init_channel_callback,
        .telemetry_cb = pump_node_publish_telemetry_callback,
        .user_ctx = NULL
    };
    
    esp_err_t err = node_framework_init(&config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(err));
        return err;
    }
    
    // Регистрация обработчиков команд
    err = node_command_handler_register("run_pump", handle_run_pump, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register run_pump handler: %s", esp_err_to_name(err));
        return err;
    }

    // Регистрация callback для отключения актуаторов в safe_mode
    err = node_state_manager_register_safe_mode_callback(pump_node_disable_actuators_in_safe_mode, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to register safe mode callback: %s", esp_err_to_name(err));
    }
    
    ESP_LOGI(TAG, "pump_node framework integration initialized");
    return ESP_OK;
}

// Callback для отключения актуаторов в safe_mode
static esp_err_t pump_node_disable_actuators_in_safe_mode(void *user_ctx) {
    (void)user_ctx;
    ESP_LOGW(TAG, "Disabling all actuators in safe mode");
    return pump_driver_emergency_stop();
}

/**
 * @brief Регистрация MQTT обработчиков через node_framework
 */
void pump_node_framework_register_mqtt_handlers(void) {
    mqtt_manager_register_config_cb(pump_node_config_handler_wrapper, NULL);
    mqtt_manager_register_command_cb(pump_node_command_handler_wrapper, NULL);
    ESP_LOGI(TAG, "MQTT handlers registered via node_framework");
}

