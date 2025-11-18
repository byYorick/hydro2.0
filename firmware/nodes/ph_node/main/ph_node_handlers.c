/**
 * @file ph_node_handlers.c
 * @brief MQTT message handlers for ph_node
 * 
 * Объединяет обработчики:
 * - Config messages (NodeConfig)
 * - Command messages (команды управления насосами и другими каналами)
 */

#include "ph_node_handlers.h"
#include "ph_node_app.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "pump_control.h"
#include "trema_ph.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "ph_node_handlers";

// Helper function to send error response
static void send_command_error_response(const char *channel, const char *cmd_id, 
                                        const char *error_code, const char *error_message) {
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
        cJSON_AddStringToObject(response, "status", "ERROR");
        cJSON_AddStringToObject(response, "error_code", error_code);
        cJSON_AddStringToObject(response, "error_message", error_message);
        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
        
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            mqtt_manager_publish_command_response(channel, json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }
}

// Helper function to send success response
static void send_command_success_response(const char *channel, const char *cmd_id, cJSON *extra_data) {
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
        cJSON_AddStringToObject(response, "status", "ACK");
        cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));
        
        if (extra_data) {
            // Copy extra fields from extra_data
            cJSON *item = extra_data->child;
            while (item) {
                cJSON_AddItemToObject(response, item->string, cJSON_Duplicate(item, 1));
                item = item->next;
            }
        }
        
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            mqtt_manager_publish_command_response(channel, json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }
}

/**
 * @brief Handle MQTT config message
 */
