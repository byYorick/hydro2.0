/**
 * @file main.c
 * @brief Главный файл тестовой прошивки
 */

#include "test_node_app.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"

static const char *TAG = "test_node_main";

void app_main(void) {
    ESP_LOGI(TAG, "Test node starting...");
    
    // Инициализация NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    
    // Инициализация сетевого интерфейса
    ESP_ERROR_CHECK(esp_netif_init());
    
    // Инициализация тестовой ноды
    ESP_ERROR_CHECK(test_node_app_init());
    
    ESP_LOGI(TAG, "Test node started successfully");
}

