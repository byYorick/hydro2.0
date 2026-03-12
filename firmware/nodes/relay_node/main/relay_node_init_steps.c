/**
 * @file relay_node_init_steps.c
 * @brief Реализация модульных шагов инициализации relay_node
 * 
 * Каждый шаг инициализации вынесен в отдельную функцию,
 * что позволяет:
 * - Легко тестировать отдельные компоненты
 * - Повторно применять шаги при обновлении конфигурации
 * - Упростить отладку и логирование
 */

#include "relay_node_init_steps.h"
#include "relay_node_defaults.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "oled_ui.h"
#include "relay_driver.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "relay_node_init_steps";

// Вспомогательная функция для получения значения из config_storage с дефолтом
static esp_err_t get_config_string(const char *key, char *buffer, size_t buffer_size, const char *default_value) {
    esp_err_t err = ESP_ERR_NOT_FOUND;
    
    if (strcmp(key, "node_id") == 0) {
        err = config_storage_get_node_id(buffer, buffer_size);
    } else if (strcmp(key, "gh_uid") == 0) {
        err = config_storage_get_gh_uid(buffer, buffer_size);
    } else if (strcmp(key, "zone_uid") == 0) {
        err = config_storage_get_zone_uid(buffer, buffer_size);
    }
    
    if (err != ESP_OK && default_value) {
        strncpy(buffer, default_value, buffer_size - 1);
        buffer[buffer_size - 1] = '\0';
        return ESP_OK;
    }
    
    return err;
}

esp_err_t relay_node_init_step_config_storage(relay_node_init_context_t *ctx, 
                                           relay_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 1/7] Loading config...");
    
    if (result) {
        result->component_name = "config_storage";
        result->component_initialized = false;
    }
    
    esp_err_t err = config_storage_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize config storage: %s", esp_err_to_name(err));
        if (result) result->err = err;
        return err;
    }
    
    err = config_storage_load();
    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No config in NVS, using defaults. Waiting for config from MQTT...");
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to load config from NVS: %s", esp_err_to_name(err));
        ESP_LOGW(TAG, "Using default values, waiting for config from MQTT...");
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t relay_node_init_step_wifi(relay_node_init_context_t *ctx,
                                  relay_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 2/7] Wi-Fi manager init...");
    
    if (result) {
        result->component_name = "wifi_manager";
        result->component_initialized = false;
    }
    
    esp_err_t err = wifi_manager_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize Wi-Fi manager: %s", esp_err_to_name(err));
        if (result) result->err = err;
        return err;
    }
    
    // Проверка конфигурации WiFi
    config_storage_wifi_t wifi_cfg;
    bool wifi_configured = (config_storage_get_wifi(&wifi_cfg) == ESP_OK) && 
                           (strlen(wifi_cfg.ssid) > 0);
    
    if (!wifi_configured) {
        ESP_LOGW(TAG, "WiFi config not found, setup mode will be triggered");
        if (result) {
            result->err = ESP_ERR_NOT_FOUND;
            result->component_initialized = false;
        }
        return ESP_ERR_NOT_FOUND;
    }
    
    // Подключение к WiFi будет выполнено позже, после проверки setup mode
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t relay_node_init_step_i2c(relay_node_init_context_t *ctx,
                                 relay_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 3/7] I2C init...");
    
    if (result) {
        result->component_name = "i2c_bus";
        result->component_initialized = false;
    }
    
    esp_err_t err = ESP_OK;
    
    // Инициализация I2C 0 для OLED (если используется)
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGI(TAG, "Initializing I2C bus 0 (OLED)...");
        i2c_bus_config_t i2c0_config = {
            .sda_pin = RELAY_NODE_I2C_BUS_0_SDA,
            .scl_pin = RELAY_NODE_I2C_BUS_0_SCL,
            .clock_speed = RELAY_NODE_I2C_CLOCK_SPEED,
            .pullup_enable = true
        };
        err = i2c_bus_init_bus(I2C_BUS_0, &i2c0_config);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to initialize I2C bus 0: %s (OLED may not be available)", esp_err_to_name(err));
            // Continue - I2C может быть не критичен
        } else {
            ESP_LOGI(TAG, "I2C bus 0 initialized: SDA=%d, SCL=%d", 
                     i2c0_config.sda_pin, i2c0_config.scl_pin);
        }
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t relay_node_init_step_oled(relay_node_init_context_t *ctx,
                                  relay_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 4/7] OLED UI init...");
    
    if (result) {
        result->component_name = "oled_ui";
        result->component_initialized = false;
    }
    
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGW(TAG, "I2C bus 0 not initialized, cannot initialize OLED");
        if (result) {
            result->err = ESP_ERR_INVALID_STATE;
        }
        return ESP_ERR_INVALID_STATE;
    }
    
    // Получаем node_id из config_storage или используем дефолт
    char node_id[64];
    get_config_string("node_id", node_id, sizeof(node_id), RELAY_NODE_DEFAULT_NODE_ID);
    ESP_LOGI(TAG, "Node ID for OLED: %s", node_id);
    
    oled_ui_config_t oled_config = {
        .i2c_address = RELAY_NODE_OLED_I2C_ADDRESS,
        .update_interval_ms = RELAY_NODE_OLED_UPDATE_INTERVAL_MS,
        .enable_task = true
    };
    
    esp_err_t err = oled_ui_init(OLED_UI_NODE_TYPE_UNKNOWN, node_id, &oled_config);
    if (err == ESP_OK) {
        err = oled_ui_set_state(OLED_UI_STATE_BOOT);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(err));
        }
        
        // Показываем предыдущие шаги, если OLED уже инициализирован
        if (ctx && ctx->show_oled_steps) {
            oled_ui_show_init_step(3, "I2C init");
            vTaskDelay(pdMS_TO_TICKS(200));
            oled_ui_show_init_step(4, "OLED UI init");
        }
        
        ESP_LOGI(TAG, "OLED UI initialized successfully");
        if (result) {
            result->err = ESP_OK;
            result->component_initialized = true;
        }
    } else {
        ESP_LOGW(TAG, "Failed to initialize OLED UI: %s (OLED may not be available)", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
    }
    
    return err;
}

