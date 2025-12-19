/**
 * @file main.c
 * @brief Точка входа для pump_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include "esp_log.h"
#include "pump_node_app.h"
#include "node_utils.h"

static const char *TAG = "pump_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting pump_node...");

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    pump_node_app_init();

    ESP_LOGI(TAG, "pump_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в pump_node_start_tasks()
}

