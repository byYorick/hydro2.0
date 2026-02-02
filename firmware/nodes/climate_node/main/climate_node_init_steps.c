/**
 * @file climate_node_init_steps.c
 * @brief Реализация модульных шагов инициализации climate_node
 * 
 * Каждый шаг инициализации вынесен в отдельную функцию,
 * что позволяет:
 * - Легко тестировать отдельные компоненты
 * - Повторно применять шаги при обновлении конфигурации
 * - Упростить отладку и логирование
 */

#include "climate_node_init_steps.h"
#include "climate_node_defaults.h"
#include "init_steps_utils.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "i2c_bus.h"
#include "sht3x.h"
#include "ccs811.h"
#include "oled_ui.h"
#include "relay_driver.h"
#include "pwm_driver.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_err.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "climate_node_init_steps";

static void climate_node_patch_config_task(void *pvParameters);

static bool climate_node_has_channel_name(const cJSON *channels, const char *name) {
    if (!channels || !name || !cJSON_IsArray(channels)) {
        return false;
    }

    const int count = cJSON_GetArraySize(channels);
    for (int i = 0; i < count; i++) {
        const cJSON *entry = cJSON_GetArrayItem(channels, i);
        if (!entry || !cJSON_IsObject(entry)) {
            continue;
        }
        const cJSON *entry_name = cJSON_GetObjectItem(entry, "name");
        if (cJSON_IsString(entry_name) && entry_name->valuestring &&
            strcmp(entry_name->valuestring, name) == 0) {
            return true;
        }
    }

    return false;
}

static bool climate_node_add_sensor_channel(
    cJSON *channels,
    const char *name,
    const char *metric,
    int poll_interval_ms,
    const char *unit,
    int precision
) {
    if (!channels || !cJSON_IsArray(channels) || !name || !metric) {
        return false;
    }

    cJSON *entry = cJSON_CreateObject();
    if (!entry) {
        return false;
    }

    cJSON_AddStringToObject(entry, "name", name);
    cJSON_AddStringToObject(entry, "type", "SENSOR");
    cJSON_AddStringToObject(entry, "metric", metric);
    cJSON_AddNumberToObject(entry, "poll_interval_ms", poll_interval_ms);
    if (unit && unit[0] != '\0') {
        cJSON_AddStringToObject(entry, "unit", unit);
    }
    cJSON_AddNumberToObject(entry, "precision", precision);

    if (!cJSON_AddItemToArray(channels, entry)) {
        cJSON_Delete(entry);
        return false;
    }

    return true;
}

esp_err_t climate_node_init_step_config_storage(climate_node_init_context_t *ctx, 
                                                climate_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 1/8] Loading config...");
    
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

    if (xTaskCreate(climate_node_patch_config_task, "climate_cfg_patch", 8192, NULL, 4, NULL) != pdPASS) {
        ESP_LOGW(TAG, "Failed to start config patch task");
    }
    
    return ESP_OK;
}

static void climate_node_patch_config_task(void *pvParameters) {
    (void)pvParameters;

    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(config_json, sizeof(config_json)) != ESP_OK) {
        vTaskDelete(NULL);
        return;
    }

    cJSON *config = cJSON_Parse(config_json);
    if (!config) {
        vTaskDelete(NULL);
        return;
    }

    bool changed = false;
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    if (channels == NULL || !cJSON_IsArray(channels)) {
        if (channels) {
            cJSON_DeleteItemFromObject(config, "channels");
        }
        channels = cJSON_CreateArray();
        if (!channels) {
            cJSON_Delete(config);
            vTaskDelete(NULL);
            return;
        }
        cJSON_AddItemToObject(config, "channels", channels);
        changed = true;
    }

    if (!climate_node_has_channel_name(channels, "temperature")) {
        if (!climate_node_add_sensor_channel(channels, "temperature", "TEMPERATURE", 5000, "°C", 1)) {
            cJSON_Delete(config);
            vTaskDelete(NULL);
            return;
        }
        changed = true;
    }

    if (!climate_node_has_channel_name(channels, "humidity")) {
        if (!climate_node_add_sensor_channel(channels, "humidity", "HUMIDITY", 5000, "%", 1)) {
            cJSON_Delete(config);
            vTaskDelete(NULL);
            return;
        }
        changed = true;
    }

    if (!climate_node_has_channel_name(channels, "co2")) {
        if (!climate_node_add_sensor_channel(channels, "co2", "CO2", 10000, "ppm", 0)) {
            cJSON_Delete(config);
            vTaskDelete(NULL);
            return;
        }
        changed = true;
    }

    if (!changed) {
        cJSON_Delete(config);
        vTaskDelete(NULL);
        return;
    }

    char *patched = cJSON_PrintUnformatted(config);
    cJSON_Delete(config);
    if (!patched) {
        vTaskDelete(NULL);
        return;
    }

    esp_err_t patch_err = config_storage_save(patched, strlen(patched));
    free(patched);
    if (patch_err == ESP_OK) {
        ESP_LOGI(TAG, "Config patched with climate sensor channels");
    } else if (patch_err != ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to patch config: %s", esp_err_to_name(patch_err));
    }

    vTaskDelete(NULL);
}