esp_err_t relay_node_init_step_relays(relay_node_init_context_t *ctx,
                                   relay_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 5/7] Relays init...");
    
    if (result) {
        result->component_name = "relay_driver";
        result->component_initialized = false;
    }
    
    esp_err_t err = relay_driver_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Relay driver initialized successfully from config");
        if (result) {
            result->err = ESP_OK;
            result->component_initialized = true;
        }
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No relay channels found in config, relays will be initialized when config received");
        if (result) {
            result->err = ESP_ERR_NOT_FOUND;
        }
    } else {
        ESP_LOGE(TAG, "Failed to initialize relay driver: %s", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
    }
    
    return err;
}

esp_err_t relay_node_init_step_mqtt(relay_node_init_context_t *ctx,
                                 relay_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 6/7] MQTT init...");
    
    if (result) {
        result->component_name = "mqtt_manager";
        result->component_initialized = false;
    }
    
    // Загрузка конфигурации MQTT
    config_storage_mqtt_t mqtt_cfg;
    mqtt_manager_config_t mqtt_config;
    mqtt_node_info_t node_info;
    
    static char mqtt_host[CONFIG_STORAGE_MAX_STRING_LEN];
    static char mqtt_username[CONFIG_STORAGE_MAX_STRING_LEN];
    static char mqtt_password[CONFIG_STORAGE_MAX_STRING_LEN];
    static char node_id[64];
    static char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    static char zone_uid[CONFIG_STORAGE_MAX_STRING_LEN];
    
    if (config_storage_get_mqtt(&mqtt_cfg) == ESP_OK) {
        strncpy(mqtt_host, mqtt_cfg.host, sizeof(mqtt_host) - 1);
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';
        mqtt_config.host = mqtt_host;
        mqtt_config.port = mqtt_cfg.port;
        mqtt_config.keepalive = mqtt_cfg.keepalive;
        mqtt_config.client_id = NULL;
        if (strlen(mqtt_cfg.username) > 0) {
            strncpy(mqtt_username, mqtt_cfg.username, sizeof(mqtt_username) - 1);
            mqtt_username[sizeof(mqtt_username) - 1] = '\0';
            mqtt_config.username = mqtt_username;
        } else {
            mqtt_config.username = NULL;
        }
        if (strlen(mqtt_cfg.password) > 0) {
            strncpy(mqtt_password, mqtt_cfg.password, sizeof(mqtt_password) - 1);
            mqtt_password[sizeof(mqtt_password) - 1] = '\0';
            mqtt_config.password = mqtt_password;
        } else {
            mqtt_config.password = NULL;
        }
        mqtt_config.use_tls = mqtt_cfg.use_tls;
        ESP_LOGI(TAG, "MQTT config from storage: %s:%d", mqtt_cfg.host, mqtt_cfg.port);
    } else {
        // Default values из relay_node_defaults.h
        strncpy(mqtt_host, RELAY_NODE_DEFAULT_MQTT_HOST, sizeof(mqtt_host) - 1);
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';
        mqtt_config.host = mqtt_host;
        mqtt_config.port = RELAY_NODE_DEFAULT_MQTT_PORT;
        mqtt_config.keepalive = RELAY_NODE_DEFAULT_MQTT_KEEPALIVE;
        mqtt_config.client_id = NULL;
        mqtt_config.username = NULL;
        mqtt_config.password = NULL;
        mqtt_config.use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    // Получение node_id, gh_uid, zone_uid
    get_config_string("node_id", node_id, sizeof(node_id), RELAY_NODE_DEFAULT_NODE_ID);
    get_config_string("gh_uid", gh_uid, sizeof(gh_uid), RELAY_NODE_DEFAULT_GH_UID);
    get_config_string("zone_uid", zone_uid, sizeof(zone_uid), RELAY_NODE_DEFAULT_ZONE_UID);
    
    node_info.node_uid = node_id;
    node_info.gh_uid = gh_uid;
    node_info.zone_uid = zone_uid;
    
    esp_err_t err = mqtt_manager_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
        return err;
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t relay_node_init_step_finalize(relay_node_init_context_t *ctx,
                                      relay_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 7/7] Starting...");
    
    if (result) {
        result->component_name = "finalize";
        result->component_initialized = true;
    }
    
    // Запускаем MQTT после регистрации callbacks (которые происходят в relay_node_init.c)
    esp_err_t err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
        return err;
    }
    ESP_LOGI(TAG, "MQTT client started (callbacks already registered)");
    
    // Останавливаем анимацию шагов инициализации
    if (ctx && ctx->show_oled_steps && oled_ui_is_initialized()) {
        oled_ui_stop_init_steps();
        oled_ui_set_state(OLED_UI_STATE_NORMAL);
    }
    
    ESP_LOGI(TAG, "All components initialized successfully");
    
    if (result) {
        result->err = ESP_OK;
    }
    
    return ESP_OK;
}

