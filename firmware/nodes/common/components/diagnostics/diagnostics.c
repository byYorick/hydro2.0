/**
 * @file diagnostics.c
 * @brief Реализация компонента диагностики и сбора метрик
 */

#include "diagnostics.h"
#include "node_state_manager.h"
#include "node_framework.h"
#include "node_watchdog.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "memory_pool.h"
#include "i2c_cache.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "diagnostics";

// Константы
#define DIAGNOSTICS_DEFAULT_PUBLISH_INTERVAL_MS 60000  // 60 секунд
#define DIAGNOSTICS_MAX_SENSORS 8
#define DIAGNOSTICS_MAX_TASKS 16

// Структура для хранения метрик сенсоров
typedef struct {
    char sensor_name[16];
    uint32_t read_count;
    uint32_t error_count;
    uint32_t last_read_time_ms;
    bool initialized;
} sensor_metrics_entry_t;

// Структура для хранения метрик MQTT
typedef struct {
    uint32_t messages_sent;
    uint32_t messages_received;
    uint32_t publish_errors;
    uint32_t subscribe_errors;
    uint32_t reconnect_count;
    bool connected;
} mqtt_metrics_entry_t;

// Состояние компонента
static struct {
    bool initialized;
    diagnostics_config_t config;
    SemaphoreHandle_t mutex;
    
    // Метрики сенсоров
    sensor_metrics_entry_t sensors[DIAGNOSTICS_MAX_SENSORS];
    size_t sensor_count;
    
    // Метрики MQTT
    mqtt_metrics_entry_t mqtt;
    
    // Время последней публикации
    int64_t last_publish_time_us;
} s_diagnostics = {0};

/**
 * @brief Внутренняя функция для получения метрик памяти
 */
static void diagnostics_get_memory_metrics(diagnostics_memory_metrics_t *metrics) {
    if (metrics == NULL) {
        return;
    }
    
    memset(metrics, 0, sizeof(*metrics));
    
    metrics->free_heap = esp_get_free_heap_size();
    metrics->min_free_heap = esp_get_minimum_free_heap_size();
    metrics->largest_free_block = heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT);
    
    // Метрики из memory_pool, если доступны
    if (memory_pool_is_initialized()) {
        memory_pool_metrics_t mem_pool_metrics;
        if (memory_pool_get_metrics(&mem_pool_metrics) == ESP_OK) {
            metrics->heap_allocations = mem_pool_metrics.json_objects_allocated + mem_pool_metrics.json_strings_allocated;
            metrics->heap_frees = mem_pool_metrics.json_objects_freed + mem_pool_metrics.json_strings_freed;
            if (mem_pool_metrics.min_heap_free < metrics->min_free_heap) {
                metrics->min_free_heap = mem_pool_metrics.min_heap_free;
            }
        }
    }
}

/**
 * @brief Внутренняя функция для получения метрик ошибок
 */
static void diagnostics_get_error_metrics(diagnostics_error_metrics_t *metrics) {
    if (metrics == NULL) {
        return;
    }
    
    memset(metrics, 0, sizeof(*metrics));
    
    // Получаем метрики из node_state_manager
    // Примечание: node_state_manager не предоставляет разбивку по уровням,
    // поэтому используем общий счетчик
    metrics->total_count = node_state_manager_get_error_count(NULL);
    
    // TODO: Добавить разбивку по уровням ошибок в node_state_manager
    // Пока используем общий счетчик для всех типов
    metrics->warning_count = 0;
    metrics->error_count = metrics->total_count;
    metrics->critical_count = 0;
}

/**
 * @brief Внутренняя функция для получения метрик задач
 */
