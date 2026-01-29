/**
 * @file climate_node_init.c
 * @brief Component initialization, setup mode and callbacks implementation
 * 
 * Объединяет:
 * - Инициализацию компонентов
 * - Setup mode (WiFi provisioning)
 * - Event callbacks (WiFi, MQTT)
 */

#include "climate_node_init.h"
#include "climate_node_app.h"
#include "climate_node_defaults.h"
#include "climate_node_init_steps.h"
#include "climate_node_framework_integration.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "oled_ui.h"
#include "mqtt_manager.h"
#include "setup_portal.h"
#include "connection_status.h"
#include "node_utils.h"
#include "node_state_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "climate_node_init";

// Setup mode function
void climate_node_run_setup_mode(void) {
    ESP_LOGI(TAG, "Starting setup mode for CLIMATE node");
    
    // Инициализируем I2C шину для OLED перед запуском setup mode
    // Это нужно, чтобы OLED мог работать в setup mode
    // OLED UI использует I2C_BUS_0
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGI(TAG, "Initializing I2C bus 0 for OLED in setup mode...");
        i2c_bus_config_t i2c0_config = {
            .sda_pin = CLIMATE_NODE_I2C_BUS_0_SDA,
            .scl_pin = CLIMATE_NODE_I2C_BUS_0_SCL,
            .clock_speed = CLIMATE_NODE_I2C_CLOCK_SPEED,
            .pullup_enable = true
        };
        esp_err_t i2c_err = i2c_bus_init_bus(I2C_BUS_0, &i2c0_config);
        if (i2c_err == ESP_OK) {
            ESP_LOGI(TAG, "I2C bus 0 initialized for setup mode OLED");
        } else {
            ESP_LOGW(TAG, "Failed to initialize I2C bus 0 for setup mode: %s", esp_err_to_name(i2c_err));
        }
    }
    
    setup_portal_full_config_t config = {
        .node_type_prefix = "CLIMATE",
        .ap_password = CLIMATE_NODE_SETUP_AP_PASSWORD,
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

/**
 * @brief Публикация node_hello сообщения для регистрации узла
 */
static void climate_node_publish_hello(void) {
    static const char *capabilities[] = {
        "temperature",
        "humidity",
        "co2",
        "lighting",
        "ventilation"
    };
    esp_err_t err = node_utils_publish_node_hello("climate", capabilities, 5);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to publish node_hello: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", err, "Failed to publish node_hello");
    }
}

void climate_node_mqtt_connection_cb(bool connected, void *user_ctx) {
    ESP_LOGI(TAG, "climate_node_mqtt_connection_cb called: connected=%d", connected);
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - climate_node is online");
        
        // Публикуем node_hello только если узел еще не зарегистрирован (временные ID)
        if (node_utils_should_send_node_hello()) {
            ESP_LOGI(TAG, "Publishing node_hello for registration");
            climate_node_publish_hello();
            ESP_LOGI(TAG, "node_hello publish call completed");
        }
        
        // Запрашиваем время у сервера для синхронизации
        node_utils_request_time();

        // Публикуем текущий NodeConfig на сервер
        node_utils_publish_config_report();
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - climate_node is offline");
    }
    
    // Обновление OLED UI через общий компонент
    update_oled_connections();
}

void climate_node_wifi_connection_cb(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "Wi-Fi connected");
    } else {
        ESP_LOGW(TAG, "Wi-Fi disconnected");
    }
    
    // Обновление OLED UI через общий компонент
    update_oled_connections();
}

esp_err_t climate_node_init_components(void) {
    ESP_LOGI(TAG, "Initializing climate_node components...");
    
    climate_node_init_context_t init_ctx = {
        .show_oled_steps = true,
        .user_ctx = NULL
    };
    
    climate_node_init_step_result_t step_result = {0};
    
    // [Step 1/8] Config Storage
    esp_err_t err = climate_node_init_step_config_storage(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 1 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "config_storage", err, "Config storage initialization failed");
        return err;
    }
    
    // [Step 2/8] Wi-Fi Manager
    err = climate_node_init_step_wifi(&init_ctx, &step_result);
    if (err == ESP_ERR_NOT_FOUND) {
        // WiFi не настроен - запускаем setup mode
        ESP_LOGW(TAG, "WiFi config not found, starting setup mode...");
        climate_node_run_setup_mode();
        return ESP_ERR_NOT_FOUND; // setup mode will reboot device
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 2 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "wifi_manager", err, "WiFi manager initialization failed");
        return err;
    }
    
    // Регистрация Wi-Fi callback и подключение
    wifi_manager_register_connection_cb(climate_node_wifi_connection_cb, NULL);
    
    config_storage_wifi_t wifi_cfg;
    if (config_storage_get_wifi(&wifi_cfg) == ESP_OK) {
        wifi_manager_config_t wifi_config;
        static char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
        static char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
        
        strncpy(wifi_ssid, wifi_cfg.ssid, sizeof(wifi_ssid) - 1);
        wifi_ssid[sizeof(wifi_ssid) - 1] = '\0';
        strncpy(wifi_password, wifi_cfg.password, sizeof(wifi_password) - 1);
        wifi_password[sizeof(wifi_password) - 1] = '\0';
        wifi_config.ssid = wifi_ssid;
        wifi_config.password = wifi_password;
        ESP_LOGI(TAG, "Connecting to Wi-Fi from config: %s", wifi_cfg.ssid);
        
        err = wifi_manager_connect(&wifi_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to connect to Wi-Fi: %s", esp_err_to_name(err));
            node_state_manager_report_error(ERROR_LEVEL_WARNING, "wifi", err, "Failed to connect to Wi-Fi, will retry");
            // Continue - Wi-Fi will try to reconnect automatically
        }
    }
    
    // [Step 3/8] I2C Buses
    err = climate_node_init_step_i2c(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 3 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "i2c_bus", err, "I2C bus initialization failed");
        // Continue - I2C может быть не критичен
    }
    
    // [Step 4/8] Sensors
    err = climate_node_init_step_sensors(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Step 4 failed: %s (will retry later)", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_WARNING, "sensors", err, "Sensors initialization failed, will retry");
        // Continue - датчики могут быть не подключены
    }
    
    // [Step 5/8] OLED UI
    err = climate_node_init_step_oled(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Step 5 failed: %s (OLED may not be available)", esp_err_to_name(err));
        // Continue - OLED может быть не подключен
    }
    
    // [Step 6/8] Actuators
    err = climate_node_init_step_actuators(&init_ctx, &step_result);
    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Step 6: No actuator channels in config (will initialize when config received)");
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 6 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "actuators", err, "Actuators initialization failed");
        // Continue - актуаторы могут быть настроены позже
    }
    
    // [Step 7/8] MQTT Manager
    err = climate_node_init_step_mqtt(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 7 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "mqtt_manager", err, "MQTT manager initialization failed");
        return err;
    }
    
    // Инициализация node_framework (перед регистрацией MQTT callbacks)
    esp_err_t fw_err = climate_node_framework_init_integration();
    if (fw_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(fw_err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", fw_err, "Node framework initialization failed");
        return fw_err;
    }
    
    // Используем node_framework обработчики
    climate_node_framework_register_mqtt_handlers();
    ESP_LOGI(TAG, "Using node_framework handlers");
    
    mqtt_manager_register_connection_cb(climate_node_mqtt_connection_cb, NULL);
    
    // [Step 8/8] Finalize
    err = climate_node_init_step_finalize(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 8 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "init_finalize", err, "Initialization finalization failed");
        return err;
    }
    
    return ESP_OK;
}
