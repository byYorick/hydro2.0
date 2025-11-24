/**
 * @file node_telemetry_engine.c
 * @brief Реализация движка публикации телеметрии
 */

#include "node_telemetry_engine.h"
#include "mqtt_manager.h"
#include "config_storage.h"
#include "memory_pool.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "node_telemetry_engine";

// Максимальный размер батча телеметрии
#define TELEMETRY_BATCH_MAX_SIZE 10
#define TELEMETRY_BATCH_INTERVAL_MS 5000  // 5 секунд

// Структура элемента телеметрии в батче
typedef struct {
    char channel[64];
    char metric_type[32];
    float value;
    int32_t raw;
    bool stub;
    bool stable;
    uint64_t ts;
} telemetry_item_t;

// Структура батча
typedef struct {
    telemetry_item_t items[TELEMETRY_BATCH_MAX_SIZE];
    size_t count;
    uint64_t last_flush_time;
} telemetry_batch_t;

static struct {
    telemetry_batch_t batch;
    SemaphoreHandle_t mutex;
    TaskHandle_t flush_task;
    bool initialized;
    uint32_t batch_interval_ms;
    uint32_t batch_size;
} s_telemetry_engine = {
    .batch_interval_ms = TELEMETRY_BATCH_INTERVAL_MS,
    .batch_size = TELEMETRY_BATCH_MAX_SIZE
};

// Маппинг типов метрик в строки
static const char *metric_type_to_string(metric_type_t type) {
    switch (type) {
        case METRIC_TYPE_PH: return "PH";
        case METRIC_TYPE_EC: return "EC";
        case METRIC_TYPE_TEMPERATURE: return "TEMPERATURE";
        case METRIC_TYPE_HUMIDITY: return "HUMIDITY";
        case METRIC_TYPE_CURRENT: return "CURRENT";
        case METRIC_TYPE_PUMP_STATE: return "PUMP_STATE";
        default: return "UNKNOWN";
    }
}

// Задача для периодической отправки батча
static void task_telemetry_flush(void *pvParameters) {
    ESP_LOGI(TAG, "Telemetry flush task started");
    
    TickType_t last_wake_time = xTaskGetTickCount();
    const TickType_t interval = pdMS_TO_TICKS(s_telemetry_engine.batch_interval_ms);
    
    while (1) {
        vTaskDelayUntil(&last_wake_time, interval);
        
        // Принудительная отправка батча по таймеру
        node_telemetry_flush();
    }
}

static esp_err_t flush_batch_internal(void) {
    if (s_telemetry_engine.batch.count == 0) {
        return ESP_OK;
    }

    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry batch");
        return ESP_ERR_INVALID_STATE;
    }

    // Получаем node_id из конфига
    char node_id[64];
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        ESP_LOGW(TAG, "Failed to get node_id, skipping telemetry");
        return ESP_ERR_INVALID_STATE;
    }

    // Публикуем каждое сообщение из батча
    for (size_t i = 0; i < s_telemetry_engine.batch.count; i++) {
        telemetry_item_t *item = &s_telemetry_engine.batch.items[i];
        
        cJSON *telemetry = cJSON_CreateObject();
        if (telemetry) {
            cJSON_AddStringToObject(telemetry, "node_id", node_id);
            cJSON_AddStringToObject(telemetry, "channel", item->channel);
            cJSON_AddStringToObject(telemetry, "metric_type", item->metric_type);
            cJSON_AddNumberToObject(telemetry, "value", item->value);
            cJSON_AddNumberToObject(telemetry, "ts", (double)item->ts);
            
            if (item->raw != 0) {
                cJSON_AddNumberToObject(telemetry, "raw", item->raw);
            }
            if (item->stub) {
                cJSON_AddBoolToObject(telemetry, "stub", item->stub);
            }
            if (!item->stable) {
                cJSON_AddBoolToObject(telemetry, "stable", item->stable);
            }
            
            char *json_str = cJSON_PrintUnformatted(telemetry);
            if (json_str) {
                // Используем пул памяти для оптимизации (если доступен)
                // Примечание: cJSON_PrintUnformatted уже выделил память через malloc,
                // поэтому мы не можем напрямую использовать пул. Но можем отслеживать метрики.
                if (memory_pool_is_initialized()) {
                    // Обновляем метрики использования памяти
                    memory_pool_free_json_string(NULL);  // Просто обновляет метрики
                }
                
                mqtt_manager_publish_telemetry(item->channel, json_str);
                free(json_str);
            }
            cJSON_Delete(telemetry);
        }
    }

    // Очищаем батч
    s_telemetry_engine.batch.count = 0;
    s_telemetry_engine.batch.last_flush_time = esp_timer_get_time() / 1000;

    return ESP_OK;
}

