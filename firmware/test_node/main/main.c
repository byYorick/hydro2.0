/**
 * @file main.c
 * @brief Главный файл тестовой прошивки
 */

#include "test_node_app.h"
#include "esp_log.h"
#include "node_utils.h"

static const char *TAG = "test_node_main";

void app_main(void) {
    ESP_LOGI(TAG, "Test node starting...");
    
    // Общая инициализация NVS + esp_netif + event loop + Wi‑Fi STA
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());
    
    // Инициализация тестовой ноды
    ESP_ERROR_CHECK(test_node_app_init());
    
    ESP_LOGI(TAG, "Test node started successfully");
}
