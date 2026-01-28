/**
 * @file light_node_init_steps.c
 * @brief Реализация модульных шагов инициализации light_node
 * 
 * Каждый шаг инициализации вынесен в отдельную функцию,
 * что позволяет:
 * - Легко тестировать отдельные компоненты
 * - Повторно применять шаги при обновлении конфигурации
 * - Упростить отладку и логирование
 */

#include "light_node_init_steps.h"
#include "light_node_defaults.h"
#include "light_node_channel_map.h"
#include "light_node_config_utils.h"
#include "init_steps_utils.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "trema_light.h"
#include "oled_ui.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "light_node_init_steps";

static void light_node_patch_config_task(void *pvParameters);

esp_err_t light_node_init_step_config_storage(light_node_init_context_t *ctx, 
                                              light_node_init_step_result_t *result) {
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
    if (xTaskCreate(light_node_patch_config_task, "light_cfg_patch", 8192, NULL, 4, NULL) != pdPASS) {
        ESP_LOGW(TAG, "Failed to start config patch task");
    }
    
    return ESP_OK;
}

static void light_node_patch_config_task(void *pvParameters) {
    (void)pvParameters;

    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        vTaskDelete(NULL);
        return;
    }

    bool changed = false;
    char *patched = light_node_build_patched_config(config_json, strlen(config_json), false, &changed);
    if (!patched) {
        if (changed) {
            ESP_LOGW(TAG, "Failed to build patched config");
        }
        vTaskDelete(NULL);
        return;
    }

    esp_err_t patch_err = config_storage_save(patched, strlen(patched));
    free(patched);
    if (patch_err == ESP_OK) {
        ESP_LOGI(TAG, "Config patched with firmware channels");
    } else if (patch_err != ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to patch config: %s", esp_err_to_name(patch_err));
    }

    vTaskDelete(NULL);
}

esp_err_t light_node_init_step_wifi(light_node_init_context_t *ctx,
                                     light_node_init_step_result_t *result) {
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

esp_err_t light_node_init_step_i2c(light_node_init_context_t *ctx,
                                    light_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 3/7] I2C init...");
    
    if (result) {
        result->component_name = "i2c_bus";
        result->component_initialized = false;
    }
    
    esp_err_t err = ESP_OK;
    
    // Инициализация I2C 0 для OLED и датчика света (на одной шине)
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGI(TAG, "Initializing I2C bus 0 (OLED + light sensor)...");
        i2c_bus_config_t i2c0_config = {
            .sda_pin = LIGHT_NODE_I2C_BUS_0_SDA,
            .scl_pin = LIGHT_NODE_I2C_BUS_0_SCL,
            .clock_speed = LIGHT_NODE_I2C_CLOCK_SPEED,
            .pullup_enable = true
        };
        err = i2c_bus_init_bus(I2C_BUS_0, &i2c0_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize I2C bus 0: %s", esp_err_to_name(err));
            if (result) result->err = err;
            return err;
        }
        ESP_LOGI(TAG, "I2C bus 0 initialized: SDA=GPIO%d, SCL=GPIO%d", 
                 i2c0_config.sda_pin, i2c0_config.scl_pin);
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t light_node_init_step_light_sensor(light_node_init_context_t *ctx,
                                             light_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 4/7] Light sensor init...");
    
    if (result) {
        result->component_name = "light_sensor";
        result->component_initialized = false;
    }
    
    // Датчик света на I2C_BUS_0 (та же шина, что и OLED)
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGW(TAG, "I2C bus 0 not available, light sensor initialization skipped");
        if (result) {
            result->err = ESP_ERR_INVALID_STATE;
        }
        return ESP_ERR_INVALID_STATE;
    }
    
    // Инициализация датчика света Trema
    ESP_LOGI(TAG, "Attempting to initialize Trema light sensor on I2C_BUS_0, address 0x%02X", TREMA_LIGHT_ADDR);
    bool init_success = trema_light_init(I2C_BUS_0);
    if (init_success) {
        ESP_LOGI(TAG, "Trema light sensor initialized successfully on I2C_BUS_0, address 0x%02X", TREMA_LIGHT_ADDR);
    } else {
        ESP_LOGW(TAG, "Failed to initialize Trema light sensor at address 0x%02X: will retry later (will use stub values)", TREMA_LIGHT_ADDR);
    }
    
    // Датчик не критичен, продолжаем инициализацию даже при ошибке
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t light_node_init_step_oled(light_node_init_context_t *ctx,
                                    light_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 5/7] OLED UI init...");
    
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
    char node_id[CONFIG_STORAGE_MAX_STRING_LEN];
    init_steps_utils_get_config_string("node_id", node_id, sizeof(node_id), LIGHT_NODE_DEFAULT_NODE_ID);
    ESP_LOGI(TAG, "Node ID for OLED: %s", node_id);
    
    oled_ui_config_t oled_config = {
        .i2c_address = LIGHT_NODE_OLED_I2C_ADDRESS,
        .update_interval_ms = LIGHT_NODE_OLED_UPDATE_INTERVAL_MS,
        .enable_task = true
    };
    
    esp_err_t err = oled_ui_init(OLED_UI_NODE_TYPE_LIGHTING, node_id, &oled_config);
    if (err == ESP_OK) {
        err = oled_ui_set_state(OLED_UI_STATE_BOOT);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(err));
        }
        
        // Показываем предыдущие шаги, если OLED уже инициализирован
        if (ctx && ctx->show_oled_steps) {
            oled_ui_show_init_step(3, "I2C init");
            vTaskDelay(pdMS_TO_TICKS(200));
            oled_ui_show_init_step(4, "Light sensor init");
            vTaskDelay(pdMS_TO_TICKS(200));
            oled_ui_show_init_step(5, "OLED UI init");
        }
        
        ESP_LOGI(TAG, "OLED UI initialized successfully");
        if (result) {
            result->err = ESP_OK;
            result->component_initialized = true;
        }
    } else {
        ESP_LOGE(TAG, "Failed to initialize OLED UI: %s", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
    }
    
    return err;
}

