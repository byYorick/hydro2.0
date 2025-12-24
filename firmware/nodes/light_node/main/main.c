/**
 * @file main.c
 * @brief Точка входа для light_node
 */

#include "esp_log.h"
#include "light_node_app.h"
#include "node_utils.h"

static const char *TAG = "light_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting light_node...");

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    light_node_app_init();

    ESP_LOGI(TAG, "light_node started");
}