static esp_err_t add_to_batch(
    const char *channel,
    const char *metric_type_str,
    float value,
    int32_t raw,
    bool stub,
    bool stable
) {
    if (channel == NULL || metric_type_str == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_telemetry_engine.mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_telemetry_engine.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Проверяем, нужно ли отправить батч
        bool should_flush = false;
        
        if (s_telemetry_engine.batch.count >= s_telemetry_engine.batch_size) {
            should_flush = true;
        } else {
            uint64_t current_time_ms = esp_timer_get_time() / 1000;
            uint64_t elapsed = current_time_ms - s_telemetry_engine.batch.last_flush_time;
            if (elapsed >= s_telemetry_engine.batch_interval_ms) {
                should_flush = true;
            }
        }

        if (should_flush && s_telemetry_engine.batch.count > 0) {
            xSemaphoreGive(s_telemetry_engine.mutex);
            flush_batch_internal();
            xSemaphoreTake(s_telemetry_engine.mutex, pdMS_TO_TICKS(1000));
        }

        // Добавляем в батч
        if (s_telemetry_engine.batch.count < TELEMETRY_BATCH_MAX_SIZE) {
            telemetry_item_t *item = &s_telemetry_engine.batch.items[s_telemetry_engine.batch.count];
            strncpy(item->channel, channel, 63);
            item->channel[63] = '\0';
            strncpy(item->metric_type, metric_type_str, 31);
            item->metric_type[31] = '\0';
            item->value = value;
            item->raw = raw;
            item->stub = stub;
            item->stable = stable;
            item->ts = esp_timer_get_time() / 1000000;
            s_telemetry_engine.batch.count++;
        } else {
            ESP_LOGW(TAG, "Telemetry batch is full, dropping message");
        }

        xSemaphoreGive(s_telemetry_engine.mutex);
        return ESP_OK;
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t node_telemetry_publish_sensor(
    const char *channel,
    metric_type_t metric_type,
    float value,
    const char *unit,
    int32_t raw,
    bool stub,
    bool stable
) {
    const char *metric_type_str = metric_type_to_string(metric_type);
    return add_to_batch(channel, metric_type_str, value, raw, stub, stable);
}

esp_err_t node_telemetry_publish_actuator(
    const char *channel,
    metric_type_t metric_type,
    const char *state,
    float value
) {
    // Для актуаторов используем значение как состояние
    const char *metric_type_str = metric_type_to_string(metric_type);
    return add_to_batch(channel, metric_type_str, value, 0, false, true);
}

esp_err_t node_telemetry_publish_custom(
    const char *channel,
    const char *metric_type_str,
    float value,
    int32_t raw,
    bool stub,
    bool stable
) {
    return add_to_batch(channel, metric_type_str, value, raw, stub, stable);
}

esp_err_t node_telemetry_flush(void) {
    if (s_telemetry_engine.mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_telemetry_engine.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        esp_err_t err = flush_batch_internal();
        xSemaphoreGive(s_telemetry_engine.mutex);
        return err;
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t node_telemetry_set_batch_interval(uint32_t interval_ms) {
    if (interval_ms == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    s_telemetry_engine.batch_interval_ms = interval_ms;
    ESP_LOGI(TAG, "Telemetry batch interval set to %lu ms", (unsigned long)interval_ms);
    return ESP_OK;
}

esp_err_t node_telemetry_set_batch_size(uint32_t batch_size) {
    if (batch_size == 0 || batch_size > TELEMETRY_BATCH_MAX_SIZE) {
        return ESP_ERR_INVALID_ARG;
    }

    s_telemetry_engine.batch_size = batch_size;
    ESP_LOGI(TAG, "Telemetry batch size set to %lu", (unsigned long)batch_size);
    return ESP_OK;
}

// Объявление функции для использования из node_framework.c
esp_err_t node_telemetry_engine_init(void);
esp_err_t node_telemetry_engine_deinit(void);

// Реализация
esp_err_t node_telemetry_engine_init(void) {
    if (s_telemetry_engine.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    s_telemetry_engine.mutex = xSemaphoreCreateMutex();
    if (s_telemetry_engine.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }

    memset(&s_telemetry_engine.batch, 0, sizeof(s_telemetry_engine.batch));
    s_telemetry_engine.batch.last_flush_time = esp_timer_get_time() / 1000;

    // Создаем задачу для периодической отправки батча
    BaseType_t ret = xTaskCreate(
        task_telemetry_flush,
        "telemetry_flush",
        2048,
        NULL,
        3,  // Низкий приоритет
        &s_telemetry_engine.flush_task
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create telemetry flush task");
        vSemaphoreDelete(s_telemetry_engine.mutex);
        s_telemetry_engine.mutex = NULL;
        return ESP_ERR_NO_MEM;
    }

    s_telemetry_engine.initialized = true;
    ESP_LOGI(TAG, "Telemetry engine initialized");
    return ESP_OK;
}

// Деинициализация (вызывается из node_framework_deinit)
esp_err_t node_telemetry_engine_deinit(void) {
    if (!s_telemetry_engine.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    // Отправляем оставшиеся сообщения
    node_telemetry_flush();

    // Удаляем задачу
    if (s_telemetry_engine.flush_task) {
        vTaskDelete(s_telemetry_engine.flush_task);
        s_telemetry_engine.flush_task = NULL;
    }

    // Удаляем mutex
    if (s_telemetry_engine.mutex) {
        vSemaphoreDelete(s_telemetry_engine.mutex);
        s_telemetry_engine.mutex = NULL;
    }

    memset(&s_telemetry_engine, 0, sizeof(s_telemetry_engine));
    ESP_LOGI(TAG, "Telemetry engine deinitialized");
    return ESP_OK;
}

