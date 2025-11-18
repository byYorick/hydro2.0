/**
 * @file ph_node_init.c
 * @brief Component initialization, setup mode and callbacks implementation
 * 
 * Объединяет:
 * - Инициализацию компонентов
 * - Setup mode (WiFi provisioning)
 * - Event callbacks (WiFi, MQTT)
 */

#include "ph_node_init.h"
#include "ph_node_app.h"
#include "ph_node_defaults.h"
#include "ph_node_init_steps.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "trema_ph.h"
#include "oled_ui.h"
#include "pump_driver.h"
#include "mqtt_manager.h"
#include "ph_node_handlers.h"
#include "setup_portal.h"
#include "connection_status.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "ph_node_init";

// Setup mode function
void ph_node_run_setup_mode(void) {
    ESP_LOGI(TAG, "Starting setup mode for PH node");
    
    setup_portal_full_config_t config = {
        .node_type_prefix = "PH",
        .ap_password = PH_NODE_SETUP_AP_PASSWORD,
        .enable_oled = true,
        .oled_user_ctx = NULL
    };
    
    // This function will block until credentials are received and device reboots
    setup_portal_run_full_setup(&config);
}

// Callback functions
static void update_oled_connections(void) {
    if (!oled_ui_is_initialized()) {
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

esp_err_t ph_node_init_components(void) {
    ESP_LOGI(TAG, "Initializing ph_node components...");
    
    ph_node_init_context_t init_ctx = {
        .show_oled_steps = true,
        .user_ctx = NULL
    };
    
    ph_node_init_step_result_t step_result = {0};
    
    // [Step 1/8] Config Storage
    esp_err_t err = ph_node_init_step_config_storage(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 1 failed: %s", esp_err_to_name(err));
        return err;
    }
    
    // [Step 2/8] Wi-Fi Manager
    err = ph_node_init_step_wifi(&init_ctx, &step_result);
    if (err == ESP_ERR_NOT_FOUND) {
        // WiFi не настроен - запускаем setup mode
        ESP_LOGW(TAG, "WiFi config not found, starting setup mode...");
        ph_node_run_setup_mode();
        return ESP_ERR_NOT_FOUND; // setup mode will reboot device
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 2 failed: %s", esp_err_to_name(err));
        return err;
    }
    
    // Регистрация Wi-Fi callback и подключение
    wifi_manager_register_connection_cb(ph_node_wifi_connection_cb, NULL);
    
    config_storage_wifi_t wifi_cfg;
    if (config_storage_get_wifi(&wifi_cfg) == ESP_OK) {
    wifi_manager_config_t wifi_config;
    static char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
    static char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
    
    strncpy(wifi_ssid, wifi_cfg.ssid, sizeof(wifi_ssid) - 1);
    strncpy(wifi_password, wifi_cfg.password, sizeof(wifi_password) - 1);
    wifi_config.ssid = wifi_ssid;
    wifi_config.password = wifi_password;
    ESP_LOGI(TAG, "Connecting to Wi-Fi from config: %s", wifi_cfg.ssid);
    
    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect to Wi-Fi: %s", esp_err_to_name(err));
        // Continue - Wi-Fi will try to reconnect automatically
    }
    }
    
    // [Step 3/8] I2C Buses
    err = ph_node_init_step_i2c(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 3 failed: %s", esp_err_to_name(err));
        // Continue - I2C может быть не критичен
    }
    
    // [Step 4/8] pH Sensor
    err = ph_node_init_step_ph_sensor(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Step 4 failed: %s (will retry later)", esp_err_to_name(err));
        // Continue - датчик может быть не подключен
    }
    
    // [Step 5/8] OLED UI
    err = ph_node_init_step_oled(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Step 5 failed: %s (OLED may not be available)", esp_err_to_name(err));
        // Continue - OLED может быть не подключен
    }
    
    // [Step 6/8] Pump Driver
    err = ph_node_init_step_pumps(&init_ctx, &step_result);
    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Step 6: No pump channels in config (will initialize when config received)");
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 6 failed: %s", esp_err_to_name(err));
        // Continue - насосы могут быть настроены позже
    }
    
    // [Step 7/8] MQTT Manager
    err = ph_node_init_step_mqtt(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 7 failed: %s", esp_err_to_name(err));
        return err;
    }
    
    // Регистрация MQTT callbacks
    mqtt_manager_register_config_cb(ph_node_config_handler, NULL);
    mqtt_manager_register_command_cb(ph_node_command_handler, NULL);
    mqtt_manager_register_connection_cb(ph_node_mqtt_connection_cb, NULL);
    
    // [Step 8/8] Finalize
    err = ph_node_init_step_finalize(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 8 failed: %s", esp_err_to_name(err));
        return err;
    }
    
    return ESP_OK;
}

