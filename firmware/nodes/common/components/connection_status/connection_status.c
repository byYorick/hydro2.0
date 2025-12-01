/**
 * @file connection_status.c
 * @brief Реализация компонента connection_status
 */

#include "connection_status.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_wifi.h"

static const char *TAG = "connection_status";

esp_err_t connection_status_get(connection_status_t *status) {
    if (status == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Инициализация структуры
    status->wifi_connected = wifi_manager_is_connected();
    status->mqtt_connected = mqtt_manager_is_connected();
    status->wifi_rssi = -100;
    
    // Получение RSSI если WiFi подключен
    // Используем wifi_manager_get_rssi вместо прямого вызова esp_wifi_sta_get_ap_info
    // для корректной обработки случаев, когда Wi-Fi не инициализирован
    if (status->wifi_connected) {
        int8_t rssi = -100;
        esp_err_t rssi_err = wifi_manager_get_rssi(&rssi);
        if (rssi_err == ESP_OK) {
            status->wifi_rssi = rssi;
        } else {
            // Если не удалось получить RSSI, оставляем -100
            // Это может произойти, если Wi-Fi не полностью инициализирован
            ESP_LOGD(TAG, "Failed to get RSSI: %s", esp_err_to_name(rssi_err));
        }
    }
    
    return ESP_OK;
}

