/**
 * @file pump_node_app.c
 * @brief Пример использования mqtt_client компонента в pump_node
 * 
 * Демонстрирует интеграцию mqtt_client для:
 * - Подключения к MQTT брокеру
 * - Подписки на config и command топики
 * - Публикации телеметрии, статусов и ответов
 */

#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "config_apply.h"
#include "pump_node_app.h"
#include "pump_driver.h"
#include "setup_portal.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// Объявление функции из pump_node_tasks.c
extern void pump_node_start_tasks(void);

static const char *TAG = "pump_node";

// Forward declarations
static void on_command_received(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);
static void on_mqtt_connection_changed(bool connected, void *user_ctx);
static void on_wifi_connection_changed(bool connected, void *user_ctx);

// Пример: обработка config сообщений
static void on_config_received(const char *topic, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Config received on %s: %.*s", topic, data_len, data);
    
    // Парсинг NodeConfig согласно NODE_CONFIG_SPEC.md
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        // Отправка ошибки
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid JSON");
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_manager_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    cJSON *previous_config = config_apply_load_previous_config();

    // Валидация обязательных полей согласно NODE_CONFIG_SPEC.md
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
        
        // Отправка ошибки валидации
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid channel ph_sensor");
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_manager_publish_config_response(json_str);
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
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *error_json = cJSON_PrintUnformatted(error_response);
            if (error_json) {
                mqtt_manager_publish_config_response(error_json);
                free(error_json);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
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
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *error_json = cJSON_PrintUnformatted(error_response);
            if (error_json) {
                mqtt_manager_publish_config_response(error_json);
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
        .default_node_id = "pump-001",
        .default_gh_uid = "gh-1",
        .default_zone_uid = "zn-3",
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

    esp_err_t pump_err = config_apply_channels_pump(&apply_result);
    if (pump_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reinitialize pump channels: %s", esp_err_to_name(pump_err));
    }

    esp_err_t ack_err = config_apply_publish_ack(&apply_result);
    if (ack_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish config ACK: %s", esp_err_to_name(ack_err));
    }

    extern void pump_node_update_current_poll_interval(void);
    pump_node_update_current_poll_interval();

    if (previous_config) {
        cJSON_Delete(previous_config);
    }
    cJSON_Delete(config);
}

// Пример: обработка command сообщений
static void on_command_received(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Command received on %s (channel: %s): %.*s", topic, channel, data_len, data);
    
    // Парсинг команды
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
    
    // Здесь должна быть логика выполнения команды
    // Например, для команды run_pump:
    if (strcmp(cmd, "run_pump") == 0) {
        cJSON *duration_item = cJSON_GetObjectItem(json, "duration_ms");
        if (cJSON_IsNumber(duration_item)) {
            int duration_ms = (int)cJSON_GetNumberValue(duration_item);
            ESP_LOGI(TAG, "Running pump on channel %s for %d ms", channel, duration_ms);
            
            // Реальная логика управления насосом через pump_driver
            // pump_driver автоматически проверяет ток через INA209 при запуске
            esp_err_t err = pump_driver_run(channel, duration_ms);
            
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                if (err == ESP_OK) {
                    cJSON_AddStringToObject(response, "status", "ACK");
                } else {
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    // Определяем тип ошибки на основе кода ошибки
                    if (err == ESP_ERR_INVALID_RESPONSE) {
                        cJSON_AddStringToObject(response, "error_code", "current_not_detected");
                        cJSON_AddStringToObject(response, "error_message", "Pump started but no current detected");
                    } else if (err == ESP_ERR_INVALID_SIZE) {
                        cJSON_AddStringToObject(response, "error_code", "overcurrent");
                        cJSON_AddStringToObject(response, "error_message", "Pump current exceeds safe limit");
                    } else {
                        cJSON_AddStringToObject(response, "error_code", "pump_driver_failed");
                        cJSON_AddStringToObject(response, "error_message", esp_err_to_name(err));
                    }
                }
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_manager_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
        }
    } else {
        // Неизвестная команда - отправка ERROR согласно MQTT_SPEC_FULL.md
        // Обязательно отправляем ответ даже при ошибке
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            cJSON_AddStringToObject(response, "status", "ERROR");
            cJSON_AddStringToObject(response, "error_code", "unknown_command");
            cJSON_AddStringToObject(response, "error_message", "Unknown command");
            cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
            
            // Опционально: details для расширенной информации
            cJSON *details = cJSON_CreateObject();
            if (details) {
                cJSON_AddStringToObject(details, "channel", channel);
                cJSON_AddStringToObject(details, "received_cmd", cmd);
                cJSON_AddItemToObject(response, "details", details);
            }
            
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                    mqtt_manager_publish_command_response(channel, json_str);
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
        ESP_LOGI(TAG, "MQTT connected - pump_node is online");
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - pump_node is offline");
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
 * @brief Инициализация pump_node с использованием mqtt_client
 * 
 * Пример инициализации компонента mqtt_client для pump_node.
 * В реальном приложении параметры должны загружаться из NodeConfig (NVS).
 */
void pump_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing pump_node...");
    
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
            .node_type_prefix = "PUMP",
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
        strncpy(node_id, "pump-001", sizeof(node_id) - 1);
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
    
    // Регистрация callbacks
    mqtt_manager_register_config_cb(on_config_received, NULL);
    mqtt_manager_register_command_cb(on_command_received, NULL);
    mqtt_manager_register_connection_cb(on_mqtt_connection_changed, NULL);
    
    // Запуск MQTT клиента
    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    // Инициализация pump_driver из NodeConfig
    err = pump_driver_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Pump driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No pump channels found in config, pump driver not initialized");
    } else {
        ESP_LOGE(TAG, "Failed to initialize pump driver: %s", esp_err_to_name(err));
    }
    
    ESP_LOGI(TAG, "pump_node initialized");
    
    // Запуск FreeRTOS задач для heartbeat
    pump_node_start_tasks();
}

/**
 * @brief Пример публикации телеметрии
 */
void pump_node_publish_telemetry_example(void) {
    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }
    
    // Пример телеметрии для канала pump_in
    // Формат согласно MQTT_SPEC_FULL.md раздел 3.2:
    // {
    //   "node_id": "nd-ph-1",
    //   "channel": "ph_sensor",
    //   "metric_type": "PH",
    //   "value": 5.86,
    //   "raw": 1465,
    //   "timestamp": 1710001234
    // }
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", "pump-001");  // UID узла из NodeConfig
        cJSON_AddStringToObject(telemetry, "channel", "pump_in");     // Имя канала
        cJSON_AddStringToObject(telemetry, "metric_type", "CURRENT"); // Тип метрики
        cJSON_AddNumberToObject(telemetry, "value", 1.25);           // Обработанное значение
        cJSON_AddNumberToObject(telemetry, "raw", 1250);             // Сырое значение (ADC, I2C и т.д.)
        cJSON_AddNumberToObject(telemetry, "timestamp", (double)(esp_timer_get_time() / 1000000)); // Unix timestamp в секундах
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_manager_publish_telemetry("pump_in", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

/**
 * @brief Пример публикации heartbeat
 */
void pump_node_publish_heartbeat_example(void) {
    if (!mqtt_manager_is_connected()) {
        return;
    }
    
    // Формат heartbeat согласно MQTT_SPEC_FULL.md раздел 9.1:
    // {
    //   "uptime": 35555,
    //   "free_heap": 102000,
    //   "rssi": -62
    // }
    cJSON *heartbeat = cJSON_CreateObject();
    if (heartbeat) {
        cJSON_AddNumberToObject(heartbeat, "uptime", (double)(esp_timer_get_time() / 1000)); // В миллисекундах
        cJSON_AddNumberToObject(heartbeat, "free_heap", (double)esp_get_free_heap_size());   // В байтах
        // TODO: Получить реальный RSSI из Wi-Fi
        cJSON_AddNumberToObject(heartbeat, "rssi", -62); // RSSI в dBm
        
        char *json_str = cJSON_PrintUnformatted(heartbeat);
        if (json_str) {
            mqtt_manager_publish_heartbeat(json_str);
            free(json_str);
        }
        cJSON_Delete(heartbeat);
    }
}
