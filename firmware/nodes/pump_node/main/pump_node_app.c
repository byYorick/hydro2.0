/**
 * @file pump_node_app.c
 * @brief Main application logic for pump_node
 * 
 * Pump node for controlling pumps and monitoring current via INA209
 * According to NODE_ARCH_FULL.md and MQTT_SPEC_FULL.md
 * 
 * Тонкий слой координации - вся логика делегируется в компоненты
 */

#include "pump_node_app.h"
#include "pump_node_init.h"
#include "pump_node_defaults.h"
#include "pump_driver.h"
#include "config_storage.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "pump_node";

// Кеш для node_id (опционально, для быстрого доступа)
static char s_node_id_cache[64] = {0};
static bool s_node_id_cache_valid = false;
static SemaphoreHandle_t s_node_id_cache_mutex = NULL;  // Mutex для защиты кеша node_id

// State getters/setters - делегируют в компоненты
bool pump_node_is_pump_control_initialized(void) {
    return pump_driver_is_initialized();
}

/**
 * @brief Инициализация mutex для кеша node_id
 */
static void init_node_id_cache_mutex(void) {
    if (s_node_id_cache_mutex == NULL) {
        s_node_id_cache_mutex = xSemaphoreCreateMutex();
        if (s_node_id_cache_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create node_id cache mutex");
        }
    }
}

const char* pump_node_get_node_id(void) {
    // Инициализация mutex при первом вызове
    init_node_id_cache_mutex();
    
    // Захватываем mutex
    if (s_node_id_cache_mutex != NULL && 
        xSemaphoreTake(s_node_id_cache_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        
        // Если кеш валиден, возвращаем его
        if (s_node_id_cache_valid) {
            xSemaphoreGive(s_node_id_cache_mutex);
            return s_node_id_cache;
        }
        
        // Иначе получаем из config_storage
        if (config_storage_get_node_id(s_node_id_cache, sizeof(s_node_id_cache)) == ESP_OK) {
            s_node_id_cache_valid = true;
            xSemaphoreGive(s_node_id_cache_mutex);
            return s_node_id_cache;
        }
        
        // Если не найдено, возвращаем дефолтное значение
        if (s_node_id_cache[0] == '\0') {
            strncpy(s_node_id_cache, PUMP_NODE_DEFAULT_NODE_ID, sizeof(s_node_id_cache) - 1);
            s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
        }
        
        xSemaphoreGive(s_node_id_cache_mutex);
        return s_node_id_cache;
    } else {
        // Если mutex недоступен, используем без защиты (fallback)
        ESP_LOGW(TAG, "Failed to take node_id cache mutex, using unsafe access");
        if (!s_node_id_cache_valid) {
            if (config_storage_get_node_id(s_node_id_cache, sizeof(s_node_id_cache)) == ESP_OK) {
                s_node_id_cache_valid = true;
            } else if (s_node_id_cache[0] == '\0') {
                strncpy(s_node_id_cache, PUMP_NODE_DEFAULT_NODE_ID, sizeof(s_node_id_cache) - 1);
                s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
            }
        }
        return s_node_id_cache;
    }
}

void pump_node_set_node_id(const char *node_id) {
    if (node_id) {
        // Инициализация mutex при первом вызове
        init_node_id_cache_mutex();
        
        // Захватываем mutex
        if (s_node_id_cache_mutex != NULL && 
            xSemaphoreTake(s_node_id_cache_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
            strncpy(s_node_id_cache, node_id, sizeof(s_node_id_cache) - 1);
            s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
            s_node_id_cache_valid = true;
            xSemaphoreGive(s_node_id_cache_mutex);
        } else {
            // Если mutex недоступен, используем без защиты (fallback)
            ESP_LOGW(TAG, "Failed to take node_id cache mutex, using unsafe write");
            strncpy(s_node_id_cache, node_id, sizeof(s_node_id_cache) - 1);
            s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
            s_node_id_cache_valid = true;
        }
        // Примечание: сохранение в config_storage должно происходить через config handler
    }
}

/**
 * @brief Initialize pump_node application
 */
void pump_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing pump_node application...");
    
    esp_err_t err = pump_node_init_components();
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Failed to initialize components: %s", esp_err_to_name(err));
        return;
    }
    
    // If setup mode was triggered, it will reboot the device
    if (err == ESP_ERR_NOT_FOUND) {
        return;
    }
    
    ESP_LOGI(TAG, "pump_node application initialized");
    
    // Start FreeRTOS tasks for current polling and heartbeat
    pump_node_start_tasks();
}
