/**
 * @file memory_pool.c
 * @brief Реализация пула памяти для оптимизации использования памяти
 */

#include "memory_pool.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "memory_pool";

// Конфигурация по умолчанию
#define DEFAULT_JSON_OBJECT_POOL_SIZE 16
#define DEFAULT_JSON_STRING_POOL_SIZE 8
#define DEFAULT_JSON_STRING_MAX_LEN 512

// Структура для хранения JSON объекта в пуле
typedef struct {
    void *object;           // Указатель на cJSON объект
    bool in_use;            // Флаг использования
    uint32_t alloc_count;   // Счетчик выделений
} json_object_slot_t;

// Структура для хранения JSON строки в пуле
typedef struct {
    char *buffer;           // Буфер для строки
    size_t size;            // Размер буфера
    bool in_use;            // Флаг использования
    uint32_t alloc_count;   // Счетчик выделений
} json_string_slot_t;

static struct {
    bool initialized;
    memory_pool_config_t config;
    json_object_slot_t *json_object_pool;
    json_string_slot_t *json_string_pool;
    SemaphoreHandle_t mutex;
    memory_pool_metrics_t metrics;
} s_memory_pool = {0};

esp_err_t memory_pool_init(const memory_pool_config_t *config) {
    if (s_memory_pool.initialized) {
        ESP_LOGW(TAG, "Memory pool already initialized");
        return ESP_ERR_INVALID_STATE;
    }

    // Используем конфигурацию по умолчанию, если не указана
    memory_pool_config_t default_config = {
        .json_object_pool_size = DEFAULT_JSON_OBJECT_POOL_SIZE,
        .json_string_pool_size = DEFAULT_JSON_STRING_POOL_SIZE,
        .json_string_max_len = DEFAULT_JSON_STRING_MAX_LEN,
        .enable_metrics = true
    };

    if (config != NULL) {
        s_memory_pool.config = *config;
    } else {
        s_memory_pool.config = default_config;
    }

    // Создание mutex
    s_memory_pool.mutex = xSemaphoreCreateMutex();
    if (s_memory_pool.mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }

    // Инициализация метрик
    memset(&s_memory_pool.metrics, 0, sizeof(memory_pool_metrics_t));
    s_memory_pool.metrics.current_heap_free = esp_get_free_heap_size();
    s_memory_pool.metrics.min_heap_free = s_memory_pool.metrics.current_heap_free;

    // Примечание: Пул для JSON объектов не выделяется заранее,
    // так как cJSON использует malloc/free внутри себя.
    // Вместо этого, мы просто отслеживаем использование и предоставляем метрики.
    // Для JSON строк выделяем пул буферов.

    // Выделение пула для JSON строк
    s_memory_pool.json_string_pool = (json_string_slot_t *)calloc(
        s_memory_pool.config.json_string_pool_size,
        sizeof(json_string_slot_t)
    );
    if (s_memory_pool.json_string_pool == NULL) {
        ESP_LOGE(TAG, "Failed to allocate JSON string pool");
        vSemaphoreDelete(s_memory_pool.mutex);
        s_memory_pool.mutex = NULL;
        return ESP_ERR_NO_MEM;
    }

    // Выделение буферов для JSON строк
    for (size_t i = 0; i < s_memory_pool.config.json_string_pool_size; i++) {
        s_memory_pool.json_string_pool[i].buffer = (char *)malloc(
            s_memory_pool.config.json_string_max_len
        );
        if (s_memory_pool.json_string_pool[i].buffer == NULL) {
            ESP_LOGE(TAG, "Failed to allocate JSON string buffer %zu", i);
            // Освобождаем уже выделенные буферы
            for (size_t j = 0; j < i; j++) {
                free(s_memory_pool.json_string_pool[j].buffer);
            }
            free(s_memory_pool.json_string_pool);
            s_memory_pool.json_string_pool = NULL;
            vSemaphoreDelete(s_memory_pool.mutex);
            s_memory_pool.mutex = NULL;
            return ESP_ERR_NO_MEM;
        }
        s_memory_pool.json_string_pool[i].size = s_memory_pool.config.json_string_max_len;
        s_memory_pool.json_string_pool[i].in_use = false;
        s_memory_pool.json_string_pool[i].alloc_count = 0;
    }

    s_memory_pool.initialized = true;
    ESP_LOGI(TAG, "Memory pool initialized (json_string_pool_size=%zu, max_len=%zu)",
             s_memory_pool.config.json_string_pool_size,
             s_memory_pool.config.json_string_max_len);

    return ESP_OK;
}

