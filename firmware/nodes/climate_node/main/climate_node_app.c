/**
 * @file climate_node_app.c
 * @brief Основная логика climate_node
 * 
 * Климатическая нода для измерения температуры, влажности, CO₂ и управления
 * вентиляторами, нагревателями, освещением
 * Согласно NODE_ARCH_FULL.md и MQTT_SPEC_FULL.md
 */

#include "mqtt_client.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "config_apply.h"
#include "climate_node_app.h"
#include "relay_driver.h"
#include "setup_portal.h"
#include "i2c_bus.h"
#include "sht3x.h"
#include "ccs811.h"
#include "pwm_driver.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

static const char *TAG = "climate_node";
static esp_err_t climate_node_init_i2c_bus(void) {
    esp_err_t err = i2c_bus_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "I2C bus initialized from config");
        return ESP_OK;
    }

    if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "I2C config not found, using defaults");
        i2c_bus_config_t cfg = {
            .sda_pin = 21,
            .scl_pin = 22,
            .clock_speed = 400000,
            .pullup_enable = true,
        };
        err = i2c_bus_init(&cfg);
    }

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "I2C bus initialized with fallback config");
    } else {
        ESP_LOGE(TAG, "Failed to initialize I2C bus: %s", esp_err_to_name(err));
    }

    return err;
}

static void climate_node_init_sensors(void) {
    esp_err_t err = climate_node_init_i2c_bus();
    if (err != ESP_OK) {
        return;
    }

    sht3x_config_t sht_cfg = {
        .i2c_address = 0x44,
    };
    err = sht3x_init(&sht_cfg);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "SHT3x driver initialized");
    } else {
        ESP_LOGE(TAG, "Failed to init SHT3x: %s", esp_err_to_name(err));
    }

    ccs811_config_t ccs_cfg = {
        .i2c_address = 0x5A,
        .measurement_interval_ms = 1000,
    };
    err = ccs811_init(&ccs_cfg);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "CCS811 driver initialized");
    } else {
        ESP_LOGE(TAG, "Failed to init CCS811: %s", esp_err_to_name(err));
    }
}

