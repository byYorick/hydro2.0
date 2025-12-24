/**
 * @file main.c
 * @brief Точка входа для relay_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include "esp_log.h"
#include "relay_node_app.h"
#include "node_utils.h"

static const char *TAG = "relay_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting relay_node...");

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    relay_node_app_init();

    ESP_LOGI(TAG, "relay_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в relay_node_start_tasks()
}
