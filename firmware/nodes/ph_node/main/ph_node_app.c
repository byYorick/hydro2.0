/**
 * @file ph_node_app.c
 * @brief Основная логика ph_node
 * 
 * pH-нода для измерения pH и управления насосами кислоты/щелочи
 * Согласно NODE_ARCH_FULL.md и MQTT_SPEC_FULL.md
 */

#include "mqtt_client.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "ph_node_app.h"
#include "trema_ph.h"
#include "i2c_bus.h"
#include "oled_ui.h"
#include "pump_control.h"
#include <stdbool.h>
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

static const char *TAG = "ph_node";

// Глобальное состояние pH-сенсора (для доступа из других модулей)
bool ph_sensor_initialized = false;

// Глобальное состояние OLED UI
bool oled_ui_initialized = false;

// Глобальное состояние насосов
static bool pump_control_initialized = false;

// Глобальный node_id для использования в разных местах
static char g_node_id[64] = "nd-ph-1";

// Пример: обработка config сообщений
static void on_config_received(const char *topic, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Config received on %s: %.*s", topic, data_len, data);
    
    // Парсинг NodeConfig согласно NODE_CONFIG_SPEC.md
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid JSON");
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_client_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
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
        
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Missing required fields");
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
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
    
    // Валидация конфигурации
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
        
        // Отправка ошибки валидации
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", error_msg);
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
            char *error_json = cJSON_PrintUnformatted(error_response);
            if (error_json) {
                mqtt_client_publish_config_response(error_json);
                free(error_json);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    // Сохранение конфигурации в NVS
    err = config_storage_save(json_str, strlen(json_str));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config to NVS: %s", esp_err_to_name(err));
        free(json_str);
        cJSON_Delete(config);
        
        // Отправка ошибки сохранения
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Failed to save config to NVS");
            cJSON_AddNumberToObject(error_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
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
    cJSON_Delete(config);
    
    // TODO: Обновление параметров Wi-Fi и MQTT (требует переподключения)
    // TODO: Перезапуск каналов согласно новой конфигурации
    
    // Отправка подтверждения
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "status", "OK");
        cJSON_AddStringToObject(response, "node_id", node_id);
        cJSON_AddBoolToObject(response, "applied", true);
        cJSON_AddNumberToObject(response, "timestamp", (double)(esp_timer_get_time() / 1000000));
        
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            mqtt_client_publish_config_response(json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }
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
    
    // Обработка команд для насосов (pump_acid, pump_base)
    if (strcmp(channel, "pump_acid") == 0 || strcmp(channel, "pump_base") == 0) {
        pump_id_t pump_id = (strcmp(channel, "pump_acid") == 0) ? PUMP_ACID : PUMP_BASE;
        
        if (strcmp(cmd, "DOSE") == 0) {
            // Команда дозирования по объёму
            cJSON *ml_item = cJSON_GetObjectItem(json, "ml");
            if (cJSON_IsNumber(ml_item)) {
                float dose_ml = (float)cJSON_GetNumberValue(ml_item);
                ESP_LOGI(TAG, "Dosing %s: %.2f ml", channel, dose_ml);
                
                if (!pump_control_initialized) {
                    ESP_LOGE(TAG, "Pump control not initialized");
                    cJSON *response = cJSON_CreateObject();
                    if (response) {
                        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                        cJSON_AddStringToObject(response, "status", "ERROR");
                        cJSON_AddStringToObject(response, "error_code", "not_initialized");
                        cJSON_AddStringToObject(response, "error_message", "Pump control not initialized");
                        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                        
                        char *json_str = cJSON_PrintUnformatted(response);
                        if (json_str) {
                            mqtt_client_publish_command_response(channel, json_str);
                            free(json_str);
                        }
                        cJSON_Delete(response);
                    }
                } else {
                    esp_err_t ret = pump_control_dose(pump_id, dose_ml);
                    
                    cJSON *response = cJSON_CreateObject();
                    if (response) {
                        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                        if (ret == ESP_OK) {
                            cJSON_AddStringToObject(response, "status", "ACK");
                            cJSON_AddNumberToObject(response, "dose_ml", dose_ml);
                        } else {
                            cJSON_AddStringToObject(response, "status", "ERROR");
                            cJSON_AddStringToObject(response, "error_code", "pump_error");
                            cJSON_AddStringToObject(response, "error_message", esp_err_to_name(ret));
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
                ESP_LOGE(TAG, "Invalid DOSE command: missing ml parameter");
                cJSON *response = cJSON_CreateObject();
                if (response) {
                    cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    cJSON_AddStringToObject(response, "error_code", "invalid_format");
                    cJSON_AddStringToObject(response, "error_message", "Missing ml parameter");
                    cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                    
                    char *json_str = cJSON_PrintUnformatted(response);
                    if (json_str) {
                        mqtt_client_publish_command_response(channel, json_str);
                        free(json_str);
                    }
                    cJSON_Delete(response);
                }
            }
        } else if (strcmp(cmd, "SET_STATE") == 0) {
            // Команда установки состояния (включить/выключить)
            cJSON *state_item = cJSON_GetObjectItem(json, "state");
            if (cJSON_IsNumber(state_item)) {
                int state = (int)cJSON_GetNumberValue(state_item);
                ESP_LOGI(TAG, "Setting %s state to %d", channel, state);
                
                if (!pump_control_initialized) {
                    ESP_LOGE(TAG, "Pump control not initialized");
                    cJSON *response = cJSON_CreateObject();
                    if (response) {
                        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                        cJSON_AddStringToObject(response, "status", "ERROR");
                        cJSON_AddStringToObject(response, "error_code", "not_initialized");
                        cJSON_AddStringToObject(response, "error_message", "Pump control not initialized");
                        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                        
                        char *json_str = cJSON_PrintUnformatted(response);
                        if (json_str) {
                            mqtt_client_publish_command_response(channel, json_str);
                            free(json_str);
                        }
                        cJSON_Delete(response);
                    }
                } else {
                    esp_err_t ret = pump_control_set_state(pump_id, state);
                    
                    cJSON *response = cJSON_CreateObject();
                    if (response) {
                        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                        if (ret == ESP_OK) {
                            cJSON_AddStringToObject(response, "status", "ACK");
                            cJSON_AddNumberToObject(response, "state", state);
                        } else {
                            cJSON_AddStringToObject(response, "status", "ERROR");
                            cJSON_AddStringToObject(response, "error_code", "pump_error");
                            cJSON_AddStringToObject(response, "error_message", esp_err_to_name(ret));
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
                ESP_LOGE(TAG, "Invalid SET_STATE command: missing state parameter");
                cJSON *response = cJSON_CreateObject();
                if (response) {
                    cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    cJSON_AddStringToObject(response, "error_code", "invalid_format");
                    cJSON_AddStringToObject(response, "error_message", "Missing state parameter");
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
            ESP_LOGE(TAG, "Unknown command for pump: %s", cmd);
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "unknown_command");
                cJSON_AddStringToObject(response, "error_message", "Unknown command for pump");
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_client_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
        }
    } else if (strcmp(cmd, "calibrate") == 0) {
        // Команда калибровки pH
        cJSON *stage_item = cJSON_GetObjectItem(json, "stage");
        cJSON *ph_value_item = cJSON_GetObjectItem(json, "ph_value");
        
        if (!cJSON_IsNumber(stage_item) || !cJSON_IsNumber(ph_value_item)) {
            ESP_LOGE(TAG, "Invalid calibration command format");
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "invalid_format");
                cJSON_AddStringToObject(response, "error_message", "Missing stage or ph_value");
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_client_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
        float known_ph = (float)cJSON_GetNumberValue(ph_value_item);
        
        if (stage != 1 && stage != 2) {
            ESP_LOGE(TAG, "Invalid calibration stage: %d (must be 1 or 2)", stage);
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "invalid_stage");
                cJSON_AddStringToObject(response, "error_message", "Stage must be 1 or 2");
                cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
                
                char *json_str = cJSON_PrintUnformatted(response);
                if (json_str) {
                    mqtt_client_publish_command_response(channel, json_str);
                    free(json_str);
                }
                cJSON_Delete(response);
            }
            cJSON_Delete(json);
            return;
        }
        
        ESP_LOGI(TAG, "Starting pH calibration: stage=%d, known_pH=%.2f", stage, known_ph);
        
        bool cal_success = trema_ph_calibrate(stage, known_ph);
        
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            if (cal_success) {
                cJSON_AddStringToObject(response, "status", "ACK");
                cJSON_AddNumberToObject(response, "stage", stage);
                cJSON_AddNumberToObject(response, "known_ph", known_ph);
            } else {
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "calibration_failed");
                cJSON_AddStringToObject(response, "error_message", "Failed to start calibration");
            }
            cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
            
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_client_publish_command_response(channel, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
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

// Обработка событий подключения MQTT
static void on_mqtt_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - ph_node is online");
        
        // Обновление OLED UI
        if (oled_ui_initialized) {
            oled_ui_model_t model = {0};
            oled_ui_update_model(&model); // Получим текущую модель
            model.connections.mqtt_connected = true;
            oled_ui_update_model(&model);
        }
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - ph_node is offline");
        
        // Обновление OLED UI
        if (oled_ui_initialized) {
            oled_ui_model_t model = {0};
            oled_ui_update_model(&model);
            model.connections.mqtt_connected = false;
            oled_ui_update_model(&model);
        }
    }
}

// Обработка событий подключения Wi-Fi
static void on_wifi_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "Wi-Fi connected");
        
        // Обновление OLED UI
        if (oled_ui_initialized) {
            wifi_ap_record_t ap_info;
            int8_t rssi = -100;
            if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                rssi = ap_info.rssi;
            }
            
            oled_ui_model_t model = {0};
            oled_ui_update_model(&model);
            model.connections.wifi_connected = true;
            model.connections.wifi_rssi = rssi;
            oled_ui_update_model(&model);
        }
    } else {
        ESP_LOGW(TAG, "Wi-Fi disconnected");
        
        // Обновление OLED UI
        if (oled_ui_initialized) {
            oled_ui_model_t model = {0};
            oled_ui_update_model(&model);
            model.connections.wifi_connected = false;
            oled_ui_update_model(&model);
        }
    }
}

/**
 * @brief Инициализация ph_node
 */
void ph_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing ph_node...");
    
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
    
    // Регистрация callback для Wi-Fi событий
    wifi_manager_register_connection_cb(on_wifi_connection_changed, NULL);
    
    // Подключение к Wi-Fi (из конфига или значения по умолчанию)
    config_storage_wifi_t wifi_cfg;
    wifi_manager_config_t wifi_config;
    static char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
    static char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
    
    if (config_storage_get_wifi(&wifi_cfg) == ESP_OK) {
        strncpy(wifi_ssid, wifi_cfg.ssid, sizeof(wifi_ssid) - 1);
        strncpy(wifi_password, wifi_cfg.password, sizeof(wifi_password) - 1);
        wifi_config.ssid = wifi_ssid;
        wifi_config.password = wifi_password;
        ESP_LOGI(TAG, "Connecting to Wi-Fi from config: %s", wifi_cfg.ssid);
    } else {
        // Значения по умолчанию (для первого запуска)
        strncpy(wifi_ssid, "FarmWiFi", sizeof(wifi_ssid) - 1);
        strncpy(wifi_password, "12345678", sizeof(wifi_password) - 1);
        wifi_config.ssid = wifi_ssid;
        wifi_config.password = wifi_password;
        ESP_LOGW(TAG, "Using default Wi-Fi credentials");
    }
    
    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect to Wi-Fi: %s", esp_err_to_name(err));
        // Продолжаем работу - Wi-Fi будет пытаться переподключиться автоматически
    }
    
    // Инициализация I²C шины (если еще не инициализирована)
    if (!i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "Initializing I²C bus...");
        err = i2c_bus_init_from_config();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to initialize I²C bus from config, using defaults");
            i2c_bus_config_t i2c_config = {
                .sda_pin = 21,
                .scl_pin = 22,
                .clock_speed = 100000,
                .pullup_enable = true
            };
            err = i2c_bus_init(&i2c_config);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to initialize I²C bus: %s", esp_err_to_name(err));
                // Продолжаем работу, возможно I²C не нужен
            }
        }
    }
    
    // Инициализация Trema pH-сенсора
    if (i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "Initializing Trema pH sensor...");
        if (trema_ph_init()) {
            ph_sensor_initialized = true;
            ESP_LOGI(TAG, "Trema pH sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize Trema pH sensor, will retry later");
            ph_sensor_initialized = false;
        }
    } else {
        ESP_LOGW(TAG, "I²C bus not available, pH sensor initialization skipped");
    }
    
    // Инициализация OLED UI
    if (i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "Initializing OLED UI...");
        oled_ui_config_t oled_config = {
            .i2c_address = 0x3C,
            .update_interval_ms = 500,
            .enable_task = true
        };
        
        esp_err_t oled_err = oled_ui_init(OLED_UI_NODE_TYPE_PH, g_node_id, &oled_config);
        if (oled_err == ESP_OK) {
            oled_ui_initialized = true;
            oled_ui_set_state(OLED_UI_STATE_BOOT);
            ESP_LOGI(TAG, "OLED UI initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize OLED UI: %s", esp_err_to_name(oled_err));
            oled_ui_initialized = false;
        }
    } else {
        ESP_LOGW(TAG, "I²C bus not available, OLED UI initialization skipped");
    }
    
    // Инициализация управления насосами
    ESP_LOGI(TAG, "Initializing pump control...");
    pump_config_t pump_configs[PUMP_MAX] = {
        {
            .gpio_pin = 12,  // GPIO для pump_acid (можно переопределить через NodeConfig)
            .max_duration_ms = 30000,  // 30 секунд максимум
            .min_off_time_ms = 5000,   // 5 секунд минимум между запусками
            .ml_per_second = 2.0f     // 2 мл/сек по умолчанию
        },
        {
            .gpio_pin = 13,  // GPIO для pump_base (можно переопределить через NodeConfig)
            .max_duration_ms = 30000,
            .min_off_time_ms = 5000,
            .ml_per_second = 2.0f
        }
    };
    
    esp_err_t pump_err = pump_control_init(pump_configs);
    if (pump_err == ESP_OK) {
        pump_control_initialized = true;
        ESP_LOGI(TAG, "Pump control initialized successfully");
    } else {
        ESP_LOGE(TAG, "Failed to initialize pump control: %s", esp_err_to_name(pump_err));
        pump_control_initialized = false;
    }
    
    // Инициализация MQTT клиента (из конфига или значения по умолчанию)
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
        // Значения по умолчанию
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
    
    // Получение node_id из конфига
    if (config_storage_get_node_id(node_id, sizeof(node_id)) == ESP_OK) {
        node_info.node_uid = node_id;
        strncpy(g_node_id, node_id, sizeof(g_node_id) - 1);
        ESP_LOGI(TAG, "Node ID from config: %s", node_id);
    } else {
        // Значение по умолчанию
        strncpy(node_id, "nd-ph-1", sizeof(node_id) - 1);
        strncpy(g_node_id, node_id, sizeof(g_node_id) - 1);
        node_info.node_uid = node_id;
        ESP_LOGW(TAG, "Using default node ID");
    }
    
    // gh_uid и zone_uid пока не хранятся в NodeConfig, используем значения по умолчанию
    // TODO: Добавить эти поля в NodeConfig или получать из другого источника
    node_info.gh_uid = default_gh_uid;
    node_info.zone_uid = default_zone_uid;
    
    err = mqtt_client_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    // Регистрация callbacks
    mqtt_client_register_config_cb(on_config_received, NULL);
    mqtt_client_register_command_cb(on_command_received, NULL);
    mqtt_client_register_connection_cb(on_mqtt_connection_changed, NULL);
    
    // Запуск MQTT клиента (будет подключаться автоматически после подключения Wi-Fi)
    err = mqtt_client_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return;
    }
    
    ESP_LOGI(TAG, "ph_node initialized");
    
    // Переход OLED UI в нормальный режим после инициализации
    if (oled_ui_initialized) {
        oled_ui_set_state(OLED_UI_STATE_NORMAL);
    }
    
    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    ph_node_start_tasks();
}