static void diagnostics_get_task_metrics(diagnostics_task_metrics_t *tasks, uint32_t *task_count) {
    if (tasks == NULL || task_count == NULL) {
        return;
    }
    
    *task_count = 0;
    
    // Получаем список задач через FreeRTOS
    UBaseType_t num_tasks = uxTaskGetNumberOfTasks();
    if (num_tasks > DIAGNOSTICS_MAX_TASKS) {
        num_tasks = DIAGNOSTICS_MAX_TASKS;
    }
    
    TaskStatus_t *task_status_array = (TaskStatus_t*)malloc(sizeof(TaskStatus_t) * num_tasks);
    if (task_status_array == NULL) {
        ESP_LOGE(TAG, "Failed to allocate memory for task status");
        return;
    }
    
    // В ESP-IDF 5.5 uxTaskGetSystemState требует configUSE_TRACE_FACILITY
    // Используем упрощенный подход - получаем информацию только о текущей задаче
    // и основных задачах через vTaskList или другие методы
    // Пока отключаем сбор метрик задач, так как требует дополнительной конфигурации
    // TODO: Включить configUSE_TRACE_FACILITY в sdkconfig для полной поддержки
    
    // Временно возвращаем пустой список задач
    *task_count = 0;
    
    free(task_status_array);
    return;
    
    // Код ниже будет использован после включения configUSE_TRACE_FACILITY
    /*
    UBaseType_t actual_count = uxTaskGetSystemState(task_status_array, num_tasks, NULL);
    
    for (UBaseType_t i = 0; i < actual_count && *task_count < DIAGNOSTICS_MAX_TASKS; i++) {
        diagnostics_task_metrics_t *task = &tasks[*task_count];
        
        strncpy(task->task_name, task_status_array[i].pcTaskName, sizeof(task->task_name) - 1);
        task->task_name[sizeof(task->task_name) - 1] = '\0';
        task->stack_high_water_mark = task_status_array[i].usStackHighWaterMark;
        task->runtime_ms = task_status_array[i].ulRunTimeCounter / (configTICK_RATE_HZ / 1000);
        
        // Получаем core_id через xTaskGetCoreID (ESP-IDF 5.5)
        TaskHandle_t task_handle = xTaskGetHandle(task_status_array[i].pcTaskName);
        if (task_handle != NULL) {
            BaseType_t core_id = xTaskGetCoreID(task_handle);
            task->core_id = (core_id >= 0 && core_id <= 1) ? (uint32_t)core_id : 0;
        } else {
            task->core_id = 0;  // По умолчанию core 0
        }
        
        (*task_count)++;
    }
    */
    
    free(task_status_array);
}

esp_err_t diagnostics_init(const diagnostics_config_t *config) {
    if (s_diagnostics.initialized) {
        ESP_LOGW(TAG, "Diagnostics already initialized");
        return ESP_OK;
    }
    
    ESP_LOGI(TAG, "Initializing diagnostics component...");
    
    // Установка конфигурации
    if (config != NULL) {
        memcpy(&s_diagnostics.config, config, sizeof(diagnostics_config_t));
    } else {
        s_diagnostics.config.publish_interval_ms = DIAGNOSTICS_DEFAULT_PUBLISH_INTERVAL_MS;
        s_diagnostics.config.enable_auto_publish = true;
        s_diagnostics.config.enable_metrics = true;
    }
    
    // Создание mutex
    s_diagnostics.mutex = xSemaphoreCreateMutex();
    if (s_diagnostics.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }
    
    // Инициализация метрик
    memset(&s_diagnostics.sensors, 0, sizeof(s_diagnostics.sensors));
    s_diagnostics.sensor_count = 0;
    memset(&s_diagnostics.mqtt, 0, sizeof(s_diagnostics.mqtt));
    s_diagnostics.last_publish_time_us = 0;
    
    s_diagnostics.initialized = true;
    
    ESP_LOGI(TAG, "Diagnostics component initialized (publish_interval: %u ms, auto_publish: %s)",
             s_diagnostics.config.publish_interval_ms,
             s_diagnostics.config.enable_auto_publish ? "enabled" : "disabled");
    
    return ESP_OK;
}

esp_err_t diagnostics_deinit(void) {
    if (!s_diagnostics.initialized) {
        return ESP_OK;
    }
    
    if (s_diagnostics.mutex) {
        vSemaphoreDelete(s_diagnostics.mutex);
        s_diagnostics.mutex = NULL;
    }
    
    memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    
    ESP_LOGI(TAG, "Diagnostics component deinitialized");
    return ESP_OK;
}

