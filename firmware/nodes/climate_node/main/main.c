/**
 * @file main.c
 * @brief Точка входа для climate_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include "esp_log.h"
#include "climate_node_app.h"
#include "node_utils.h"

static const char *TAG = "climate_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting climate_node...");

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    climate_node_app_init();

    ESP_LOGI(TAG, "climate_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в climate_node_start_tasks()
}
