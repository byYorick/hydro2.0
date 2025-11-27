/**
 * @file pump_node_tasks.c
 * @brief FreeRTOS задачи для pump_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_heartbeat - публикация heartbeat
 * - task_current_poll - периодический опрос INA209
 * - task_pump_health - health-метрики насосов
 * 
 * Примечание: pump_node не имеет периодических сенсоров,
 * телеметрия публикуется только при выполнении команд (ток насоса)
 */

#include "mqtt_manager.h"
#include "ina209.h"
#include "config_storage.h"
#include "pump_driver.h"
#include "pump_node_framework_integration.h"
#include "node_telemetry_engine.h"
#include "node_utils.h"
#include "node_watchdog.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "pump_node_tasks";

// Периоды задач (в миллисекундах)
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat
#define DEFAULT_CURRENT_POLL_MS   1000  // 1 секунда по умолчанию для тока насоса
#define PUMP_HEALTH_INTERVAL_MS    10000 // 10 секунд - health отчеты

// Глобальная переменная для интервала опроса тока (потокобезопасно)
static uint32_t s_current_poll_interval_ms = DEFAULT_CURRENT_POLL_MS;
static SemaphoreHandle_t s_current_poll_interval_mutex = NULL;

/**
 * @brief Инициализация mutex для s_current_poll_interval_ms
 */
static void init_current_poll_interval_mutex(void) {
    if (s_current_poll_interval_mutex == NULL) {
        s_current_poll_interval_mutex = xSemaphoreCreateMutex();
        if (s_current_poll_interval_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create current poll interval mutex");
        }
    }
}

/**
 * @brief Потокобезопасное получение интервала опроса
 */
static uint32_t get_current_poll_interval(void) {
    init_current_poll_interval_mutex();
    uint32_t result = DEFAULT_CURRENT_POLL_MS;
    if (s_current_poll_interval_mutex != NULL && 
        xSemaphoreTake(s_current_poll_interval_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        result = s_current_poll_interval_ms;
        xSemaphoreGive(s_current_poll_interval_mutex);
    }
    return result;
}

/**
 * @brief Потокобезопасная установка интервала опроса
 */
static void set_current_poll_interval(uint32_t interval_ms) {
    init_current_poll_interval_mutex();
    if (s_current_poll_interval_mutex != NULL && 
        xSemaphoreTake(s_current_poll_interval_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        s_current_poll_interval_ms = interval_ms;
        xSemaphoreGive(s_current_poll_interval_mutex);
    }
}

/**
 * @brief Задача публикации heartbeat
 * 
 * Публикует heartbeat каждые 15 секунд согласно NODE_ARCH_FULL.md раздел 9
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
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        // Сбрасываем watchdog
        node_watchdog_reset();
        
        if (!mqtt_manager_is_connected()) {
            continue;
        }
        
        // Получение RSSI
        wifi_ap_record_t ap_info;
        int8_t rssi = -100;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            rssi = ap_info.rssi;
        }
        
        // Формат согласно MQTT_SPEC_FULL.md раздел 9.1
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
    }
}

/**
 * @brief Задача опроса тока насоса (INA209)
 * 
 * Периодически опрашивает INA209 и публикует телеметрию pump_bus_current
 * Интервал опроса берется из NodeConfig для канала "pump_bus_current"
 */
static void task_current_poll(void *pvParameters) {
    ESP_LOGI(TAG, "Current poll task started");
    
    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add current poll task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    TickType_t last_wake_time = xTaskGetTickCount();
    
    while (1) {
        // Получаем актуальный интервал из конфигурации (потокобезопасно)
        uint32_t poll_interval = get_current_poll_interval();
        const TickType_t interval = pdMS_TO_TICKS(poll_interval);
        
        vTaskDelayUntil(&last_wake_time, interval);
        
        // Сбрасываем watchdog
        node_watchdog_reset();
        
        if (!mqtt_manager_is_connected()) {
            ESP_LOGW(TAG, "MQTT not connected, skipping current poll");
            continue;
        }
        
        // Чтение тока из INA209
        ina209_reading_t reading;
        esp_err_t err = ina209_read(&reading);
        
        if (err == ESP_OK && reading.valid) {
            // Публикация телеметрии через node_framework
            pump_node_publish_telemetry_callback(NULL);
        } else {
            ESP_LOGW(TAG, "Failed to read INA209: %s", esp_err_to_name(err));
        }
    }
}

/**
 * @brief Задача публикации health-метрик насосов и INA209
 */
static void task_pump_health(void *pvParameters) {
    ESP_LOGI(TAG, "Pump health task started");

    // Добавляем задачу в watchdog
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add pump health task to watchdog: %s", esp_err_to_name(wdt_err));
    }

    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(PUMP_HEALTH_INTERVAL_MS);
    pump_driver_health_snapshot_t snapshot;

    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);

        // Сбрасываем watchdog
        node_watchdog_reset();

        if (!mqtt_manager_is_connected()) {
            continue;
        }

        esp_err_t err = pump_driver_get_health_snapshot(&snapshot);
        if (err != ESP_OK) {
            ESP_LOGD(TAG, "Health snapshot unavailable: %s", esp_err_to_name(err));
            continue;
        }

        cJSON *health = cJSON_CreateObject();
        if (!health) {
            continue;
        }

        cJSON_AddNumberToObject(health, "ts", (double)node_utils_get_timestamp_seconds());

        cJSON *channels = cJSON_CreateArray();
        if (!channels) {
            cJSON_Delete(health);
            continue;
        }

        for (size_t i = 0; i < snapshot.channel_count; i++) {
            const pump_driver_channel_health_t *ch = &snapshot.channels[i];
            cJSON *entry = cJSON_CreateObject();
            if (!entry) {
                continue;
            }

            cJSON_AddStringToObject(entry, "channel", ch->channel_name);
            cJSON_AddBoolToObject(entry, "running", ch->is_running);
            cJSON_AddBoolToObject(entry, "last_run_success", ch->last_run_success);
            cJSON_AddNumberToObject(entry, "last_run_ms", (double)ch->last_run_duration_ms);
            cJSON_AddNumberToObject(entry, "total_run_ms", (double)ch->total_run_time_ms);
            cJSON_AddNumberToObject(entry, "run_count", (double)ch->run_count);
            cJSON_AddNumberToObject(entry, "failure_count", (double)ch->failure_count);
            cJSON_AddNumberToObject(entry, "overcurrent_events", (double)ch->overcurrent_events);
            cJSON_AddNumberToObject(entry, "no_current_events", (double)ch->no_current_events);
            cJSON_AddNumberToObject(entry, "last_start_ts", (double)ch->last_start_timestamp_ms);
            cJSON_AddNumberToObject(entry, "last_stop_ts", (double)ch->last_stop_timestamp_ms);

            cJSON_AddItemToArray(channels, entry);
        }

        cJSON_AddItemToObject(health, "channels", channels);

        cJSON *ina = cJSON_CreateObject();
        if (ina) {
            cJSON_AddBoolToObject(ina, "enabled", snapshot.ina_status.enabled);
            cJSON_AddBoolToObject(ina, "reading_valid", snapshot.ina_status.last_read_valid);
            cJSON_AddBoolToObject(ina, "overcurrent", snapshot.ina_status.last_read_overcurrent);
            cJSON_AddBoolToObject(ina, "undercurrent", snapshot.ina_status.last_read_undercurrent);
            cJSON_AddNumberToObject(ina, "last_current_ma", snapshot.ina_status.last_current_ma);
            cJSON_AddItemToObject(health, "ina209", ina);
        }

        char *json_str = cJSON_PrintUnformatted(health);
        if (json_str) {
            mqtt_manager_publish_telemetry("pump_health", json_str);
            free(json_str);
        }

        cJSON_Delete(health);
    }
}

