/**
 * @file main.c
 * @brief Точка входа для storage_irrigation_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include "esp_log.h"
#include "storage_irrigation_node_app.h"
#include "node_utils.h"

static const char *TAG = "storage_irrigation_main";

void app_main(void) {
    // DEBUG нужен для binding/MQTT, но i2c_bus write-trace забивает monitor и мешает анализу.
    esp_log_level_set("i2c_bus", ESP_LOG_INFO);

    ESP_LOGI(TAG, "Starting storage_irrigation_node...");

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    storage_irrigation_node_app_init();

    ESP_LOGI(TAG, "storage_irrigation_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в storage_irrigation_node_start_tasks()
}
