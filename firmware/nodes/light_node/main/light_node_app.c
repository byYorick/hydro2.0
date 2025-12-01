/**
 * @file light_node_app.c
 * @brief Основная логика light_node
 * 
 * Нода света для измерения освещенности
 */

#include "light_node_app.h"
#include "light_node_init.h"
#include "esp_log.h"

static const char *TAG = "light_node";

/**
 * @brief Инициализация light_node
 */
void light_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing light_node...");
    
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