void ph_node_config_handler(const char *topic, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Config received on %s: %.*s", topic, data_len, data);
    
    // Parse NodeConfig
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
                mqtt_manager_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    // Validate required fields
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
        ESP_LOGE(TAG, "Invalid config structure");
        cJSON_Delete(config);
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid config structure");
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
    
    // Validate config using config_storage
    char error_msg[256];
    esp_err_t validate_err = config_storage_validate(data, data_len, error_msg, sizeof(error_msg));
    if (validate_err != ESP_OK) {
        ESP_LOGE(TAG, "Config validation failed: %s", error_msg);
        cJSON_Delete(config);
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", error_msg);
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
    
    // Save config to NVS
    esp_err_t save_err = config_storage_save(data, data_len);
    if (save_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config: %s", esp_err_to_name(save_err));
        cJSON_Delete(config);
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Failed to save config");
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
    
    // Update node_id cache
    if (node_id_item && cJSON_IsString(node_id_item)) {
        ph_node_set_node_id(node_id_item->valuestring);
    }
    
    // Reload config from storage
    esp_err_t load_err = config_storage_load();
    if (load_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reload config: %s", esp_err_to_name(load_err));
    }
    
    ESP_LOGI(TAG, "Config saved and reloaded successfully");
    
    cJSON_Delete(config);
    
    // Graceful переподключение Wi-Fi при изменении параметров
    if (wifi_changed) {
        ESP_LOGI(TAG, "Wi-Fi config changed, reconnecting...");
        
        // Остановка MQTT перед переподключением Wi-Fi
        if (mqtt_manager_is_connected()) {
            mqtt_manager_stop();
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
        if (mqtt_manager_is_connected()) {
            mqtt_manager_stop();
            vTaskDelay(pdMS_TO_TICKS(500)); // Даем время на остановку
        }
        
        // Деинициализация MQTT менеджера
        mqtt_manager_deinit();
        vTaskDelay(pdMS_TO_TICKS(500));
        
        // Инициализация с новыми параметрами
        config_storage_mqtt_t new_mqtt_cfg;
        mqtt_manager_config_t mqtt_config;
        mqtt_node_info_t node_info;
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
            strncpy(node_id_buf, "nd-ph-1", sizeof(node_id_buf) - 1);
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
        
        esp_err_t err = mqtt_manager_init(&mqtt_config, &node_info);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to reinitialize MQTT manager: %s", esp_err_to_name(err));
        } else {
            // Регистрация callbacks (нужно получить из ph_node_init.c)
            extern void ph_node_config_handler(const char *topic, const char *data, int data_len, void *user_ctx);
            extern void ph_node_command_handler(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);
            extern void ph_node_mqtt_connection_cb(bool connected, void *user_ctx);
            
            mqtt_manager_register_config_cb(ph_node_config_handler, NULL);
            mqtt_manager_register_command_cb(ph_node_command_handler, NULL);
            mqtt_manager_register_connection_cb(ph_node_mqtt_connection_cb, NULL);
            
            // Запуск MQTT менеджера
            err = mqtt_manager_start();
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to restart MQTT manager: %s", esp_err_to_name(err));
            } else {
                ESP_LOGI(TAG, "MQTT reconnected successfully");
            }
        }
    }
    
    // Send success response
    cJSON *success_response = cJSON_CreateObject();
    if (success_response) {
        cJSON_AddStringToObject(success_response, "status", "OK");
        cJSON_AddNumberToObject(success_response, "timestamp", (double)(esp_timer_get_time() / 1000000));
        char *json_str = cJSON_PrintUnformatted(success_response);
        if (json_str) {
            mqtt_manager_publish_config_response(json_str);
            free(json_str);
        }
        cJSON_Delete(success_response);
    }
}

/**
 * @brief Handle MQTT command message
 */
void ph_node_command_handler(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    ESP_LOGI(TAG, "Command received on %s, channel: %s", topic, channel);
    
    // Parse command JSON
    cJSON *cmd = cJSON_ParseWithLength(data, data_len);
    if (!cmd) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    // Extract command ID and command type
    cJSON *cmd_id_item = cJSON_GetObjectItem(cmd, "cmd_id");
    cJSON *cmd_item = cJSON_GetObjectItem(cmd, "cmd");
    
    if (!cmd_id_item || !cJSON_IsString(cmd_id_item) || !cmd_item || !cJSON_IsString(cmd_item)) {
        ESP_LOGE(TAG, "Invalid command format: missing cmd_id or cmd");
        cJSON_Delete(cmd);
        return;
    }
    
    const char *cmd_id = cmd_id_item->valuestring;
    const char *cmd_type = cmd_item->valuestring;
    
    ESP_LOGI(TAG, "Processing command: %s (cmd_id: %s)", cmd_type, cmd_id);
    
    // Handle pump commands
    if (strcmp(channel, "pump_acid") == 0 || strcmp(channel, "pump_base") == 0) {
        pump_id_t pump_id = (strcmp(channel, "pump_acid") == 0) ? PUMP_ACID : PUMP_BASE;
        
        if (!ph_node_is_pump_control_initialized()) {
            send_command_error_response(channel, cmd_id, "pump_not_initialized", 
                                       "Pump control not initialized");
            cJSON_Delete(cmd);
            return;
        }
        
        if (strcmp(cmd_type, "run_pump") == 0) {
            cJSON *duration_item = cJSON_GetObjectItem(cmd, "duration_ms");
            if (!duration_item || !cJSON_IsNumber(duration_item)) {
                send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                           "Missing or invalid duration_ms");
                cJSON_Delete(cmd);
                return;
            }
            
            uint32_t duration_ms = (uint32_t)cJSON_GetNumberValue(duration_item);
            esp_err_t err = pump_control_run(pump_id, duration_ms);
            
            if (err == ESP_OK) {
                send_command_success_response(channel, cmd_id, NULL);
            } else if (err == ESP_ERR_INVALID_STATE) {
                send_command_error_response(channel, cmd_id, "pump_busy", 
                                           "Pump is already running or in cooldown");
            } else {
                send_command_error_response(channel, cmd_id, "pump_error", 
                                           "Failed to start pump");
            }
        } else if (strcmp(cmd_type, "stop_pump") == 0) {
            esp_err_t err = pump_control_stop(pump_id);
            
            if (err == ESP_OK) {
                send_command_success_response(channel, cmd_id, NULL);
            } else {
                send_command_error_response(channel, cmd_id, "pump_error", 
                                           "Failed to stop pump");
            }
        } else if (strcmp(cmd_type, "dose") == 0) {
            cJSON *dose_item = cJSON_GetObjectItem(cmd, "dose_ml");
            if (!dose_item || !cJSON_IsNumber(dose_item)) {
                send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                           "Missing or invalid dose_ml");
                cJSON_Delete(cmd);
                return;
            }
            
            float dose_ml = (float)cJSON_GetNumberValue(dose_item);
            esp_err_t err = pump_control_dose(pump_id, dose_ml);
            
            if (err == ESP_OK) {
                send_command_success_response(channel, cmd_id, NULL);
            } else if (err == ESP_ERR_INVALID_STATE) {
                send_command_error_response(channel, cmd_id, "pump_busy", 
                                           "Pump is already running or in cooldown");
            } else {
                send_command_error_response(channel, cmd_id, "pump_error", 
                                           "Failed to dose pump");
            }
        } else if (strcmp(cmd_type, "set_state") == 0) {
            cJSON *state_item = cJSON_GetObjectItem(cmd, "state");
            if (!state_item || !cJSON_IsNumber(state_item)) {
                send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                           "Missing or invalid state");
                cJSON_Delete(cmd);
                return;
            }
            
            int state = (int)cJSON_GetNumberValue(state_item);
            esp_err_t err = pump_control_set_state(pump_id, state);
            
            if (err == ESP_OK) {
                send_command_success_response(channel, cmd_id, NULL);
            } else {
                send_command_error_response(channel, cmd_id, "pump_error", 
                                           "Failed to set pump state");
            }
        } else {
            send_command_error_response(channel, cmd_id, "unknown_command", 
                                       "Unknown command type");
        }
    } else if (strcmp(channel, "ph_sensor") == 0) {
        // Handle pH sensor commands (calibration, etc.)
        if (strcmp(cmd_type, "calibrate") == 0) {
            cJSON *stage_item = cJSON_GetObjectItem(cmd, "stage");
            cJSON *known_ph_item = cJSON_GetObjectItem(cmd, "known_ph");
            
            if (!stage_item || !cJSON_IsNumber(stage_item) || 
                !known_ph_item || !cJSON_IsNumber(known_ph_item)) {
                send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                           "Missing or invalid stage/known_ph");
                cJSON_Delete(cmd);
                return;
            }
            
            uint8_t stage = (uint8_t)cJSON_GetNumberValue(stage_item);
            float known_ph = (float)cJSON_GetNumberValue(known_ph_item);
            
            if (trema_ph_calibrate(stage, known_ph)) {
                send_command_success_response(channel, cmd_id, NULL);
            } else {
                send_command_error_response(channel, cmd_id, "calibration_failed", 
                                           "Failed to calibrate pH sensor");
            }
        } else {
            send_command_error_response(channel, cmd_id, "unknown_command", 
                                       "Unknown command type for ph_sensor");
        }
    } else {
        ESP_LOGW(TAG, "Unknown channel: %s", channel);
        send_command_error_response(channel, cmd_id, "unknown_channel", 
                                   "Unknown channel");
    }
    
    cJSON_Delete(cmd);
}

