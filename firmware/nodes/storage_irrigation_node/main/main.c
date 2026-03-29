/**
 * @file main.c
 * @brief Точка входа для storage_irrigation_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include "esp_log.h"
#include "storage_irrigation_node_app.h"
#include "node_utils.h"

void app_main(void) {
    // Оставляем только high-signal runtime logs: команды и состояние датчиков.
    esp_log_level_set("*", ESP_LOG_WARN);
    esp_log_level_set("node_command_handler", ESP_LOG_INFO);
    esp_log_level_set("storage_irrigation_node_framework", ESP_LOG_INFO);

    // Общая сеть + NVS + Wi-Fi STA (идемпотентно для всех нод)
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());

    // Инициализация приложения
    storage_irrigation_node_app_init();
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в storage_irrigation_node_start_tasks()
}