/**
 * @brief Обновление интервала опроса тока из NodeConfig
 * 
 * Ищет канал "pump_bus_current" в NodeConfig и обновляет s_current_poll_interval_ms
 */
void pump_node_update_current_poll_interval(void) {
    char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        ESP_LOGW(TAG, "Failed to load config for poll interval update");
        return;
    }
    
    cJSON *config = cJSON_Parse(config_json);
    if (config == NULL) {
        ESP_LOGW(TAG, "Failed to parse config for poll interval update");
        return;
    }
    
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels != NULL && cJSON_IsArray(channels)) {
        int channel_count = cJSON_GetArraySize(channels);
        for (int i = 0; i < channel_count; i++) {
            cJSON *ch = cJSON_GetArrayItem(channels, i);
            if (ch != NULL && cJSON_IsObject(ch)) {
                cJSON *name = cJSON_GetObjectItem(ch, "name");
                if (name != NULL && cJSON_IsString(name) && 
                    strcmp(name->valuestring, "pump_bus_current") == 0) {
                    cJSON *poll_interval = cJSON_GetObjectItem(ch, "poll_interval_ms");
                    if (poll_interval != NULL && cJSON_IsNumber(poll_interval)) {
                        uint32_t new_interval = (uint32_t)cJSON_GetNumberValue(poll_interval);
                        set_current_poll_interval(new_interval);
                        ESP_LOGI(TAG, "Updated current poll interval to %lu ms", new_interval);
                    }
                    break;
                }
            }
        }
    }
    
    cJSON_Delete(config);
}

/**
 * @brief Запуск FreeRTOS задач
 */
void pump_node_start_tasks(void) {
    // Обновляем интервал опроса из конфигурации
    pump_node_update_current_poll_interval();
    
    // Задача опроса тока насоса (если INA209 инициализирован)
    // Проверяем, что INA209 доступен через pump_driver
    xTaskCreate(task_current_poll, "current_poll_task", 3072, NULL, 4, NULL);

    // Health отчеты по насосам и INA209
    xTaskCreate(task_pump_health, "pump_health_task", 4096, NULL, 4, NULL);

    // Задача heartbeat
    xTaskCreate(task_heartbeat, "heartbeat_task", 3072, NULL, 3, NULL);
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}