esp_err_t light_node_init_step_mqtt(light_node_init_context_t *ctx,
                                     light_node_init_step_result_t *result) {
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
    static char node_id[CONFIG_STORAGE_MAX_STRING_LEN];
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
        // Default values из light_node_defaults.h
        strncpy(mqtt_host, LIGHT_NODE_DEFAULT_MQTT_HOST, sizeof(mqtt_host) - 1);
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';
        mqtt_config.host = mqtt_host;
        mqtt_config.port = LIGHT_NODE_DEFAULT_MQTT_PORT;
        mqtt_config.keepalive = LIGHT_NODE_DEFAULT_MQTT_KEEPALIVE;
        mqtt_config.client_id = NULL;
        mqtt_config.username = NULL;
        mqtt_config.password = NULL;
        mqtt_config.use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    // Получение node_id, gh_uid, zone_uid
    init_steps_utils_get_config_string("node_id", node_id, sizeof(node_id), LIGHT_NODE_DEFAULT_NODE_ID);
    init_steps_utils_get_config_string("gh_uid", gh_uid, sizeof(gh_uid), LIGHT_NODE_DEFAULT_GH_UID);
    init_steps_utils_get_config_string("zone_uid", zone_uid, sizeof(zone_uid), LIGHT_NODE_DEFAULT_ZONE_UID);
    
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
    
    // Callbacks будут зарегистрированы в light_node_init.c перед light_node_init_step_finalize
    // MQTT старт перенесен в light_node_init_step_finalize, чтобы callbacks были зарегистрированы до старта
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t light_node_init_step_finalize(light_node_init_context_t *ctx,
                                         light_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 7/7] Starting...");
    
    if (result) {
        result->component_name = "finalize";
        result->component_initialized = true;
    }
    
    // Запускаем MQTT после регистрации callbacks (которые происходят в light_node_init.c)
    // Это гарантирует, что ранние входящие команды/config не будут дропнуты
    esp_err_t err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        if (result) {
            result->err = err;
        }
        return err;
    }
    ESP_LOGI(TAG, "MQTT client started (callbacks already registered)");
    
    // Останавливаем анимацию шагов инициализации и переводим OLED в нормальный режим
    if (oled_ui_is_initialized()) {
        if (ctx && ctx->show_oled_steps) {
            oled_ui_stop_init_steps();
        }
        // Всегда переводим OLED в нормальный режим после инициализации
        esp_err_t oled_err = oled_ui_set_state(OLED_UI_STATE_NORMAL);
        if (oled_err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set OLED state to NORMAL: %s", esp_err_to_name(oled_err));
        } else {
            ESP_LOGI(TAG, "OLED UI set to NORMAL state");
        }
    }
    
    ESP_LOGI(TAG, "All components initialized successfully");
    
    if (result) {
        result->err = ESP_OK;
    }
    
    return ESP_OK;
}
