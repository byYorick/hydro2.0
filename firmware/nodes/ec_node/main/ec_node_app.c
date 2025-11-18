/**
 * @file ec_node_app.c
 * @brief Основная логика ec_node
 * 
 * EC-нода для измерения электропроводности и управления насосом питательных веществ
 * Согласно NODE_ARCH_FULL.md и MQTT_SPEC_FULL.md
 */

#include "mqtt_client.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "ec_node_app.h"
#include "trema_ec.h"
#include "i2c_bus.h"
#include "pump_driver.h"
#include "setup_portal.h"
#include "esp_log.h"
#include "esp_err.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdbool.h>

static const char *TAG = "ec_node";

// Глобальное состояние EC-сенсора
static bool ec_sensor_initialized = false;

static const char *ec_node_pump_state_to_string(pump_driver_state_t state) {
    switch (state) {
        case PUMP_STATE_OFF:
            return "OFF";
        case PUMP_STATE_ON:
            return "ON";
        case PUMP_STATE_COOLDOWN:
            return "COOLDOWN";
        case PUMP_STATE_ERROR:
        default:
            return "ERROR";
    }
}

static void ec_node_publish_pump_status(const char *channel, const char *event) {
    if (channel == NULL || !mqtt_client_is_connected()) {
        return;
    }

    pump_driver_state_t pump_state;
    if (pump_driver_get_state(channel, &pump_state) != ESP_OK) {
        return;
    }

    char node_id[CONFIG_STORAGE_MAX_STRING_LEN] = {0};
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        strncpy(node_id, "nd-ec-1", sizeof(node_id) - 1);
    }

    cJSON *status = cJSON_CreateObject();
    if (!status) {
        return;
    }

    cJSON_AddStringToObject(status, "node_id", node_id);
    cJSON_AddStringToObject(status, "channel", channel);
    cJSON_AddStringToObject(status, "metric_type", "PUMP_STATE");
    cJSON_AddNumberToObject(status, "value", (int)pump_state);
    cJSON_AddStringToObject(status, "state", ec_node_pump_state_to_string(pump_state));
    if (event) {
        cJSON_AddStringToObject(status, "event", event);
    }
    cJSON_AddNumberToObject(status, "timestamp", (double)(esp_timer_get_time() / 1000000));

    char *json_str = cJSON_PrintUnformatted(status);
    if (json_str) {
        mqtt_client_publish_telemetry(channel, json_str);
        free(json_str);
    }

    cJSON_Delete(status);
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
    
    // Проверка изменений Wi-Fi и MQTT параметров (ПЕРЕД сохранением нового конфига)
    config_storage_wifi_t old_wifi_cfg;
    config_storage_mqtt_t old_mqtt_cfg;
    bool wifi_changed = false;
    bool mqtt_changed = false;
    
    // Загружаем старые параметры для сравнения
    if (config_storage_get_wifi(&old_wifi_cfg) == ESP_OK) {
        cJSON *wifi_item = cJSON_GetObjectItem(config, "wifi");
        if (wifi_item != NULL && cJSON_IsObject(wifi_item)) {
            cJSON *ssid_item = cJSON_GetObjectItem(wifi_item, "ssid");
            cJSON *pass_item = cJSON_GetObjectItem(wifi_item, "pass");
            
            if (ssid_item != NULL && cJSON_IsString(ssid_item)) {
                if (strcmp(old_wifi_cfg.ssid, ssid_item->valuestring) != 0) {
                    wifi_changed = true;
                    ESP_LOGI(TAG, "Wi-Fi SSID changed: %s -> %s", old_wifi_cfg.ssid, ssid_item->valuestring);
                }
            }
            
            if (pass_item != NULL && cJSON_IsString(pass_item)) {
                if (strcmp(old_wifi_cfg.password, pass_item->valuestring) != 0) {
                    wifi_changed = true;
                    ESP_LOGI(TAG, "Wi-Fi password changed");
                }
            }
        }
    }
    
    if (config_storage_get_mqtt(&old_mqtt_cfg) == ESP_OK) {
        cJSON *mqtt_item = cJSON_GetObjectItem(config, "mqtt");
        if (mqtt_item != NULL && cJSON_IsObject(mqtt_item)) {
            cJSON *host_item = cJSON_GetObjectItem(mqtt_item, "host");
            cJSON *port_item = cJSON_GetObjectItem(mqtt_item, "port");
            cJSON *username_item = cJSON_GetObjectItem(mqtt_item, "username");
            cJSON *password_item = cJSON_GetObjectItem(mqtt_item, "password");
            cJSON *use_tls_item = cJSON_GetObjectItem(mqtt_item, "use_tls");
            
            if (host_item != NULL && cJSON_IsString(host_item)) {
                if (strcmp(old_mqtt_cfg.host, host_item->valuestring) != 0) {
                    mqtt_changed = true;
                    ESP_LOGI(TAG, "MQTT host changed: %s -> %s", old_mqtt_cfg.host, host_item->valuestring);
                }
            }
            
            if (port_item != NULL && cJSON_IsNumber(port_item)) {
                if (old_mqtt_cfg.port != (uint16_t)cJSON_GetNumberValue(port_item)) {
                    mqtt_changed = true;
                    ESP_LOGI(TAG, "MQTT port changed: %d -> %d", old_mqtt_cfg.port, (uint16_t)cJSON_GetNumberValue(port_item));
                }
            }
            
            if (username_item != NULL && cJSON_IsString(username_item)) {
                if (strcmp(old_mqtt_cfg.username, username_item->valuestring) != 0) {
                    mqtt_changed = true;
                    ESP_LOGI(TAG, "MQTT username changed");
                }
            }
            
            if (password_item != NULL && cJSON_IsString(password_item)) {
                if (strcmp(old_mqtt_cfg.password, password_item->valuestring) != 0) {
                    mqtt_changed = true;
                    ESP_LOGI(TAG, "MQTT password changed");
                }
            }
            
            if (use_tls_item != NULL && cJSON_IsBool(use_tls_item)) {
                if (old_mqtt_cfg.use_tls != cJSON_IsTrue(use_tls_item)) {
                    mqtt_changed = true;
                    ESP_LOGI(TAG, "MQTT TLS setting changed");
                }
            }
        }
    }
    
    // Сохраняем новый конфиг
    err = config_storage_save(json_str, strlen(json_str));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config to NVS: %s", esp_err_to_name(err));
        free(json_str);
        cJSON_Delete(config);
        
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
    
    // Graceful переподключение Wi-Fi при изменении параметров
    if (wifi_changed) {
        ESP_LOGI(TAG, "Wi-Fi config changed, reconnecting...");
        
        // Остановка MQTT перед переподключением Wi-Fi
        if (mqtt_client_is_connected()) {
            mqtt_client_stop();
            vTaskDelay(pdMS_TO_TICKS(500)); // Даем время на остановку
        }
        
        // Отключение от текущей Wi-Fi сети
        wifi_manager_disconnect();
        vTaskDelay(pdMS_TO_TICKS(1000)); // Даем время на отключение
        
        // Подключение с новыми параметрами
        config_storage_wifi_t new_wifi_cfg;
        if (config_storage_get_wifi(&new_wifi_cfg) == ESP_OK) {
            wifi_manager_config_t wifi_config;
            static char wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
            static char wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
            
            strncpy(wifi_ssid, new_wifi_cfg.ssid, sizeof(wifi_ssid) - 1);
            strncpy(wifi_password, new_wifi_cfg.password, sizeof(wifi_password) - 1);
            wifi_config.ssid = wifi_ssid;
            wifi_config.password = wifi_password;
            
            esp_err_t err = wifi_manager_connect(&wifi_config);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to reconnect to Wi-Fi: %s", esp_err_to_name(err));
            } else {
                ESP_LOGI(TAG, "Wi-Fi reconnected successfully");
            }
        }
    }
    
    // Graceful переподключение MQTT при изменении параметров
    if (mqtt_changed) {
        ESP_LOGI(TAG, "MQTT config changed, reconnecting...");
        
        // Остановка текущего MQTT подключения
        if (mqtt_client_is_connected()) {
            mqtt_client_stop();
            vTaskDelay(pdMS_TO_TICKS(500)); // Даем время на остановку
        }
        
        // Деинициализация MQTT клиента
        mqtt_client_deinit();
        vTaskDelay(pdMS_TO_TICKS(500));
        
        // Инициализация с новыми параметрами
        config_storage_mqtt_t new_mqtt_cfg;
        mqtt_client_config_t mqtt_config;
        mqtt_client_node_info_t node_info;
        static char mqtt_host[CONFIG_STORAGE_MAX_STRING_LEN];
        static char mqtt_username[CONFIG_STORAGE_MAX_STRING_LEN];
        static char mqtt_password[CONFIG_STORAGE_MAX_STRING_LEN];
        static char node_id_buf[64];
        static const char *default_gh_uid = "gh-1";
        static const char *default_zone_uid = "zn-1";
        
        if (config_storage_get_mqtt(&new_mqtt_cfg) == ESP_OK) {
            strncpy(mqtt_host, new_mqtt_cfg.host, sizeof(mqtt_host) - 1);
            mqtt_config.host = mqtt_host;
            mqtt_config.port = new_mqtt_cfg.port;
            mqtt_config.keepalive = new_mqtt_cfg.keepalive;
            mqtt_config.client_id = NULL;
            if (strlen(new_mqtt_cfg.username) > 0) {
                strncpy(mqtt_username, new_mqtt_cfg.username, sizeof(mqtt_username) - 1);
                mqtt_config.username = mqtt_username;
            } else {
                mqtt_config.username = NULL;
            }
            if (strlen(new_mqtt_cfg.password) > 0) {
                strncpy(mqtt_password, new_mqtt_cfg.password, sizeof(mqtt_password) - 1);
                mqtt_config.password = mqtt_password;
            } else {
                mqtt_config.password = NULL;
            }
            mqtt_config.use_tls = new_mqtt_cfg.use_tls;
        }
        
        if (config_storage_get_node_id(node_id_buf, sizeof(node_id_buf)) == ESP_OK) {
            node_info.node_uid = node_id_buf;
        } else {
            strncpy(node_id_buf, "ec-001", sizeof(node_id_buf) - 1);
            node_info.node_uid = node_id_buf;
        }
        
        static char gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
        static char zone_uid[CONFIG_STORAGE_MAX_STRING_LEN];
        if (config_storage_get_gh_uid(gh_uid, sizeof(gh_uid)) == ESP_OK) {
            node_info.gh_uid = gh_uid;
        } else {
            node_info.gh_uid = default_gh_uid;
        }
        
        if (config_storage_get_zone_uid(zone_uid, sizeof(zone_uid)) == ESP_OK) {
            node_info.zone_uid = zone_uid;
        } else {
            node_info.zone_uid = default_zone_uid;
        }
        
        esp_err_t err = mqtt_client_init(&mqtt_config, &node_info);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to reinitialize MQTT client: %s", esp_err_to_name(err));
        } else {
            // Регистрация callbacks
            mqtt_client_register_config_cb(on_config_received, NULL);
            mqtt_client_register_command_cb(on_command_received, NULL);
            mqtt_client_register_connection_cb(on_mqtt_connection_changed, NULL);
            
            // Запуск MQTT клиента
            err = mqtt_client_start();
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to restart MQTT client: %s", esp_err_to_name(err));
            } else {
                ESP_LOGI(TAG, "MQTT reconnected successfully");
            }
        }
    }
    
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
    
    // Обработка команд для насоса питательных веществ
    if (strcmp(channel, "pump_nutrient") == 0) {
        if (strcmp(cmd, "run_pump") == 0) {
            cJSON *duration_item = cJSON_GetObjectItem(json, "duration_ms");
            if (cJSON_IsNumber(duration_item)) {
                int duration_ms = (int)cJSON_GetNumberValue(duration_item);
                ESP_LOGI(TAG, "Running pump_nutrient for %d ms", duration_ms);

                pump_driver_state_t pump_state;
                esp_err_t state_err = pump_driver_get_state(channel, &pump_state);

                cJSON *response = cJSON_CreateObject();
                if (response) {
                    cJSON_AddStringToObject(response, "cmd_id", cmd_id);

                    if (state_err != ESP_OK) {
                        cJSON_AddStringToObject(response, "status", "ERROR");
                        cJSON_AddStringToObject(response, "error_code", "pump_state_unavailable");
                        cJSON_AddStringToObject(response, "error_message", esp_err_to_name(state_err));
                    } else if (pump_state == PUMP_STATE_ON) {
                        cJSON_AddStringToObject(response, "status", "ERROR");
                        cJSON_AddStringToObject(response, "error_code", "pump_busy");
                        cJSON_AddStringToObject(response, "error_message", "Pump already running");
                    } else if (pump_state == PUMP_STATE_COOLDOWN) {
                        cJSON_AddStringToObject(response, "status", "ERROR");
                        cJSON_AddStringToObject(response, "error_code", "pump_cooldown");
                        cJSON_AddStringToObject(response, "error_message", "Pump is cooling down");
                    } else {
                        esp_err_t err = pump_driver_run(channel, duration_ms);
                        if (err == ESP_OK) {
                            cJSON_AddStringToObject(response, "status", "ACK");
                            cJSON_AddNumberToObject(response, "duration_ms", duration_ms);
                            ec_node_publish_pump_status(channel, "run_pump");
                        } else {
                            cJSON_AddStringToObject(response, "status", "ERROR");
                            cJSON_AddStringToObject(response, "error_code", "pump_driver_failed");
                            cJSON_AddStringToObject(response, "error_message", esp_err_to_name(err));
                        }
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
        } else if (strcmp(cmd, "stop_pump") == 0) {
            ESP_LOGI(TAG, "Stopping pump_nutrient");
            esp_err_t err = pump_driver_stop(channel);

            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                if (err == ESP_OK) {
                    cJSON_AddStringToObject(response, "status", "ACK");
                    ec_node_publish_pump_status(channel, "stop_pump");
                } else {
                    cJSON_AddStringToObject(response, "status", "ERROR");
                    cJSON_AddStringToObject(response, "error_code", "pump_driver_failed");
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
    } else if (strcmp(cmd, "calibrate") == 0) {
        // Команда калибровки EC
        cJSON *stage_item = cJSON_GetObjectItem(json, "stage");
        cJSON *tds_value_item = cJSON_GetObjectItem(json, "tds_value");
        
        if (!cJSON_IsNumber(stage_item) || !cJSON_IsNumber(tds_value_item)) {
            ESP_LOGE(TAG, "Invalid calibration command format");
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "invalid_format");
                cJSON_AddStringToObject(response, "error_message", "Missing stage or tds_value");
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
        uint16_t known_tds = (uint16_t)cJSON_GetNumberValue(tds_value_item);
        
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
        
        if (known_tds > 10000) {
            ESP_LOGE(TAG, "Invalid TDS value: %u (must be <= 10000)", known_tds);
            cJSON *response = cJSON_CreateObject();
            if (response) {
                cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                cJSON_AddStringToObject(response, "status", "ERROR");
                cJSON_AddStringToObject(response, "error_code", "invalid_tds");
                cJSON_AddStringToObject(response, "error_message", "TDS value must be <= 10000");
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
        
        ESP_LOGI(TAG, "Starting EC calibration: stage=%d, known_tds=%u ppm", stage, known_tds);
        
        bool cal_success = trema_ec_calibrate(stage, known_tds);
        
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            if (cal_success) {
                cJSON_AddStringToObject(response, "status", "ACK");
                cJSON_AddNumberToObject(response, "stage", stage);
                cJSON_AddNumberToObject(response, "known_tds", known_tds);
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

// Пример: обработка событий подключения MQTT
static void on_mqtt_connection_changed(bool connected, void *user_ctx) {
    if (connected) {
        ESP_LOGI(TAG, "MQTT connected - ec_node is online");
    } else {
        ESP_LOGW(TAG, "MQTT disconnected - ec_node is offline");
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
 * @brief Инициализация ec_node
 */
void ec_node_app_init(void) {
    ESP_LOGI(TAG, "Initializing ec_node...");
    
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
            .node_type_prefix = "EC",
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
    
    // Инициализация Trema EC-сенсора
    if (i2c_bus_is_initialized()) {
        ESP_LOGI(TAG, "Initializing Trema EC sensor...");
        if (trema_ec_init()) {
            ec_sensor_initialized = true;
            ESP_LOGI(TAG, "Trema EC sensor initialized successfully");
        } else {
            ESP_LOGW(TAG, "Failed to initialize Trema EC sensor, will retry later");
            ec_sensor_initialized = false;
        }
    } else {
        ESP_LOGW(TAG, "I²C bus not available, EC sensor initialization skipped");
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
        strncpy(node_id, "nd-ec-1", sizeof(node_id) - 1);
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
    
    // Инициализация pump_driver из NodeConfig
    err = pump_driver_init_from_config();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Pump driver initialized from config");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No pump channels found in config, pump driver not initialized");
    } else {
        ESP_LOGE(TAG, "Failed to initialize pump driver: %s", esp_err_to_name(err));
    }
    
    ESP_LOGI(TAG, "ec_node initialized");
    
    // Запуск FreeRTOS задач для опроса сенсоров и heartbeat
    ec_node_start_tasks();
}

/**
 * @brief Публикация телеметрии EC с реальными значениями от Trema EC-сенсора
 */
void ec_node_publish_telemetry_example(void) {
    if (!mqtt_client_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, skipping telemetry");
        return;
    }
    
    // Инициализация сенсора, если еще не инициализирован
    if (!ec_sensor_initialized && i2c_bus_is_initialized()) {
        if (trema_ec_init()) {
            ec_sensor_initialized = true;
            ESP_LOGI(TAG, "Trema EC sensor initialized");
        }
    }
    
    // Чтение значения EC
    float ec_value = NAN;
    bool read_success = false;
    bool using_stub = false;
    uint16_t tds_value = 0;
    
    if (ec_sensor_initialized) {
        read_success = trema_ec_read(&ec_value);
        using_stub = trema_ec_is_using_stub_values();
        
        if (!read_success || isnan(ec_value)) {
            ESP_LOGW(TAG, "Failed to read EC value, using stub");
            ec_value = 1.2f;  // Значение по умолчанию
            using_stub = true;
        } else {
            // Читаем TDS значение
            tds_value = trema_ec_get_tds();
        }
    } else {
        ESP_LOGW(TAG, "EC sensor not initialized, using stub value");
        ec_value = 1.2f;
        tds_value = 800;
        using_stub = true;
    }
    
    // Получение node_id из конфига
    char node_id[64];
    if (config_storage_get_node_id(node_id, sizeof(node_id)) != ESP_OK) {
        strncpy(node_id, "nd-ec-1", sizeof(node_id) - 1);
    }
    
    // Формат согласно MQTT_SPEC_FULL.md раздел 3.2
    cJSON *telemetry = cJSON_CreateObject();
    if (telemetry) {
        cJSON_AddStringToObject(telemetry, "node_id", node_id);
        cJSON_AddStringToObject(telemetry, "channel", "ec_sensor");
        cJSON_AddStringToObject(telemetry, "metric_type", "EC");
        cJSON_AddNumberToObject(telemetry, "value", ec_value);
        cJSON_AddNumberToObject(telemetry, "raw", (int)(ec_value * 1000));  // Сырое значение в тысячных
        cJSON_AddNumberToObject(telemetry, "tds", tds_value);  // TDS значение в ppm
        cJSON_AddBoolToObject(telemetry, "stub", using_stub);  // Флаг использования заглушки
        cJSON_AddNumberToObject(telemetry, "timestamp", (double)(esp_timer_get_time() / 1000000));
        
        char *json_str = cJSON_PrintUnformatted(telemetry);
        if (json_str) {
            mqtt_client_publish_telemetry("ec_sensor", json_str);
            free(json_str);
        }
        cJSON_Delete(telemetry);
    }
}