/**
 * @brief Публикация телеметрии pH с реальными значениями от Trema pH-сенсора
 */
void ph_node_publish_telemetry_example(void) {
    if (!mqtt_client_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }
    
    // Инициализация сенсора, если еще не инициализирован
    if (!ph_sensor_initialized && i2c_bus_is_initialized()) {
        if (trema_ph_init()) {
            ph_sensor_initialized = true;
            ESP_LOGI(TAG, "Trema pH sensor initialized");
        }
    }
    
    // Чтение значения pH
    float ph_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    
    if (ph_sensor_initialized) {
        read_success = trema_ph_read(&ph_value);
        using_stub = trema_ph_is_using_stub_values();
        
        if (!read_success || isnan(ph_value)) {
            ESP_LOGW(TAG, "Failed to read pH value, using stub");
            ph_value = 6.5f;  // Нейтральное значение
            using_stub = true;
        }
    } else {
        ESP_LOGW(TAG, "pH sensor not initialized, using stub value");
        ph_value = 6.5f;
        using_stub = true;
    }
    
    // Получение node_id из конфига
    char node_id[64];
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        strncpy(node_id, "nd-ph-1", sizeof(node_id) - 1);
    }
    
    // Формат согласно MQTT_SPEC_FULL.md раздел 3.2
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "ph_sensor");
        cJSON_AddStringToObject(telemetry, "metric_type", "PH");
        cJSON_AddNumberToObject(telemetry, "value", ph_value);
        cJSON_AddNumberToObject(telemetry, "raw", (int)(ph_value * 1000));  // Сырое значение в тысячных
        cJSON_AddBoolToObject(telemetry, "stub", using_stub);  // Флаг использования заглушки
        cJSON_AddNumberToObject(telemetry, "timestamp", (double)(esp_timer_get_time() / 1000000));
        
        // Добавляем информацию о стабильности, если доступна
        if (ph_sensor_initialized && !using_stub) {
            bool is_stable = trema_ph_get_stability();
            cJSON_AddBoolToObject(telemetry, "stable", is_stable);
        }
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_client_publish_telemetry("ph_sensor", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

