/**
 * @file main.c
 * @brief Главный файл тестовой прошивки
 */

#include "test_node_app.h"
#include "test_node_ui.h"
#include "esp_log.h"
#include "node_utils.h"

static const char *TAG = "test_node_main";

void app_main(void) {
    // В UART оставляем только лог команд test_node_cmd.
    esp_log_level_set("*", ESP_LOG_NONE);
    esp_log_level_set("test_node_cmd", ESP_LOG_INFO);

    ESP_LOGI(TAG, "Test node starting...");

    // 1) Экран поднимаем первым
    esp_err_t ui_err = test_node_ui_init();
    if (ui_err != ESP_OK) {
        ESP_LOGW(TAG, "test_node_ui_init failed: %s", esp_err_to_name(ui_err));
    } else {
        test_node_ui_show_step("3) Screen is ready");
    }

    // 2) Общая инициализация NVS + esp_netif + event loop + Wi‑Fi STA
    test_node_ui_show_step("4) Network bootstrap started");
    ESP_ERROR_CHECK(node_utils_bootstrap_network_stack());
    test_node_ui_show_step("5) Network bootstrap done");

    // 3) Инициализация тестовой ноды
    test_node_ui_show_step("6) Test node app init started");
    ESP_ERROR_CHECK(test_node_app_init());
    test_node_ui_show_step("7) Test node app init done");

    if (ui_err != ESP_OK) {
        test_node_ui_show_step("UI init failed, running headless");
    }
    
    ESP_LOGI(TAG, "Test node started successfully");
    test_node_ui_show_step("8) Startup complete");
}
