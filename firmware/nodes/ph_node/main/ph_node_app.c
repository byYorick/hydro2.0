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
#include "trema_ph.h"
#include "oled_ui.h"
#include "pump_control.h"
#include "config_storage.h"
#include "esp_log.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ph_node";

// Кеш для node_id (опционально, для быстрого доступа)
static char s_node_id_cache[64] = {0};
static bool s_node_id_cache_valid = false;

// State getters/setters - делегируют в компоненты
bool ph_node_is_ph_sensor_initialized(void) {
    return trema_ph_is_initialized();
}

bool ph_node_is_oled_initialized(void) {
    return oled_ui_is_initialized();
}

bool ph_node_is_pump_control_initialized(void) {
    return pump_control_is_initialized();
}

const char* ph_node_get_node_id(void) {
    // Если кеш валиден, возвращаем его
    if (s_node_id_cache_valid) {
        return s_node_id_cache;
    }
    
    // Иначе получаем из config_storage
    if (config_storage_get_node_id(s_node_id_cache, sizeof(s_node_id_cache)) == ESP_OK) {
        s_node_id_cache_valid = true;
        return s_node_id_cache;
    }
    
    // Если не найдено, возвращаем дефолтное значение
    if (s_node_id_cache[0] == '\0') {
        strncpy(s_node_id_cache, "nd-ph-1", sizeof(s_node_id_cache) - 1);
        s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
    }
    return s_node_id_cache;
}

void ph_node_set_node_id(const char *node_id) {
    if (node_id) {
        strncpy(s_node_id_cache, node_id, sizeof(s_node_id_cache) - 1);
        s_node_id_cache[sizeof(s_node_id_cache) - 1] = '\0';
        s_node_id_cache_valid = true;
        // Примечание: сохранение в config_storage должно происходить через config handler
    }
}

/**
 * @brief Initialize ph_node application
 */
void ph_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing ph_node application...");
    
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
