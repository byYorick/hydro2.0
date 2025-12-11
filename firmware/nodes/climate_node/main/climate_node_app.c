/**
 * @file climate_node_app.c
 * @brief Основная логика climate_node
 * 
 * Климатическая нода для измерения температуры, влажности, CO₂ и управления
 * вентиляторами, нагревателями, освещением
 * Согласно NODE_ARCH_FULL.md и MQTT_SPEC_FULL.md
 */

#include "climate_node_app.h"
#include "climate_node_init.h"
#include "climate_node_defaults.h"
#include "factory_reset_button.h"
#include "esp_log.h"
#include "esp_err.h"

static const char *TAG = "climate_node";

/**
 * @brief Инициализация climate_node
 */
void climate_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing climate_node...");

    factory_reset_button_config_t reset_cfg = {
        .gpio_num = CLIMATE_NODE_FACTORY_RESET_GPIO,
        .active_level_low = CLIMATE_NODE_FACTORY_RESET_ACTIVE_LOW,
        .pull_up = true,
        .pull_down = false,
        .hold_time_ms = CLIMATE_NODE_FACTORY_RESET_HOLD_MS,
        .poll_interval_ms = CLIMATE_NODE_FACTORY_RESET_POLL_INTERVAL
    };
    esp_err_t reset_err = factory_reset_button_init(&reset_cfg);
    if (reset_err != ESP_OK) {
        ESP_LOGW(TAG, "Factory reset button not armed: %s", esp_err_to_name(reset_err));
    }
    
    // Используем модульную систему инициализации
    esp_err_t err = climate_node_init_components();
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGE(TAG, "Failed to initialize climate_node components: %s", esp_err_to_name(err));
        return;
    }
    
    // If setup mode was triggered, it will reboot the device
    if (err == ESP_ERR_NOT_FOUND) {
        return;
    }
    
    ESP_LOGI(TAG, "climate_node application initialized");
    
    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    climate_node_start_tasks();
}
