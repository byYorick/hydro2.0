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
    if (status->wifi_connected) {
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            status->wifi_rssi = ap_info.rssi;
        }
    }
    
    return ESP_OK;
}

