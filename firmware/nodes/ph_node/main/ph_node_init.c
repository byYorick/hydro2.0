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
#include "ph_node_framework_integration.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "trema_ph.h"
#include "oled_ui.h"
#include "pump_driver.h"
#include "mqtt_manager.h"
#include "setup_portal.h"
#include "connection_status.h"
#include "node_utils.h"
#include "node_state_manager.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_mac.h"
#include "esp_idf_version.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ph_node_init";

// Setup mode function
void ph_node_run_setup_mode(void) {
    ESP_LOGI(TAG, "Starting setup mode for PH node");
    
    // Инициализируем I2C шину для OLED перед запуском setup mode
    // Это нужно, чтобы OLED мог работать в setup mode
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGI(TAG, "Initializing I2C bus 0 for OLED in setup mode...");
        i2c_bus_config_t i2c0_config = {
            .sda_pin = PH_NODE_I2C_BUS_0_SDA,
            .scl_pin = PH_NODE_I2C_BUS_0_SCL,
            .clock_speed = 100000,
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

/**
 * @brief Публикация node_hello сообщения для регистрации узла
 */
static void ph_node_publish_hello(void) {
    // Получаем MAC адрес как hardware_id
    uint8_t mac[6] = {0};
    esp_err_t err = esp_efuse_mac_get_default(mac);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get MAC address: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "system", err, "Failed to get MAC address for node_hello");
        return;
    }
    
    // Формируем hardware_id из MAC адреса
    char hardware_id[32];
    snprintf(hardware_id, sizeof(hardware_id), "esp32-%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    
    // Получаем версию прошивки
    // Используем версию ESP-IDF, так как версия прошивки не хранится в config_storage
    char fw_version[64];
    const char *idf_ver = esp_get_idf_version();
    // esp_get_idf_version() уже возвращает версию с префиксом "v", не добавляем еще один
    snprintf(fw_version, sizeof(fw_version), "%s", idf_ver);
    
    // Создаем JSON сообщение node_hello
    cJSON *hello = cJSON_CreateObject();
    if (!hello) {
        ESP_LOGE(TAG, "Failed to create node_hello JSON");
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", ESP_ERR_NO_MEM, "Failed to create node_hello JSON");
        return;
    }
    
    cJSON_AddStringToObject(hello, "message_type", "node_hello");
    cJSON_AddStringToObject(hello, "hardware_id", hardware_id);
    cJSON_AddStringToObject(hello, "node_type", "ph");
    cJSON_AddStringToObject(hello, "fw_version", fw_version);
    
    // Добавляем capabilities
    cJSON *capabilities = cJSON_CreateArray();
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("ph"));
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("temperature"));
    cJSON_AddItemToObject(hello, "capabilities", capabilities);
    
    // Публикуем в общий топик для регистрации
    char *json_str = cJSON_PrintUnformatted(hello);
    if (json_str) {
        // Используем внутреннюю функцию публикации через mqtt_manager
        // Публикуем в hydro/node_hello для начальной регистрации
        // Это будет обработано history-logger и зарегистрирует узел
        ESP_LOGI(TAG, "Publishing node_hello: hardware_id=%s", hardware_id);
        
        // Публикуем через mqtt_manager_publish_raw
        esp_err_t pub_err = mqtt_manager_publish_raw("hydro/node_hello", json_str, 1, 0);
        if (pub_err == ESP_OK) {
            ESP_LOGI(TAG, "node_hello published successfully");
        } else {
            ESP_LOGE(TAG, "Failed to publish node_hello: %s", esp_err_to_name(pub_err));
            node_state_manager_report_error(ERROR_LEVEL_ERROR, "mqtt", pub_err, "Failed to publish node_hello");
        }
        
        free(json_str);
    }
    
    cJSON_Delete(hello);
}

void ph_node_mqtt_connection_cb(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - ph_node is online");
        
        // Публикуем node_hello при первом подключении для регистрации
        // Проверяем, есть ли уже конфиг с правильными ID (не временные)
        char node_id[CONFIG_STORAGE_MAX_STRING_LEN];
        char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
        bool has_node_id = (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK);
        bool has_gh_uid = (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK);
        bool has_valid_config = has_node_id && 
                                strcmp(node_id, "node-temp") != 0 &&
                                has_gh_uid &&
                                strcmp(gh_uid, "gh-temp") != 0;
        
        if (!has_valid_config) {
            // Устройство еще не зарегистрировано - публикуем node_hello
            ph_node_publish_hello();
        }
        
        // Запрашиваем время у сервера для синхронизации
        node_utils_request_time();

        // Публикуем текущий NodeConfig на сервер
        node_utils_publish_config_report();
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
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "config_storage", err, "Config storage initialization failed");
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
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "wifi_manager", err, "WiFi manager initialization failed");
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
    err = ph_node_init_step_i2c(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 3 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "i2c_bus", err, "I2C bus initialization failed");
        // Continue - I2C может быть не критичен
    }
    
    // [Step 4/8] pH Sensor
    err = ph_node_init_step_ph_sensor(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Step 4 failed: %s (will retry later)", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_WARNING, "ph_sensor", err, "pH sensor initialization failed, will retry");
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
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "pump_driver", err, "Pump driver initialization failed");
        // Continue - насосы могут быть настроены позже
    }
    
    // [Step 7/8] MQTT Manager
    err = ph_node_init_step_mqtt(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 7 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "mqtt_manager", err, "MQTT manager initialization failed");
        return err;
    }
    
    // Инициализация node_framework (перед регистрацией MQTT callbacks)
    esp_err_t fw_err = ph_node_framework_init();
    if (fw_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s. Entering safe mode and restarting...", 
                 esp_err_to_name(fw_err));
        node_state_manager_report_error(ERROR_LEVEL_CRITICAL, "node_framework", fw_err, "Node framework initialization failed, restarting");
        // Останавливаем насосы на всякий случай
        pump_driver_emergency_stop();
        // Даем логам уйти (включая отправку ошибки)
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
        return fw_err;
    }

    // Используем node_framework обработчики
    ph_node_framework_register_mqtt_handlers();
    ESP_LOGI(TAG, "Using node_framework handlers");
    
    mqtt_manager_register_connection_cb(ph_node_mqtt_connection_cb, NULL);
    
    // [Step 8/8] Finalize
    err = ph_node_init_step_finalize(&init_ctx, &step_result);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Step 8 failed: %s", esp_err_to_name(err));
        node_state_manager_report_error(ERROR_LEVEL_ERROR, "init_finalize", err, "Initialization finalization failed");
        return err;
    }
    
    return ESP_OK;
}
