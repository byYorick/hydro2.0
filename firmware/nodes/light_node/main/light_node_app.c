/**
 * @file light_node_app.c
 * @brief Основная логика light_node
 * 
 * Нода света для измерения освещенности
 */

#include "light_node_app.h"
#include "light_node_init.h"
#include "light_node_defaults.h"
#include "factory_reset_button.h"
#include "esp_log.h"

static const char *TAG = "light_node";

/**
 * @brief Инициализация light_node
 */
void light_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing light_node...");

    factory_reset_button_config_t reset_cfg = {
        .gpio_num = LIGHT_NODE_FACTORY_RESET_GPIO,
        .active_level_low = LIGHT_NODE_FACTORY_RESET_ACTIVE_LOW,
        .pull_up = true,
        .pull_down = false,
        .hold_time_ms = LIGHT_NODE_FACTORY_RESET_HOLD_MS,
        .poll_interval_ms = LIGHT_NODE_FACTORY_RESET_POLL_INTERVAL
    };
    esp_err_t reset_err = factory_reset_button_init(&reset_cfg);
    if (reset_err != ESP_OK) {
        ESP_LOGW(TAG, "Factory reset button not armed: %s", esp_err_to_name(reset_err));
    }
    
    // Используем модульную систему инициализации
    esp_err_t err = light_node_init_components();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize light_node components: %s", esp_err_to_name(err));
        return;
    }
    
    ESP_LOGI(TAG, "light_node application initialized");
    
    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    light_node_start_tasks();
}
