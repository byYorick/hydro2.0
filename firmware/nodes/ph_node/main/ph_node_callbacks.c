/**
 * @file ph_node_callbacks.c
 * @brief Event callbacks implementation для ph_node
 * 
 * Обработка событий подключения MQTT и WiFi с обновлением OLED UI
 */

#include "ph_node_callbacks.h"
#include "ph_node_app.h"
#include "oled_ui.h"
#include "connection_status.h"
#include "esp_log.h"

static const char *TAG = "ph_node_cb";

/**
 * @brief Обновление OLED UI с текущим статусом соединений
 */
static void update_oled_connections(void) {
    if (!ph_node_is_oled_initialized()) {
        return;
    }
    
    connection_status_t conn_status;
    if (connection_status_get(&conn_status) != ESP_OK) {
        return;
    }
    
    // Получение текущей модели и обновление только статуса соединений
    oled_ui_model_t model = {0};
    model.connections.wifi_connected = conn_status.wifi_connected;
    model.connections.mqtt_connected = conn_status.mqtt_connected;
    model.connections.wifi_rssi = conn_status.wifi_rssi;
    
    oled_ui_update_model(&model);
}

void ph_node_mqtt_connection_cb(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - ph_node is online");
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - ph_node is offline");
    }
    
    // Обновление OLED UI через общий компонент
    update_oled_connections();
}

void ph_node_wifi_connection_cb(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "Wi-Fi connected");
    } else {
        ESP_LOGW(TAG, "Wi-Fi disconnected");
    }
    
    // Обновление OLED UI через общий компонент
    update_oled_connections();
}