esp_err_t memory_pool_deinit(void) {
    if (!s_memory_pool.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_memory_pool.mutex != NULL &&
        xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {

        // Освобождение пула JSON строк
        if (s_memory_pool.json_string_pool != NULL) {
            for (size_t i = 0; i < s_memory_pool.config.json_string_pool_size; i++) {
                if (s_memory_pool.json_string_pool[i].buffer != NULL) {
                    free(s_memory_pool.json_string_pool[i].buffer);
                }
            }
            free(s_memory_pool.json_string_pool);
            s_memory_pool.json_string_pool = NULL;
        }

        xSemaphoreGive(s_memory_pool.mutex);
        vSemaphoreDelete(s_memory_pool.mutex);
        s_memory_pool.mutex = NULL;
    }

    memset(&s_memory_pool, 0, sizeof(s_memory_pool));
    ESP_LOGI(TAG, "Memory pool deinitialized");
    return ESP_OK;
}

void *memory_pool_alloc_json_object(void) {
    if (!s_memory_pool.initialized) {
        // Fallback на обычное выделение
        return NULL;  // cJSON_CreateObject() будет вызван напрямую
    }

    // Примечание: cJSON использует malloc/free внутри себя,
    // поэтому мы не можем переиспользовать объекты напрямую.
    // Эта функция существует для будущей оптимизации и метрик.
    
    if (s_memory_pool.config.enable_metrics && s_memory_pool.mutex != NULL &&
        xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        s_memory_pool.metrics.json_objects_allocated++;
        s_memory_pool.metrics.pool_misses++;  // Пока нет пула, все промахи
        xSemaphoreGive(s_memory_pool.mutex);
    }

    return NULL;  // Возвращаем NULL, чтобы вызывающий код использовал cJSON_CreateObject()
}

void memory_pool_free_json_object(void *obj) {
    if (!s_memory_pool.initialized || obj == NULL) {
        return;
    }

    // Примечание: cJSON использует free() внутри cJSON_Delete(),
    // поэтому мы просто обновляем метрики.
    
    if (s_memory_pool.config.enable_metrics && s_memory_pool.mutex != NULL &&
        xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        s_memory_pool.metrics.json_objects_freed++;
        xSemaphoreGive(s_memory_pool.mutex);
    }
}

char *memory_pool_alloc_json_string(size_t size) {
    if (!s_memory_pool.initialized) {
        // Fallback на обычное выделение
        return (char *)malloc(size);
    }

    if (s_memory_pool.mutex == NULL) {
        return (char *)malloc(size);
    }

    if (xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take mutex, using malloc");
        return (char *)malloc(size);
    }

    // Поиск свободного слота в пуле
    char *result = NULL;
    for (size_t i = 0; i < s_memory_pool.config.json_string_pool_size; i++) {
        if (!s_memory_pool.json_string_pool[i].in_use) {
            // Проверка размера
            if (size <= s_memory_pool.json_string_pool[i].size) {
                s_memory_pool.json_string_pool[i].in_use = true;
                s_memory_pool.json_string_pool[i].alloc_count++;
                result = s_memory_pool.json_string_pool[i].buffer;
                
                if (s_memory_pool.config.enable_metrics) {
                    s_memory_pool.metrics.json_strings_allocated++;
                    s_memory_pool.metrics.pool_hits++;
                }
                break;
            }
        }
    }

    xSemaphoreGive(s_memory_pool.mutex);

    // Если не нашли в пуле, выделяем через malloc
    if (result == NULL) {
        result = (char *)malloc(size);
        if (result != NULL && s_memory_pool.config.enable_metrics &&
            s_memory_pool.mutex != NULL &&
            xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            s_memory_pool.metrics.json_strings_allocated++;
            s_memory_pool.metrics.pool_misses++;
            xSemaphoreGive(s_memory_pool.mutex);
        }
    }

    return result;
}

void memory_pool_free_json_string(char *str) {
    if (!s_memory_pool.initialized || str == NULL) {
        if (str != NULL) {
            free(str);
        }
        return;
    }

    if (s_memory_pool.mutex == NULL) {
        free(str);
        return;
    }

    if (xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take mutex, using free");
        free(str);
        return;
    }

    // Поиск буфера в пуле
    bool found_in_pool = false;
    for (size_t i = 0; i < s_memory_pool.config.json_string_pool_size; i++) {
        if (s_memory_pool.json_string_pool[i].buffer == str) {
            s_memory_pool.json_string_pool[i].in_use = false;
            found_in_pool = true;
            
            if (s_memory_pool.config.enable_metrics) {
                s_memory_pool.metrics.json_strings_freed++;
            }
            break;
        }
    }

    xSemaphoreGive(s_memory_pool.mutex);

    // Если не нашли в пуле, освобождаем через free
    if (!found_in_pool) {
        free(str);
        if (s_memory_pool.config.enable_metrics &&
            s_memory_pool.mutex != NULL &&
            xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            s_memory_pool.metrics.json_strings_freed++;
            xSemaphoreGive(s_memory_pool.mutex);
        }
    }
}

esp_err_t memory_pool_get_metrics(memory_pool_metrics_t *metrics) {
    if (metrics == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_memory_pool.initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    if (s_memory_pool.mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    // Обновление текущей свободной памяти
    s_memory_pool.metrics.current_heap_free = esp_get_free_heap_size();
    if (s_memory_pool.metrics.current_heap_free < s_memory_pool.metrics.min_heap_free) {
        s_memory_pool.metrics.min_heap_free = s_memory_pool.metrics.current_heap_free;
    }

    *metrics = s_memory_pool.metrics;

    xSemaphoreGive(s_memory_pool.mutex);
    return ESP_OK;
}

void memory_pool_reset_metrics(void) {
    if (!s_memory_pool.initialized || s_memory_pool.mutex == NULL) {
        return;
    }

    if (xSemaphoreTake(s_memory_pool.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        memset(&s_memory_pool.metrics, 0, sizeof(memory_pool_metrics_t));
        s_memory_pool.metrics.current_heap_free = esp_get_free_heap_size();
        s_memory_pool.metrics.min_heap_free = s_memory_pool.metrics.current_heap_free;
        xSemaphoreGive(s_memory_pool.mutex);
    }
}

bool memory_pool_is_initialized(void) {
    return s_memory_pool.initialized;
}


