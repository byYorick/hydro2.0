/**
 * @file ph_node_app.c
 * @brief Main application logic for ph_node
 * 
 * pH node for measuring pH and controlling acid/base pumps
 * According to NODE_ARCH_FULL.md and MQTT_SPEC_FULL.md
 * 
 * Тонкий слой координации - вся логика делегируется в компоненты
 */

#include "ph_node_app.h"
#include "ph_node_init.h"
#include "ph_node_defaults.h"
#include "trema_ph.h"
#include "oled_ui.h"
#include "pump_driver.h"
#include "config_storage.h"
#include "factory_reset_button.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ph_node";

// Кеш для node_id (опционально, для быстрого доступа)
static char s_node_id_cache[64] = {0};
static bool s_node_id_cache_valid = false;
static SemaphoreHandle_t s_node_id_cache_mutex = NULL;  // Mutex для защиты кеша node_id

// State getters/setters - делегируют в компоненты
bool ph_node_is_ph_sensor_initialized(void) {
    return trema_ph_is_initialized();
}

bool ph_node_is_oled_initialized(void) {
    return oled_ui_is_initialized();
}

bool ph_node_is_pump_control_initialized(void) {
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

const char* ph_node_get_node_id(void) {
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
            strncpy(s_node_id_cache, PH_NODE_DEFAULT_NODE_ID, sizeof(s_node_id_cache) - 1);
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
                strncpy(s_node_id_cache, PH_NODE_DEFAULT_NODE_ID, sizeof(s_node_id_cache) - 1);
                s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
            }
        }
        return s_node_id_cache;
    }
}

void ph_node_set_node_id(const char *node_id) {
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
 * @brief Initialize ph_node application
 */
void ph_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing ph_node application...");

    factory_reset_button_config_t reset_cfg = {
        .gpio_num = PH_NODE_FACTORY_RESET_GPIO,
        .active_level_low = PH_NODE_FACTORY_RESET_ACTIVE_LOW,
        .pull_up = true,
        .pull_down = false,
        .hold_time_ms = PH_NODE_FACTORY_RESET_HOLD_MS,
        .poll_interval_ms = PH_NODE_FACTORY_RESET_POLL_INTERVAL
    };
    esp_err_t reset_err = factory_reset_button_init(&reset_cfg);
    if (reset_err != ESP_OK) {
        ESP_LOGW(TAG, "Factory reset button not armed: %s", esp_err_to_name(reset_err));
    }
    
    esp_err_t err = ph_node_init_components();
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Failed to initialize components: %s", esp_err_to_name(err));
        return;
    }
    
    // If setup mode was triggered, it will reboot the device
    if (err == ESP_ERR_NOT_FOUND) {
        return;
    }
    
    ESP_LOGI(TAG, "ph_node application initialized");
    
    // Start FreeRTOS tasks for sensor polling and heartbeat
    ph_node_start_tasks();
}
