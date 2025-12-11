/**
 * @file main.c
 * @brief Точка входа для ec_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include <stdio.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "ec_node_app.h"

static const char *TAG = "ec_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting ec_node...");

    // Инициализация watchdog таймера выполняется автоматически в node_framework_init()

    // Инициализация NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Инициализация сетевого интерфейса
    ESP_ERROR_CHECK(esp_netif_init());
    
    // Инициализация event loop для Wi-Fi и MQTT
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    // Инициализация Wi-Fi (базовая)
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Инициализация приложения
    ec_node_app_init();

    ESP_LOGI(TAG, "ec_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в ec_node_start_tasks()
}

