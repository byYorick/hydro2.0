/**
 * @file climate_node_tasks.c
 * @brief FreeRTOS задачи для climate_node
 * 
 * Реализует периодические задачи согласно FIRMWARE_STRUCTURE.md:
 * - task_sensors - опрос датчиков
 * - task_heartbeat - публикация heartbeat
 */

#include "climate_node_app.h"
#include "mqtt_client.h"
#include "config_storage.h"
#include "sht3x.h"
#include "ccs811.h"
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
#include <stdbool.h>

static const char *TAG = "climate_node_tasks";

// Периоды задач (в миллисекундах)
#define SENSOR_POLL_INTERVAL_MS    5000  // 5 секунд - опрос климатических датчиков
#define HEARTBEAT_INTERVAL_MS      15000 // 15 секунд - heartbeat

typedef enum {
    SENSOR_METRIC_TEMPERATURE = 0,
    SENSOR_METRIC_HUMIDITY,
    SENSOR_METRIC_CO2,
    SENSOR_METRIC_MAX,
} sensor_metric_t;

typedef struct {
    float last_value;
    bool value_valid;
    int64_t last_success_us;
    esp_err_t last_error;
} sensor_metric_state_t;

static struct {
    SemaphoreHandle_t mutex;
    sensor_metric_state_t metrics[SENSOR_METRIC_MAX];
} s_sensor_state = {0};

static void sensor_state_storage_init(void) {
    if (s_sensor_state.mutex == NULL) {
        s_sensor_state.mutex = xSemaphoreCreateMutex();
    }

    if (s_sensor_state.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create sensor state mutex");
        return;
    }

    for (size_t i = 0; i < SENSOR_METRIC_MAX; i++) {
        s_sensor_state.metrics[i].last_value = 0.0f;
        s_sensor_state.metrics[i].value_valid = false;
        s_sensor_state.metrics[i].last_success_us = 0;
        s_sensor_state.metrics[i].last_error = ESP_ERR_INVALID_STATE;
    }
}

static void sensor_state_update_success(sensor_metric_t metric, float value) {
    if (metric >= SENSOR_METRIC_MAX || s_sensor_state.mutex == NULL) {
        return;
    }

    if (xSemaphoreTake(s_sensor_state.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        sensor_metric_state_t *state = &s_sensor_state.metrics[metric];
        state->last_value = value;
        state->value_valid = true;
        state->last_success_us = esp_timer_get_time();
        state->last_error = ESP_OK;
        xSemaphoreGive(s_sensor_state.mutex);
    }
}

static void sensor_state_update_error(sensor_metric_t metric, esp_err_t err) {
    if (metric >= SENSOR_METRIC_MAX || s_sensor_state.mutex == NULL) {
        return;
    }

    if (xSemaphoreTake(s_sensor_state.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        sensor_metric_state_t *state = &s_sensor_state.metrics[metric];
        state->value_valid = false;
        state->last_error = err;
        xSemaphoreGive(s_sensor_state.mutex);
    }
}

static sensor_metric_state_t sensor_state_get(sensor_metric_t metric) {
    sensor_metric_state_t snapshot = {0};
    if (metric >= SENSOR_METRIC_MAX || s_sensor_state.mutex == NULL) {
        return snapshot;
    }

    if (xSemaphoreTake(s_sensor_state.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        snapshot = s_sensor_state.metrics[metric];
        xSemaphoreGive(s_sensor_state.mutex);
    }
    return snapshot;
}

static cJSON *sensor_state_to_json(const sensor_metric_state_t *state) {
    if (state == NULL) {
        return NULL;
    }

    cJSON *obj = cJSON_CreateObject();
    if (obj == NULL) {
        return NULL;
    }

    cJSON_AddBoolToObject(obj, "value_valid", state->value_valid);
    if (state->value_valid) {
        cJSON_AddNumberToObject(obj, "last_value", state->last_value);
    }

    if (state->last_success_us > 0) {
        cJSON_AddNumberToObject(obj, "last_success_ts", (double)state->last_success_us / 1000000.0);
    } else {
        cJSON_AddNullToObject(obj, "last_success_ts");
    }

    cJSON_AddNumberToObject(obj, "last_error", state->last_error);
    cJSON_AddStringToObject(obj, "last_error_name", esp_err_to_name(state->last_error));
    return obj;
}

static cJSON *sensor_status_snapshot_json(void) {
    cJSON *status = cJSON_CreateObject();
    if (status == NULL) {
        return NULL;
    }

    sensor_metric_state_t temp = sensor_state_get(SENSOR_METRIC_TEMPERATURE);
    sensor_metric_state_t hum = sensor_state_get(SENSOR_METRIC_HUMIDITY);
    sensor_metric_state_t co2 = sensor_state_get(SENSOR_METRIC_CO2);

    cJSON *temp_json = sensor_state_to_json(&temp);
    cJSON *hum_json = sensor_state_to_json(&hum);
    cJSON *co2_json = sensor_state_to_json(&co2);

    if (temp_json) {
        cJSON_AddItemToObject(status, "temperature", temp_json);
    }
    if (hum_json) {
        cJSON_AddItemToObject(status, "humidity", hum_json);
    }
    if (co2_json) {
        cJSON_AddItemToObject(status, "co2", co2_json);
    }

    return status;
}

static const char *climate_node_get_node_id(void) {
    static char node_id[CONFIG_STORAGE_MAX_STRING_LEN];
    static bool loaded = false;

    if (!loaded) {
        if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
            strncpy(node_id, "climate-node", sizeof(node_id) - 1);
            node_id[sizeof(node_id) - 1] = '\0';
        }
        loaded = true;
    }
    return node_id;
}

static void publish_metric(const char *channel, const char *metric_type, sensor_metric_t metric,
                           bool success, float value, esp_err_t err) {
    if (success) {
        sensor_state_update_success(metric, value);
    } else {
        sensor_state_update_error(metric, err);
    }

    if (!mqtt_client_is_connected()) {
        return;
    }

    sensor_metric_state_t snapshot = sensor_state_get(metric);
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry == NULL) {
        return;
    }

    cJSON_AddStringToObject(telemetry, "node_id", climate_node_get_node_id());
    cJSON_AddStringToObject(telemetry, "channel", channel);
    cJSON_AddStringToObject(telemetry, "metric_type", metric_type);
    if (success) {
        cJSON_AddNumberToObject(telemetry, "value", value);
    } else {
        cJSON_AddNullToObject(telemetry, "value");
        cJSON_AddStringToObject(telemetry, "error", esp_err_to_name(err));
    }
    cJSON_AddNumberToObject(telemetry, "timestamp", (double)esp_timer_get_time() / 1000000.0);

    cJSON *status = sensor_state_to_json(&snapshot);
    if (status != NULL) {
        cJSON_AddItemToObject(telemetry, "sensor_status", status);
    }

    char *json_str = cJSON_PrintUnformatted(telemetry);
    if (json_str) {
        mqtt_client_publish_telemetry(channel, json_str);
        free(json_str);
    }
    cJSON_Delete(telemetry);
}

static void publish_heartbeat(void) {
    if (!mqtt_client_is_connected()) {
        return;
    }

    wifi_ap_record_t ap_info;
    int8_t rssi = -100;
    if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        rssi = ap_info.rssi;
    }

    cJSON *heartbeat = cJSON_CreateObject();
    if (heartbeat == NULL) {
        return;
    }

    cJSON_AddNumberToObject(heartbeat, "uptime", (double)(esp_timer_get_time() / 1000));
    cJSON_AddNumberToObject(heartbeat, "free_heap", (double)esp_get_free_heap_size());
    cJSON_AddNumberToObject(heartbeat, "rssi", rssi);

    cJSON *status = sensor_status_snapshot_json();
    if (status != NULL) {
        cJSON_AddItemToObject(heartbeat, "sensor_status", status);
    }

    char *json_str = cJSON_PrintUnformatted(heartbeat);
    if (json_str) {
        mqtt_client_publish_heartbeat(json_str);
        free(json_str);
    }
    cJSON_Delete(heartbeat);
}

