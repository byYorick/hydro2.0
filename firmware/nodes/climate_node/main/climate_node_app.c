/**
 * @file climate_node_app.c
 * @brief Основная логика climate_node
 * 
 * Климатическая нода для измерения температуры, влажности, CO₂ и управления
 * вентиляторами, нагревателями, освещением
 * Согласно NODE_ARCH_FULL.md и MQTT_SPEC_FULL.md
 */

#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "climate_node_app.h"
#include "climate_node_framework_integration.h"
#include "relay_driver.h"
#include "setup_portal.h"
#include "pwm_driver.h"
#include "i2c_bus.h"
#include "sht3x.h"
#include "ccs811.h"
#include "node_utils.h"
#include "esp_log.h"
#include "esp_err.h"
#include <string.h>

static const char *TAG = "climate_node";

// Forward declaration
static void on_wifi_connection_changed(bool connected, void *user_ctx);
static void on_mqtt_connection_changed(bool connected, void *user_ctx);

static void on_wifi_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "Wi-Fi connected");
    } else {
        ESP_LOGW(TAG, "Wi-Fi disconnected");
    }
}

static void on_mqtt_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - climate_node is online");
        
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
            const char *capabilities[] = {"temperature", "humidity", "co2", "lighting", "ventilation"};
            node_utils_publish_node_hello("climate", capabilities, 5);
        }
        
        // Запрашиваем время у сервера для синхронизации
        node_utils_request_time();
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - climate_node is offline");
    }
}

/**
 * @brief Инициализация climate_node
 */
