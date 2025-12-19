/**
 * @file relay_node_app.c
 * @brief Main application logic for relay_node
 * 
 * Relay node for controlling water storage and refresh system
 * According to NODE_ARCH_FULL.md and MQTT_SPEC_FULL.md
 * 
 * Тонкий слой координации - вся логика делегируется в компоненты
 */

#include "relay_node_app.h"
#include "relay_node_init.h"
#include "relay_node_defaults.h"
#include "oled_ui.h"
#include "relay_driver.h"
#include "config_storage.h"
#include "mqtt_manager.h"
#include "factory_reset_button.h"
#include "node_utils.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include <string.h>

static const char *TAG = "relay_node";

// State getters/setters - делегируют в компоненты
bool relay_node_is_relay_control_initialized(void) {
    return relay_driver_is_initialized();
}

bool relay_node_is_oled_initialized(void) {
    return oled_ui_is_initialized();
}

const char* relay_node_get_node_id(void) {
    static char node_id[64] = {0};
    
    // Получаем из config_storage (кеш не нужен, так как node_id меняется редко)
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        // Если не найдено, возвращаем дефолтное значение
        strncpy(node_id, RELAY_NODE_DEFAULT_NODE_ID, sizeof(node_id) - 1);
        node_id[sizeof(node_id) - 1] = '\0';
    }
    
    return node_id;
}

void relay_node_set_node_id(const char *node_id) {
    // Примечание: сохранение в config_storage должно происходить через config handler
    // Эта функция оставлена для совместимости, но фактически node_id управляется через node_framework
    (void)node_id;
}

/**
 * @brief Initialize relay_node application
 */
void relay_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing relay_node application...");

    factory_reset_button_config_t reset_cfg = {
        .gpio_num = RELAY_NODE_FACTORY_RESET_GPIO,
        .active_level_low = RELAY_NODE_FACTORY_RESET_ACTIVE_LOW,
        .pull_up = true,
        .pull_down = false,
        .hold_time_ms = RELAY_NODE_FACTORY_RESET_HOLD_MS,
        .poll_interval_ms = RELAY_NODE_FACTORY_RESET_POLL_INTERVAL
    };
    esp_err_t reset_err = factory_reset_button_init(&reset_cfg);
    if (reset_err != ESP_OK) {
        ESP_LOGW(TAG, "Factory reset button not armed: %s", esp_err_to_name(reset_err));
    }
    
    esp_err_t err = relay_node_init_components();
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Failed to initialize components: %s", esp_err_to_name(err));
        return;
    }
    
    // If setup mode was triggered, it will reboot the device
    if (err == ESP_ERR_NOT_FOUND) {
        return;
    }
    
    ESP_LOGI(TAG, "relay_node application initialized");
    
    // Start FreeRTOS tasks for heartbeat
    relay_node_start_tasks();
}
