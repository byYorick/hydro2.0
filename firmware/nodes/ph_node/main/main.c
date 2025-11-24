/**
 * @file main.c
 * @brief Точка входа для ph_node
 * 
 * Согласно FIRMWARE_STRUCTURE.md и NODE_ARCH_FULL.md
 */

#include <stdio.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_task_wdt.h"
#include "ph_node_app.h"

static const char *TAG = "ph_main";

void app_main(void) {
    ESP_LOGI(TAG, "Starting ph_node...");

    // Инициализация watchdog таймера (10 секунд согласно DEVICE_NODE_PROTOCOL.md)
    // Конфигурация watchdog берется из sdkconfig:
    // - CONFIG_ESP_TASK_WDT_TIMEOUT_S=10 (10 секунд)
    // - CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0=n (не проверяем idle задачи CPU0)
    // - CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1=n (не проверяем idle задачи CPU1)
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = 10000,  // 10 секунд (согласовано с CONFIG_ESP_TASK_WDT_TIMEOUT_S)
        .idle_core_mask = 0,  // Не мониторим idle задачи (отключено в sdkconfig)
        .trigger_panic = true  // Panic при срабатывании
    };
    esp_err_t wdt_err = esp_task_wdt_init(&wdt_config);
    if (wdt_err == ESP_OK) {
        ESP_LOGI(TAG, "Watchdog timer initialized (10 seconds, idle tasks disabled)");
    } else if (wdt_err == ESP_ERR_INVALID_STATE) {
        // Watchdog уже инициализирован (возможно, ESP-IDF сделал это автоматически)
        // Проверяем, что конфигурация правильная
        ESP_LOGI(TAG, "Watchdog timer already initialized, using existing configuration");
    } else {
        ESP_LOGW(TAG, "Failed to initialize watchdog: %s", esp_err_to_name(wdt_err));
    }
    // НЕ добавляем main_task в watchdog, так как он завершается после app_main()
    // и переходит в idle loop

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
    // Wi-Fi менеджер инициализируется в ph_node_app_init()
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Инициализация приложения
    ph_node_app_init();

    ESP_LOGI(TAG, "ph_node started");
    
    // app_main завершается, main_task переходит в idle loop
    // Все рабочие задачи уже добавлены в watchdog в ph_node_start_tasks()
}