// Пример: обработка config сообщений
static void on_config_received(const char *topic, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Config received on %s: %.*s", topic, data_len, data);
    
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid JSON");
            cJSON_AddNumberToObject(error_response, "ts", (double)(esp_timer_get_time() / 1000000));
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_client_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    cJSON *previous_config = config_apply_load_previous_config();

    // Валидация обязательных полей
    cJSON *node_id_item = cJSON_GetObjectItem(config, "node_id");
    cJSON *version_item = cJSON_GetObjectItem(config, "version");
    cJSON *type_item = cJSON_GetObjectItem(config, "type");
    cJSON *channels_item = cJSON_GetObjectItem(config, "channels");
    cJSON *mqtt_item = cJSON_GetObjectItem(config, "mqtt");
    
    bool valid = cJSON_IsString(node_id_item) && 
                 cJSON_IsNumber(version_item) &&
                 cJSON_IsString(type_item) &&
                 cJSON_IsArray(channels_item) &&
                 cJSON_IsObject(mqtt_item);
    
    if (!valid) {
        ESP_LOGE(TAG, "Config validation failed: missing required fields");
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Missing required fields");
            cJSON_AddNumberToObject(error_response, "ts", (double)(esp_timer_get_time() / 1000000));
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_client_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    const char *node_id = node_id_item->valuestring;
    ESP_LOGI(TAG, "Applying config for node: %s", node_id);
    
    // Валидация и сохранение конфигурации
    char *json_str = cJSON_PrintUnformatted(config);
    if (json_str == NULL) {
        ESP_LOGE(TAG, "Failed to serialize config to JSON");
        cJSON_Delete(config);
        return;
    }
    
    char error_msg[128];
    esp_err_t err = config_storage_validate(json_str, strlen(json_str), error_msg, sizeof(error_msg));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Config validation failed: %s", error_msg);
        free(json_str);
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", error_msg);
            cJSON_AddNumberToObject(error_response, "ts", (double)(esp_timer_get_time() / 1000000));
            char *error_json = cJSON_PrintUnformatted(error_response);
            if (error_json) {
                mqtt_client_publish_config_response(error_json);
                free(error_json);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    // Сохраняем новый конфиг
    err = config_storage_save(json_str, strlen(json_str));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config to NVS: %s", esp_err_to_name(err));
        free(json_str);
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Failed to save config to NVS");
            cJSON_AddNumberToObject(error_response, "ts", (double)(esp_timer_get_time() / 1000000));
            char *error_json = cJSON_PrintUnformatted(error_response);
            if (error_json) {
                mqtt_client_publish_config_response(error_json);
                free(error_json);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    free(json_str);

    config_apply_result_t apply_result;
    config_apply_result_init(&apply_result);

    const config_apply_mqtt_params_t mqtt_params = {
        .default_node_id = "climate-001",
        .default_gh_uid = "gh-1",
        .default_zone_uid = "zn-1",
        .config_cb = on_config_received,
        .command_cb = on_command_received,
        .connection_cb = on_mqtt_connection_changed,
        .user_ctx = NULL,
    };

    esp_err_t wifi_err = config_apply_wifi(config, previous_config, &apply_result);
    if (wifi_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reapply Wi-Fi config: %s", esp_err_to_name(wifi_err));
    }

    esp_err_t mqtt_err = config_apply_mqtt(config, previous_config, &mqtt_params, &apply_result);
    if (mqtt_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reapply MQTT config: %s", esp_err_to_name(mqtt_err));
    }

    esp_err_t relay_err = config_apply_channels_relay(&apply_result);
    if (relay_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reinitialize relay channels: %s", esp_err_to_name(relay_err));
    }

    esp_err_t ack_err = config_apply_publish_ack(&apply_result);
    if (ack_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish config ACK: %s", esp_err_to_name(ack_err));
    }

    if (previous_config) {
        cJSON_Delete(previous_config);
    }
    cJSON_Delete(config);
}

// Пример: обработка command сообщений
static void on_command_received(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Command received on %s (channel: %s): %.*s", topic, channel, data_len, data);
    
    cJSON *json = cJSON_ParseWithLength(data, data_len);
    if (!json) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    cJSON *cmd_item = cJSON_GetObjectItem(json, "cmd");
    cJSON *cmd_id_item = cJSON_GetObjectItem(json, "cmd_id");
    
    if (!cJSON_IsString(cmd_item) || !cJSON_IsString(cmd_id_item)) {
        ESP_LOGE(TAG, "Invalid command format");
        cJSON_Delete(json);
        return;
    }
    
    const char *cmd = cmd_item->valuestring;
    const char *cmd_id = cmd_id_item->valuestring;
    
    ESP_LOGI(TAG, "Processing command: %s (id: %s) on channel: %s", cmd, cmd_id, channel);
    
    // Обработка команд для актуаторов
    if (strcmp(cmd, "set_relay") == 0) {
        // Команда для реле (вентилятор, нагреватель, освещение)
        cJSON *state_item = cJSON_GetObjectItem(json, "state");
        if (cJSON_IsBool(state_item)) {
            bool state = cJSON_IsTrue(state_item);
            ESP_LOGI(TAG, "Setting %s to %s", channel, state ? "ON" : "OFF");
            
            // Реальная логика управления реле через relay_driver
            relay_state_t relay_state = state ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
            esp_err_t err = relay_driver_set_state(channel, relay_state);
            
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                if (err == ESP_OK) {
                    cJSON_AddStringToObject(response, "status", "ACK");
                } else {
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    cJSON_AddStringToObject(response, "error_code", "relay_driver_failed");
                    cJSON_AddStringToObject(response, "error_message", esp_err_to_name(err));
                }
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_client_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
        }
    } else if (strcmp(cmd, "set_pwm") == 0) {
        // Команда для PWM (вентилятор, освещение)
        cJSON *value_item = cJSON_GetObjectItem(json, "value");
        if (cJSON_IsNumber(value_item)) {
            int pwm_value = (int)cJSON_GetNumberValue(value_item);
            float duty_percent;
            if (pwm_value <= 100) {
                duty_percent = (float)pwm_value;
            } else {
                if (pwm_value < 0) {
                    pwm_value = 0;
                }
                if (pwm_value > 255) {
                    pwm_value = 255;
                }
                duty_percent = ((float)pwm_value / 255.0f) * 100.0f;
            }

            ESP_LOGI(TAG, "Setting %s PWM to %d (%.1f%%)", channel, pwm_value, duty_percent);
            esp_err_t pwm_err = pwm_driver_set_duty_percent(channel, duty_percent);

            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                if (pwm_err == ESP_OK) {
                    cJSON_AddStringToObject(response, "status", "ACK");
                } else {
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    cJSON_AddStringToObject(response, "error_code", "pwm_failed");
                    cJSON_AddStringToObject(response, "error_message", esp_err_to_name(pwm_err));
                }
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));

                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_client_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
        }
    } else {
        // Неизвестная команда
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            cJSON_AddStringToObject(response, "status", "ERROR");
            cJSON_AddStringToObject(response, "error_code", "unknown_command");
            cJSON_AddStringToObject(response, "error_message", "Unknown command");
            cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
            
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_client_publish_command_response(channel, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
    }
    
    cJSON_Delete(json);
}

// Пример: обработка событий подключения MQTT
static void on_mqtt_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - climate_node is online");
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - climate_node is offline");
    }
}

// Пример: обработка событий подключения Wi-Fi
static void on_wifi_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "Wi-Fi connected");
    } else {
        ESP_LOGW(TAG, "Wi-Fi disconnected");
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
    strncpy(wifi_password, wifi_cfg.password, sizeof(wifi_password) - 1);
    wifi_config.ssid = wifi_ssid;
    wifi_config.password = wifi_password;
    ESP_LOGI(TAG, "Connecting to Wi-Fi from config: %s", wifi_cfg.ssid);
    
    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect to Wi-Fi: %s", esp_err_to_name(err));
    }
    
    // Инициализация MQTT клиента
    config_storage_mqtt_t mqtt_cfg;
    mqtt_client_config_t mqtt_config;
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
    
    if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
        node_info.node_uid = node_id;
        ESP_LOGI(TAG, "Node ID from config: %s", node_id);
    } else {
        strncpy(node_id, "nd-climate-1", sizeof(node_id) - 1);
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
    
    err = mqtt_client_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    // Регистрация callbacks
    mqtt_client_register_config_cb(on_config_received, NULL);
    mqtt_client_register_command_cb(on_command_received, NULL);
    mqtt_client_register_connection_cb(on_mqtt_connection_changed, NULL);
    
    // Запуск MQTT клиента
    err = mqtt_client_start();
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

    climate_node_init_sensors();

    ESP_LOGI(TAG, "climate_node initialized");

    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    climate_node_start_tasks();
}