/**
 * @brief Задача опроса сенсоров
 */
static void task_sensors(void *pvParameters) {
    ESP_LOGI(TAG, "Sensor task started");

    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);

    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);

        sht3x_reading_t sht_reading = {0};
        esp_err_t sht_err = sht3x_read(&sht_reading);
        if (sht_err == ESP_OK && sht_reading.valid) {
            publish_metric("temperature", "TEMPERATURE", SENSOR_METRIC_TEMPERATURE, true, sht_reading.temperature, ESP_OK);
            vTaskDelay(pdMS_TO_TICKS(50));
            publish_metric("humidity", "HUMIDITY", SENSOR_METRIC_HUMIDITY, true, sht_reading.humidity, ESP_OK);
        } else {
            esp_err_t report_err = (sht_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : sht_err;
            ESP_LOGW(TAG, "Failed to read SHT3x: %s", esp_err_to_name(report_err));
            publish_metric("temperature", "TEMPERATURE", SENSOR_METRIC_TEMPERATURE, false, 0.0f, report_err);
            vTaskDelay(pdMS_TO_TICKS(50));
            publish_metric("humidity", "HUMIDITY", SENSOR_METRIC_HUMIDITY, false, 0.0f, report_err);
        }

        ccs811_reading_t ccs_reading = {0};
        esp_err_t ccs_err = ccs811_read(&ccs_reading);
        if (ccs_err == ESP_OK && ccs_reading.valid) {
            publish_metric("co2", "CO2", SENSOR_METRIC_CO2, true, (float)ccs_reading.co2_ppm, ESP_OK);
        } else {
            esp_err_t report_err = (ccs_err == ESP_OK) ? ESP_ERR_INVALID_RESPONSE : ccs_err;
            ESP_LOGW(TAG, "Failed to read CCS811: %s", esp_err_to_name(report_err));
            publish_metric("co2", "CO2", SENSOR_METRIC_CO2, false, 0.0f, report_err);
        }
    }
}

/**
 * @brief Задача публикации heartbeat
 */
static void task_heartbeat(void *pvParameters) {
    ESP_LOGI(TAG, "Heartbeat task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(HEARTBEAT_INTERVAL_MS);
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        if (!mqtt_client_is_connected()) {
            continue;
        }

        publish_heartbeat();
    }
}

/**
 * @brief Запуск FreeRTOS задач
 */
void climate_node_start_tasks(void) {
    sensor_state_storage_init();

    // Задача опроса сенсоров
    xTaskCreate(task_sensors, "sensor_task", 4096, NULL, 5, NULL);

    // Задача heartbeat
    xTaskCreate(task_heartbeat, "heartbeat_task", 3072, NULL, 3, NULL);
    
    ESP_LOGI(TAG, "FreeRTOS tasks started");
}

