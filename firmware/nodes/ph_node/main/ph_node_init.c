/**
 * @file ph_node_init.c
 * @brief Component initialization implementation
 */

#include "ph_node_init.h"
#include "ph_node_app.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "trema_ph.h"
#include "oled_ui.h"
#include "pump_control.h"
#include "mqtt_manager.h"
#include "ph_node_callbacks.h"
#include "ph_node_config_handler.h"
#include "ph_node_command_handler.h"
#include "ph_node_setup.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>

static const char *TAG = "ph_node_init";

esp_err_t ph_node_init_components(void) {
    ESP_LOGI(TAG, "Initializing ph_node components...");
    
    // Initialize config storage
    esp_err_t err = config_storage_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize config storage: %s", esp_err_to_name(err));
        return err;
    }
    
    // Try to load configuration from NVS
    err = config_storage_load();
    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No config in NVS, using defaults. Waiting for config from MQTT...");
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load config from NVS: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "Using default values, waiting for config from MQTT...");
    }
    
    // Initialize Wi-Fi manager
    err = wifi_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize Wi-Fi manager: %s", esp_err_to_name(err));
        return err;
    }
    
    // Initialize I2C bus (needed for OLED and sensors)
    ESP_LOGI(TAG, "=== I2C Bus Initialization ===");
    if (!i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "I2C bus not initialized, starting initialization...");
        err = i2c_bus_init_from_config();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to initialize I2C bus from config (%s), using defaults", esp_err_to_name(err));
            i2c_bus_config_t i2c_config = {
                .sda_pin = 8,
                .scl_pin = 9,
                .clock_speed = 100000,
                .pullup_enable = true
            };
            ESP_LOGI(TAG, "Initializing I2C bus with default config: SDA=%d, SCL=%d, speed=%d", 
                     i2c_config.sda_pin, i2c_config.scl_pin, i2c_config.clock_speed);
            err = i2c_bus_init(&i2c_config);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to initialize I2C bus: %s (error code: %d)", esp_err_to_name(err), err);
                // Continue, I2C may not be needed
            } else {
                ESP_LOGI(TAG, "I2C bus initialized successfully with defaults");
            }
        } else {
            ESP_LOGI(TAG, "I2C bus initialized successfully from config");
        }
    } else {
        ESP_LOGI(TAG, "I2C bus already initialized");
    }
    ESP_LOGI(TAG, "=== I2C Bus Initialization Complete ===");
    
    // Check for WiFi config
    config_storage_wifi_t wifi_cfg;
    bool wifi_configured = (config_storage_get_wifi(&wifi_cfg) == ESP_OK) && 
                           (strlen(wifi_cfg.ssid) > 0);
    
    if (!wifi_configured) {
        ESP_LOGW(TAG, "WiFi config not found, starting setup mode...");
        ph_node_run_setup_mode();
        return ESP_ERR_NOT_FOUND; // setup mode will reboot device
    }
    
    // Register Wi-Fi event callback
    wifi_manager_register_connection_cb(ph_node_wifi_connection_cb, NULL);
    
    // Connect to Wi-Fi from config
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
    
    // Initialize Trema pH sensor
    if (i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "Initializing Trema pH sensor...");
        if (trema_ph_init()) {
            ph_node_set_ph_sensor_initialized(true);
            ESP_LOGI(TAG, "Trema pH sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize Trema pH sensor, will retry later");
            ph_node_set_ph_sensor_initialized(false);
        }
    } else {
        ESP_LOGW(TAG, "I2C bus not available, pH sensor initialization skipped");
    }
    
    // Initialize OLED UI
    ESP_LOGI(TAG, "=== OLED UI Initialization ===");
    if (!i2c_bus_is_initialized()) {
        ESP_LOGW(TAG, "I2C bus not initialized, cannot initialize OLED");
    } else {
        ESP_LOGI(TAG, "I2C bus is initialized, proceeding with OLED init");
        const char *node_id = ph_node_get_node_id();
        ESP_LOGI(TAG, "Node ID for OLED: %s", node_id ? node_id : "NULL");
        
        oled_ui_config_t oled_config = {
            .i2c_address = 0x3C,
            .update_interval_ms = 500,
            .enable_task = true
        };
        
        ESP_LOGI(TAG, "Calling oled_ui_init with config: addr=0x%02X, interval=%dms", 
                 oled_config.i2c_address, oled_config.update_interval_ms);
        
        esp_err_t oled_err = oled_ui_init(OLED_UI_NODE_TYPE_PH, node_id, &oled_config);
        if (oled_err == ESP_OK) {
            ph_node_set_oled_initialized(true);
            ESP_LOGI(TAG, "Setting OLED state to BOOT");
            oled_err = oled_ui_set_state(OLED_UI_STATE_BOOT);
            if (oled_err != ESP_OK) {
                ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(oled_err));
            }
            ESP_LOGI(TAG, "OLED UI initialized and configured successfully");
        } else {
            ESP_LOGE(TAG, "Failed to initialize OLED UI: %s (error code: %d)", 
                     esp_err_to_name(oled_err), oled_err);
            ph_node_set_oled_initialized(false);
        }
    }
    ESP_LOGI(TAG, "=== OLED UI Initialization Complete ===");
    
    // Initialize pump control
    ESP_LOGI(TAG, "Initializing pump control...");
    pump_config_t pump_configs[PUMP_MAX] = {
        {
            .gpio_pin = 12,  // GPIO for pump_acid (can be overridden via NodeConfig)
            .max_duration_ms = 30000,  // 30 seconds maximum
            .min_off_time_ms = 5000,   // 5 seconds minimum between starts
            .ml_per_second = 2.0f     // 2 ml/sec default
        },
        {
            .gpio_pin = 13,  // GPIO for pump_base (can be overridden via NodeConfig)
            .max_duration_ms = 30000,
            .min_off_time_ms = 5000,
            .ml_per_second = 2.0f
        }
    };
    
    esp_err_t pump_err = pump_control_init(pump_configs);
    if (pump_err == ESP_OK) {
        ph_node_set_pump_control_initialized(true);
        ESP_LOGI(TAG, "Pump control initialized successfully");
    } else {
        ESP_LOGE(TAG, "Failed to initialize pump control: %s", esp_err_to_name(pump_err));
        ph_node_set_pump_control_initialized(false);
    }
    
    // Initialize MQTT client (from config or defaults)
    config_storage_mqtt_t mqtt_cfg;
    mqtt_manager_config_t mqtt_config;
    mqtt_node_info_t node_info;
    static char mqtt_host[CONFIG_STORAGE_MAX_STRING_LEN];
    static char mqtt_username[CONFIG_STORAGE_MAX_STRING_LEN];
    static char mqtt_password[CONFIG_STORAGE_MAX_STRING_LEN];
    static char node_id[64];
    static const char *default_gh_uid = "gh-1";
    static const char *default_zone_uid = "zn-3";
    
    if (config_storage_get_mqtt(&mqtt_cfg) == ESP_OK) {
        strncpy(mqtt_host, mqtt_cfg.host, sizeof(mqtt_host) - 1);
        mqtt_config.host = mqtt_host;
        mqtt_config.port = mqtt_cfg.port;
        mqtt_config.keepalive = mqtt_cfg.keepalive;
        mqtt_config.client_id = NULL;
        if (strlen(mqtt_cfg.username) > 0) {
            strncpy(mqtt_username, mqtt_cfg.username, sizeof(mqtt_username) - 1);
            mqtt_config.username = mqtt_username;
        } else {
            mqtt_config.username = NULL;
        }
        if (strlen(mqtt_cfg.password) > 0) {
            strncpy(mqtt_password, mqtt_cfg.password, sizeof(mqtt_password) - 1);
            mqtt_config.password = mqtt_password;
        } else {
            mqtt_config.password = NULL;
        }
        mqtt_config.use_tls = mqtt_cfg.use_tls;
        ESP_LOGI(TAG, "MQTT config from storage: %s:%d", mqtt_cfg.host, mqtt_cfg.port);
    } else {
        // Default values
        strncpy(mqtt_host, "192.168.1.10", sizeof(mqtt_host) - 1);
        mqtt_config.host = mqtt_host;
        mqtt_config.port = 1883;
        mqtt_config.keepalive = 30;
        mqtt_config.client_id = NULL;
        mqtt_config.username = NULL;
        mqtt_config.password = NULL;
        mqtt_config.use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    // Get node_id from config
    if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
        node_info.node_uid = node_id;
        ph_node_set_node_id(node_id);
        ESP_LOGI(TAG, "Node ID from config: %s", node_id);
    } else {
        // Default value
        strncpy(node_id, "nd-ph-1", sizeof(node_id) - 1);
        ph_node_set_node_id(node_id);
        node_info.node_uid = node_id;
        ESP_LOGW(TAG, "Using default node ID");
    }
    
    // gh_uid and zone_uid are not stored in NodeConfig yet, use defaults
    // TODO: Add these fields to NodeConfig or get from another source
    node_info.gh_uid = default_gh_uid;
    node_info.zone_uid = default_zone_uid;
    
    err = mqtt_manager_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(err));
        return err;
    }
    
    // Register callbacks
    mqtt_manager_register_config_cb(ph_node_config_handler, NULL);
    mqtt_manager_register_command_cb(ph_node_command_handler, NULL);
    mqtt_manager_register_connection_cb(ph_node_mqtt_connection_cb, NULL);
    
    // Start MQTT client (will connect automatically after Wi-Fi connection)
    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return err;
    }
    
    ESP_LOGI(TAG, "All components initialized successfully");
    
    // Transition OLED UI to normal mode after initialization
    if (ph_node_is_oled_initialized()) {
        oled_ui_set_state(OLED_UI_STATE_NORMAL);
    }
    
    return ESP_OK;
}