void climate_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing climate_node...");
    
    // Инициализация config_storage
    esp_err_t err = config_storage_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize config storage: %s", esp_err_to_name(err));
        return;
    }
    
    // Попытка загрузить конфигурацию из NVS
    err = config_storage_load();
    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No config in NVS, using defaults. Waiting for config from MQTT...");
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load config from NVS: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "Using default values, waiting for config from MQTT...");
    }
    
    // Инициализация Wi-Fi менеджера
    err = wifi_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize Wi-Fi manager: %s", esp_err_to_name(err));
        return;
    }
    
    // Проверка наличия Wi-Fi конфига
    config_storage_wifi_t wifi_cfg;
    bool wifi_configured = (config_storage_get_wifi(&wifi_cfg) == ESP_OK) && 
                           (strlen(wifi_cfg.ssid) > 0);
    
    if (!wifi_configured) {
        ESP_LOGW(TAG, "WiFi config not found, starting setup mode...");
        setup_portal_full_config_t setup_config = {
            .node_type_prefix = "CLIMATE",
            .ap_password = "hydro2025",
            .enable_oled = false,
            .oled_user_ctx = NULL
        };
        // Эта функция блокирует выполнение до получения credentials и перезагрузки устройства
        setup_portal_run_full_setup(&setup_config);
        return; // Не должно быть достигнуто, так как setup_portal перезагружает устройство
    }
    
    wifi_manager_register_connection_cb(on_wifi_connection_changed, NULL);
    
    // Подключение к Wi-Fi
    wifi_manager_config_t wifi_config;
    static char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
    static char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
    
    strncpy(wifi_ssid, wifi_cfg.ssid, sizeof(wifi_ssid) - 1);
    wifi_ssid[sizeof(wifi_ssid) - 1] = '\0';  // Гарантируем null-termination
    strncpy(wifi_password, wifi_cfg.password, sizeof(wifi_password) - 1);
    wifi_password[sizeof(wifi_password) - 1] = '\0';  // Гарантируем null-termination
    wifi_config.ssid = wifi_ssid;
    wifi_config.password = wifi_password;
    ESP_LOGI(TAG, "Connecting to Wi-Fi from config: %s", wifi_cfg.ssid);
    
    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect to Wi-Fi: %s", esp_err_to_name(err));
    }
    
    // Инициализация MQTT клиента
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
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';  // Гарантируем null-termination
        mqtt_config.host = mqtt_host;
        mqtt_config.port = mqtt_cfg.port;
        mqtt_config.keepalive = mqtt_cfg.keepalive;
        mqtt_config.client_id = NULL;
        if (strlen(mqtt_cfg.username) > 0) {
            strncpy(mqtt_username, mqtt_cfg.username, sizeof(mqtt_username) - 1);
            mqtt_username[sizeof(mqtt_username) - 1] = '\0';  // Гарантируем null-termination
            mqtt_config.username = mqtt_username;
        } else {
            mqtt_config.username = NULL;
        }
        if (strlen(mqtt_cfg.password) > 0) {
            strncpy(mqtt_password, mqtt_cfg.password, sizeof(mqtt_password) - 1);
            mqtt_password[sizeof(mqtt_password) - 1] = '\0';  // Гарантируем null-termination
            mqtt_config.password = mqtt_password;
        } else {
            mqtt_config.password = NULL;
        }
        mqtt_config.use_tls = mqtt_cfg.use_tls;
        ESP_LOGI(TAG, "MQTT config from storage: %s:%d", mqtt_cfg.host, mqtt_cfg.port);
    } else {
        strncpy(mqtt_host, "192.168.1.10", sizeof(mqtt_host) - 1);
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';  // Гарантируем null-termination
        mqtt_config.host = mqtt_host;
        mqtt_config.port = 1883;
        mqtt_config.keepalive = 30;
        mqtt_config.client_id = NULL;
        mqtt_config.username = NULL;
        mqtt_config.password = NULL;
        mqtt_config.use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
        node_info.node_uid = node_id;
        ESP_LOGI(TAG, "Node ID from config: %s", node_id);
    } else {
        strncpy(node_id, "nd-climate-1", sizeof(node_id) - 1);
        node_id[sizeof(node_id) - 1] = '\0';  // Гарантируем null-termination
        node_info.node_uid = node_id;
        ESP_LOGW(TAG, "Using default node ID");
    }
    
    // Get gh_uid and zone_uid from NodeConfig
    static char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    static char zone_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    if (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK) {
        node_info.gh_uid = gh_uid;
        ESP_LOGI(TAG, "GH UID from config: %s", gh_uid);
    } else {
        node_info.gh_uid = default_gh_uid;
        ESP_LOGW(TAG, "GH UID not found in config, using default: %s", default_gh_uid);
    }
    
    if (config_storage_get_zone_uid(zone_uid, sizeof(zone_uid)) == ESP_OK) {
        node_info.zone_uid = zone_uid;
        ESP_LOGI(TAG, "Zone UID from config: %s", zone_uid);
    } else {
        node_info.zone_uid = default_zone_uid;
        ESP_LOGW(TAG, "Zone UID not found in config, using default: %s", default_zone_uid);
    }
    
    err = mqtt_manager_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    // Инициализация node_framework и регистрация MQTT обработчиков
    esp_err_t fw_err = climate_node_framework_init_integration();
    if (fw_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize node_framework: %s", esp_err_to_name(fw_err));
        return;
    }
    
    climate_node_framework_register_mqtt_handlers();
    
    // Регистрация callback для публикации node_hello при подключении MQTT
    mqtt_manager_register_connection_cb(on_mqtt_connection_changed, NULL);
    
    // Запуск MQTT клиента
    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    // Инициализация relay_driver из NodeConfig
    err = relay_driver_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Relay driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No relay channels found in config, relay driver not initialized");
    } else {
        ESP_LOGE(TAG, "Failed to initialize relay driver: %s", esp_err_to_name(err));
    }

    err = pwm_driver_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "PWM driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No PWM channels found in config");
    } else {
        ESP_LOGE(TAG, "Failed to initialize PWM driver: %s", esp_err_to_name(err));
    }

    // Инициализация I²C шины (если еще не инициализирована)
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGI(TAG, "Initializing I²C bus 1...");
        i2c_bus_config_t i2c_config = {
            .sda_pin = 21,
            .scl_pin = 22,
            .clock_speed = 100000,
            .pullup_enable = true
        };
        err = i2c_bus_init_bus(I2C_BUS_1, &i2c_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize I²C bus 1: %s", esp_err_to_name(err));
            // Продолжаем работу, возможно I²C не нужен
        } else {
            ESP_LOGI(TAG, "I²C bus 1 initialized: SDA=%d, SCL=%d", i2c_config.sda_pin, i2c_config.scl_pin);
        }
    }
    
    // Инициализация SHT3x сенсора (температура/влажность)
    if (i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGI(TAG, "Initializing SHT3x sensor...");
        sht3x_config_t sht_config = {
            .i2c_address = 0x44  // Адрес по умолчанию для SHT3x
        };
        err = sht3x_init(&sht_config);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "SHT3x sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize SHT3x sensor: %s (will retry later)", esp_err_to_name(err));
        }
    } else {
        ESP_LOGW(TAG, "I²C bus 1 not available, SHT3x sensor initialization skipped");
    }
    
    // Инициализация CCS811 сенсора (CO₂/TVOC)
    if (i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGI(TAG, "Initializing CCS811 sensor...");
        ccs811_config_t ccs_config = {
            .i2c_address = CCS811_I2C_ADDR_DEFAULT,
            .i2c_bus = I2C_BUS_1,
            .measurement_mode = CCS811_MEAS_MODE_1SEC,
            .measurement_interval_ms = 1000
        };
        err = ccs811_init(&ccs_config);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "CCS811 sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize CCS811 sensor: %s (will use stub values)", esp_err_to_name(err));
        }
    } else {
        ESP_LOGW(TAG, "I²C bus 1 not available, CCS811 sensor initialization skipped");
    }

    ESP_LOGI(TAG, "climate_node initialized");

    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    climate_node_start_tasks();
}