esp_err_t climate_node_init_step_wifi(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 2/8] Wi-Fi manager init...");
    
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

esp_err_t climate_node_init_step_i2c(climate_node_init_context_t *ctx,
                                     climate_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 3/8] I2C init...");
    
    if (result) {
        result->component_name = "i2c_bus";
        result->component_initialized = false;
    }
    
    esp_err_t err = ESP_OK;
    
    // Инициализация I2C 0 для OLED
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGI(TAG, "Initializing I2C bus 0 (OLED)...");
        i2c_bus_config_t i2c0_config = {
            .sda_pin = CLIMATE_NODE_I2C_BUS_0_SDA,
            .scl_pin = CLIMATE_NODE_I2C_BUS_0_SCL,
            .clock_speed = CLIMATE_NODE_I2C_CLOCK_SPEED,
            .pullup_enable = true
        };
        err = i2c_bus_init_bus(I2C_BUS_0, &i2c0_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize I2C bus 0: %s", esp_err_to_name(err));
            if (result) result->err = err;
            return err;
        }
        ESP_LOGI(TAG, "I2C bus 0 initialized: SDA=%d, SCL=%d", 
                 i2c0_config.sda_pin, i2c0_config.scl_pin);
    }
    
    // Инициализация I2C 1 для SHT3x
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGI(TAG, "Initializing I2C bus 1 for SHT3x (GPIO %d SDA, GPIO %d SCL)...", 
                CLIMATE_NODE_I2C_BUS_1_SDA, CLIMATE_NODE_I2C_BUS_1_SCL);
        i2c_bus_config_t i2c1_config = {
            .sda_pin = CLIMATE_NODE_I2C_BUS_1_SDA,
            .scl_pin = CLIMATE_NODE_I2C_BUS_1_SCL,
            .clock_speed = CLIMATE_NODE_I2C_CLOCK_SPEED,
            .pullup_enable = true
        };
        err = i2c_bus_init_bus(I2C_BUS_1, &i2c1_config);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize I2C bus 1: %s", esp_err_to_name(err));
            if (result) result->err = err;
            // Не критично, продолжаем
        } else {
            ESP_LOGI(TAG, "I2C bus 1 initialized successfully: SDA=GPIO%d, SCL=GPIO%d", 
                     i2c1_config.sda_pin, i2c1_config.scl_pin);
        }
    } else {
        ESP_LOGI(TAG, "I2C bus 1 already initialized");
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t climate_node_init_step_sensors(climate_node_init_context_t *ctx,
                                         climate_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 4/8] Sensors init...");
    
    if (result) {
        result->component_name = "sensors";
        result->component_initialized = false;
    }
    
    esp_err_t err = ESP_OK;
    
    // Инициализация SHT3x сенсора (температура/влажность) на I2C_BUS_1
    if (!i2c_bus_is_initialized_bus(I2C_BUS_1)) {
        ESP_LOGW(TAG, "I2C bus 1 not available, SHT3x sensor initialization skipped");
    } else {
        ESP_LOGI(TAG, "Initializing SHT3x sensor on I2C_BUS_1...");
        sht3x_config_t sht_config = {
            .i2c_address = 0x44,  // Адрес по умолчанию для SHT3x
            .i2c_bus = I2C_BUS_1  // Используем I2C_BUS_1 (GPIO 25 SDA, GPIO 26 SCL)
        };
        err = sht3x_init(&sht_config);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "SHT3x sensor initialized successfully on I2C_BUS_1 (GPIO 25 SDA, GPIO 26 SCL), address=0x%02X", 
                    sht_config.i2c_address);
        } else {
            ESP_LOGE(TAG, "Failed to initialize SHT3x sensor: %s (will retry later)", esp_err_to_name(err));
        }
    }
    
    // Инициализация CCS811 сенсора (CO₂/TVOC) на I2C_BUS_0
    if (!i2c_bus_is_initialized_bus(I2C_BUS_0)) {
        ESP_LOGW(TAG, "I2C bus 0 not available, CCS811 sensor initialization skipped");
    } else {
        ESP_LOGI(TAG, "Initializing CCS811 sensor on I2C_BUS_0...");
        ccs811_config_t ccs_config = {
            .i2c_address = CCS811_I2C_ADDR_DEFAULT,
            .i2c_bus = I2C_BUS_0,
            .measurement_mode = CCS811_MEAS_MODE_1SEC,
            .measurement_interval_ms = 1000
        };
        err = ccs811_init(&ccs_config);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "CCS811 sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize CCS811 sensor: %s (will use stub values)", esp_err_to_name(err));
        }
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t climate_node_init_step_oled(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 5/8] OLED UI init...");
    
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
    init_steps_utils_get_config_string("node_id", node_id, sizeof(node_id), CLIMATE_NODE_DEFAULT_NODE_ID);
    ESP_LOGI(TAG, "Node ID for OLED: %s", node_id);
    
    oled_ui_config_t oled_config = {
        .i2c_address = CLIMATE_NODE_OLED_I2C_ADDRESS,
        .update_interval_ms = CLIMATE_NODE_OLED_UPDATE_INTERVAL_MS,
        .enable_task = true
    };
    
    esp_err_t err = oled_ui_init(OLED_UI_NODE_TYPE_CLIMATE, node_id, &oled_config);
    if (err == ESP_OK) {
        err = oled_ui_set_state(OLED_UI_STATE_BOOT);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(err));
        }
        
        // Показываем предыдущие шаги, если OLED уже инициализирован
        if (ctx && ctx->show_oled_steps) {
            oled_ui_show_init_step(3, "I2C init");
            vTaskDelay(pdMS_TO_TICKS(200));
            oled_ui_show_init_step(4, "Sensors init");
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

esp_err_t climate_node_init_step_actuators(climate_node_init_context_t *ctx,
                                           climate_node_init_step_result_t *result) {
    (void)ctx;
    // КРИТИЧНО: Упрощаем логирование для предотвращения паники
    // ESP_LOGI(TAG, "[Step 6/8] Actuators init...");
    
    if (result) {
        result->component_name = "actuators";
        result->component_initialized = false;
    }
    
    esp_err_t err = ESP_OK;
    
    // Инициализация relay_driver из NodeConfig
    err = relay_driver_init_from_config();
    if (err == ESP_OK) {
        // ESP_LOGI(TAG, "Relay driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No relay channels found in config, relay driver not initialized");
    } else {
        ESP_LOGE(TAG, "Failed to initialize relay driver: %s", esp_err_to_name(err));
    }
    
    // Инициализация pwm_driver из NodeConfig
    err = pwm_driver_init_from_config();
    if (err == ESP_OK) {
        // ESP_LOGI(TAG, "PWM driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No PWM channels found in config");
    } else {
        ESP_LOGE(TAG, "Failed to initialize PWM driver: %s", esp_err_to_name(err));
    }
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t climate_node_init_step_mqtt(climate_node_init_context_t *ctx,
                                      climate_node_init_step_result_t *result) {
    (void)ctx;
    ESP_LOGI(TAG, "[Step 7/8] MQTT init...");
    
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
        // Default values из climate_node_defaults.h
        strncpy(mqtt_host, CLIMATE_NODE_DEFAULT_MQTT_HOST, sizeof(mqtt_host) - 1);
        mqtt_host[sizeof(mqtt_host) - 1] = '\0';
        mqtt_config.host = mqtt_host;
        mqtt_config.port = CLIMATE_NODE_DEFAULT_MQTT_PORT;
        mqtt_config.keepalive = CLIMATE_NODE_DEFAULT_MQTT_KEEPALIVE;
        mqtt_config.client_id = NULL;
        mqtt_config.username = NULL;
        mqtt_config.password = NULL;
        mqtt_config.use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    // Получение node_id, gh_uid, zone_uid
    init_steps_utils_get_config_string("node_id", node_id, sizeof(node_id), CLIMATE_NODE_DEFAULT_NODE_ID);
    init_steps_utils_get_config_string("gh_uid", gh_uid, sizeof(gh_uid), CLIMATE_NODE_DEFAULT_GH_UID);
    init_steps_utils_get_config_string("zone_uid", zone_uid, sizeof(zone_uid), CLIMATE_NODE_DEFAULT_ZONE_UID);
    
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
    
    // Callbacks будут зарегистрированы в climate_node_init.c перед climate_node_init_step_finalize
    // MQTT старт перенесен в climate_node_init_step_finalize, чтобы callbacks были зарегистрированы до старта
    
    if (result) {
        result->err = ESP_OK;
        result->component_initialized = true;
    }
    
    return ESP_OK;
}

esp_err_t climate_node_init_step_finalize(climate_node_init_context_t *ctx,
                                          climate_node_init_step_result_t *result) {
    ESP_LOGI(TAG, "[Step 8/8] Starting...");
    
    if (result) {
        result->component_name = "finalize";
        result->component_initialized = true;
    }
    
    // Запускаем MQTT после регистрации callbacks (которые происходят в climate_node_init.c)
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
    // ВАЖНО: Эта функция вызывается только из основного потока инициализации (app_main),
    // НЕ из MQTT callback, поэтому безопасно вызывать oled_ui_stop_init_steps()
    // НО: Конфиг может прийти через MQTT callback во время выполнения этой функции,
    // поэтому нужно быть осторожным с I2C операциями
    if (oled_ui_is_initialized()) {
        if (ctx && ctx->show_oled_steps) {
            // Проверяем, что шаги еще активны (не были остановлены из другого потока)
            // Используем безопасный способ остановки шагов - через флаг
            // oled_ui_stop_init_steps() безопасен, так как использует мьютекс для I2C операций
            // Но лучше отложить вызов, если конфиг обрабатывается
            esp_err_t oled_err = oled_ui_stop_init_steps();
            if (oled_err != ESP_OK) {
                ESP_LOGW(TAG, "Failed to stop init steps: %s (may be called from config handler)", esp_err_to_name(oled_err));
            }
        }
        // Всегда переводим OLED в нормальный режим после инициализации
        // oled_ui_set_state безопасен, так как использует внутренний мьютекс
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
