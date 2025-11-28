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
#include "esp_log.h"

static const char *TAG = "climate_node";

/**
 * @brief Инициализация climate_node
 */
void climate_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing climate_node...");
    
    // Используем модульную систему инициализации
    esp_err_t err = climate_node_init_components();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize climate_node components: %s", esp_err_to_name(err));
        return;
    }
    
    ESP_LOGI(TAG, "climate_node application initialized");
    
    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    climate_node_start_tasks();
}