esp_err_t diagnostics_get_snapshot(diagnostics_snapshot_t *snapshot) {
    if (!s_diagnostics.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (snapshot == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (xSemaphoreTake(s_diagnostics.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    
    memset(snapshot, 0, sizeof(*snapshot));
    
    // Системные метрики
    snapshot->uptime_seconds = esp_timer_get_time() / 1000000;
    diagnostics_get_memory_metrics(&snapshot->memory);
    
    // Метрики ошибок
    diagnostics_get_error_metrics(&snapshot->errors);
    
    // Метрики MQTT
    snapshot->mqtt.messages_sent = s_diagnostics.mqtt.messages_sent;
    snapshot->mqtt.messages_received = s_diagnostics.mqtt.messages_received;
    snapshot->mqtt.publish_errors = s_diagnostics.mqtt.publish_errors;
    snapshot->mqtt.subscribe_errors = s_diagnostics.mqtt.subscribe_errors;
    snapshot->mqtt.connected = mqtt_manager_is_connected();
    
    // Получаем reconnect_count из mqtt_manager
    // mqtt_manager.h уже включен в начале файла, поэтому функция доступна
    snapshot->mqtt.reconnect_count = mqtt_manager_get_reconnect_count();
    
    // Метрики задач
    diagnostics_get_task_metrics(snapshot->tasks, &snapshot->task_count);
    
    // Метрики сенсоров
    snapshot->sensor_count = 0;  // Инициализация счетчика
    for (size_t i = 0; i < s_diagnostics.sensor_count && snapshot->sensor_count < DIAGNOSTICS_MAX_SENSORS; i++) {
        diagnostics_sensor_metrics_t *sensor = &snapshot->sensors[snapshot->sensor_count];
        strncpy(sensor->sensor_name, s_diagnostics.sensors[i].sensor_name, sizeof(sensor->sensor_name) - 1);
        sensor->sensor_name[sizeof(sensor->sensor_name) - 1] = '\0';
        sensor->read_count = s_diagnostics.sensors[i].read_count;
        sensor->error_count = s_diagnostics.sensors[i].error_count;
        sensor->last_read_time_ms = s_diagnostics.sensors[i].last_read_time_ms;
        sensor->initialized = s_diagnostics.sensors[i].initialized;
        snapshot->sensor_count++;
    }
    
    // Дополнительные метрики
    wifi_ap_record_t ap_info;
    snapshot->wifi_rssi = -100;
    snapshot->wifi_connected = wifi_manager_is_connected();
    if (snapshot->wifi_connected && esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        snapshot->wifi_rssi = ap_info.rssi;
    }
    
    snapshot->safe_mode = (node_framework_get_state() == NODE_STATE_SAFE_MODE);
    
    xSemaphoreGive(s_diagnostics.mutex);
    
    return ESP_OK;
}

esp_err_t diagnostics_publish(void) {
    if (!s_diagnostics.initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (!mqtt_manager_is_connected()) {
        return ESP_ERR_INVALID_STATE;
    }
    
    diagnostics_snapshot_t snapshot;
    esp_err_t err = diagnostics_get_snapshot(&snapshot);
    if (err != ESP_OK) {
        return err;
    }
    
    // Формирование JSON
    cJSON *diagnostics = cJSON_CreateObject();
    if (diagnostics == NULL) {
        return ESP_ERR_NO_MEM;
    }
    
    // Системные метрики
    cJSON *system = cJSON_CreateObject();
    if (system == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddNumberToObject(system, "uptime_seconds", (double)snapshot.uptime_seconds);
    cJSON_AddNumberToObject(system, "free_heap", (double)snapshot.memory.free_heap);
    cJSON_AddNumberToObject(system, "min_free_heap", (double)snapshot.memory.min_free_heap);
    cJSON_AddNumberToObject(system, "largest_free_block", (double)snapshot.memory.largest_free_block);
    cJSON_AddItemToObject(diagnostics, "system", system);
    
    // Метрики ошибок
    cJSON *errors = cJSON_CreateObject();
    if (errors == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddNumberToObject(errors, "warning_count", (double)snapshot.errors.warning_count);
    cJSON_AddNumberToObject(errors, "error_count", (double)snapshot.errors.error_count);
    cJSON_AddNumberToObject(errors, "critical_count", (double)snapshot.errors.critical_count);
    cJSON_AddNumberToObject(errors, "total_count", (double)snapshot.errors.total_count);
    cJSON_AddItemToObject(diagnostics, "errors", errors);
    
    // Метрики MQTT
    cJSON *mqtt = cJSON_CreateObject();
    if (mqtt == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddBoolToObject(mqtt, "connected", snapshot.mqtt.connected);
    cJSON_AddNumberToObject(mqtt, "messages_sent", (double)snapshot.mqtt.messages_sent);
    cJSON_AddNumberToObject(mqtt, "messages_received", (double)snapshot.mqtt.messages_received);
    cJSON_AddNumberToObject(mqtt, "publish_errors", (double)snapshot.mqtt.publish_errors);
    cJSON_AddNumberToObject(mqtt, "reconnect_count", (double)snapshot.mqtt.reconnect_count);
    cJSON_AddItemToObject(diagnostics, "mqtt", mqtt);
    
    // Метрики Wi-Fi
    cJSON *wifi = cJSON_CreateObject();
    if (wifi == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    cJSON_AddBoolToObject(wifi, "connected", snapshot.wifi_connected);
    cJSON_AddNumberToObject(wifi, "rssi", snapshot.wifi_rssi);
    cJSON_AddItemToObject(diagnostics, "wifi", wifi);
    
    // Метрики состояния
    cJSON_AddBoolToObject(diagnostics, "safe_mode", snapshot.safe_mode);
    
    // Метрики задач
    cJSON *tasks_array = cJSON_CreateArray();
    if (tasks_array == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    for (uint32_t i = 0; i < snapshot.task_count; i++) {
        cJSON *task = cJSON_CreateObject();
        if (task == NULL) {
            cJSON_Delete(diagnostics);
            return ESP_ERR_NO_MEM;
        }
        cJSON_AddStringToObject(task, "name", snapshot.tasks[i].task_name);
        cJSON_AddNumberToObject(task, "stack_high_water_mark", (double)snapshot.tasks[i].stack_high_water_mark);
        cJSON_AddNumberToObject(task, "runtime_ms", (double)snapshot.tasks[i].runtime_ms);
        cJSON_AddNumberToObject(task, "core_id", (double)snapshot.tasks[i].core_id);
        cJSON_AddItemToArray(tasks_array, task);
    }
    cJSON_AddItemToObject(diagnostics, "tasks", tasks_array);
    
    // Метрики сенсоров
    cJSON *sensors_array = cJSON_CreateArray();
    if (sensors_array == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    for (uint32_t i = 0; i < snapshot.sensor_count; i++) {
        cJSON *sensor = cJSON_CreateObject();
        if (sensor == NULL) {
            cJSON_Delete(diagnostics);
            return ESP_ERR_NO_MEM;
        }
        cJSON_AddStringToObject(sensor, "name", snapshot.sensors[i].sensor_name);
        cJSON_AddNumberToObject(sensor, "read_count", (double)snapshot.sensors[i].read_count);
        cJSON_AddNumberToObject(sensor, "error_count", (double)snapshot.sensors[i].error_count);
        cJSON_AddNumberToObject(sensor, "last_read_time_ms", (double)snapshot.sensors[i].last_read_time_ms);
        cJSON_AddBoolToObject(sensor, "initialized", snapshot.sensors[i].initialized);
        cJSON_AddItemToArray(sensors_array, sensor);
    }
    cJSON_AddItemToObject(diagnostics, "sensors", sensors_array);
    
    // Метрики кэша I2C (если доступны)
    if (i2c_cache_is_initialized()) {
        i2c_cache_metrics_t cache_metrics;
        if (i2c_cache_get_metrics(&cache_metrics) == ESP_OK) {
            cJSON *cache = cJSON_CreateObject();
            if (cache == NULL) {
                cJSON_Delete(diagnostics);
                return ESP_ERR_NO_MEM;
            }
            cJSON_AddNumberToObject(cache, "hits", (double)cache_metrics.cache_hits);
            cJSON_AddNumberToObject(cache, "misses", (double)cache_metrics.cache_misses);
            cJSON_AddNumberToObject(cache, "evictions", (double)cache_metrics.cache_evictions);
            cJSON_AddNumberToObject(cache, "current_entries", (double)cache_metrics.current_entries);
            cJSON_AddItemToObject(diagnostics, "i2c_cache", cache);
        }
    }
    
    // Добавляем timestamp
    cJSON_AddNumberToObject(diagnostics, "ts", (double)(esp_timer_get_time() / 1000000));
    
    // Публикация через MQTT
    char *json_str = cJSON_PrintUnformatted(diagnostics);
    if (json_str == NULL) {
        cJSON_Delete(diagnostics);
        return ESP_ERR_NO_MEM;
    }
    
    // Публикуем в топик diagnostics
    // Формат: hydro/{gh}/{zone}/{node}/diagnostics
    esp_err_t publish_err = mqtt_manager_publish_diagnostics(json_str);
    if (publish_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish diagnostics: %s", esp_err_to_name(publish_err));
    }
    
    free(json_str);
    cJSON_Delete(diagnostics);
    
    s_diagnostics.last_publish_time_us = esp_timer_get_time();
    
    return ESP_OK;
}

void diagnostics_update_mqtt_metrics(bool message_sent, bool message_received, bool error) {
    if (!s_diagnostics.initialized) {
        return;
    }
    
    if (xSemaphoreTake(s_diagnostics.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return;
    }
    
    if (message_sent) {
        s_diagnostics.mqtt.messages_sent++;
    }
    if (message_received) {
        s_diagnostics.mqtt.messages_received++;
    }
    if (error) {
        s_diagnostics.mqtt.publish_errors++;
    }
    
    s_diagnostics.mqtt.connected = mqtt_manager_is_connected();
    
    xSemaphoreGive(s_diagnostics.mutex);
}

void diagnostics_update_sensor_metrics(const char *sensor_name, bool read_success) {
    if (!s_diagnostics.initialized || sensor_name == NULL) {
        return;
    }
    
    if (xSemaphoreTake(s_diagnostics.mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return;
    }
    
    // Поиск существующего сенсора
    size_t index = 0;
    bool found = false;
    for (size_t i = 0; i < s_diagnostics.sensor_count; i++) {
        if (strcmp(s_diagnostics.sensors[i].sensor_name, sensor_name) == 0) {
            index = i;
            found = true;
            break;
        }
    }
    
    // Если не найден, создаем новую запись
    if (!found) {
        if (s_diagnostics.sensor_count >= DIAGNOSTICS_MAX_SENSORS) {
            xSemaphoreGive(s_diagnostics.mutex);
            return;
        }
        index = s_diagnostics.sensor_count;
        strncpy(s_diagnostics.sensors[index].sensor_name, sensor_name, sizeof(s_diagnostics.sensors[index].sensor_name) - 1);
        s_diagnostics.sensors[index].sensor_name[sizeof(s_diagnostics.sensors[index].sensor_name) - 1] = '\0';
        s_diagnostics.sensors[index].read_count = 0;
        s_diagnostics.sensors[index].error_count = 0;
        s_diagnostics.sensors[index].initialized = true;
        s_diagnostics.sensor_count++;
    }
    
    // Обновление метрик
    if (read_success) {
        s_diagnostics.sensors[index].read_count++;
    } else {
        s_diagnostics.sensors[index].error_count++;
    }
    s_diagnostics.sensors[index].last_read_time_ms = (uint32_t)(esp_timer_get_time() / 1000);
    
    xSemaphoreGive(s_diagnostics.mutex);
}

bool diagnostics_is_initialized(void) {
    return s_diagnostics.initialized;
}

