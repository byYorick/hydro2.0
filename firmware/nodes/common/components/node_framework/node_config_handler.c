/**
 * @file node_config_handler.c
 * @brief Реализация обработчика NodeConfig
 */

#include "node_config_handler.h"
#include "node_framework.h"
#include "node_utils.h"
#include "config_storage.h"
#include "config_apply.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

// Forward declarations для типов из mqtt_manager.h
typedef void (*mqtt_config_callback_t)(const char *topic, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_command_callback_t)(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);
typedef void (*mqtt_connection_callback_t)(bool connected, void *user_ctx);

static const char *TAG = "node_config_handler";

// Глобальная ссылка на callback для инициализации каналов
static node_config_channel_callback_t s_channel_init_cb = NULL;
static void *s_channel_init_ctx = NULL;

// Глобальные ссылки на MQTT callbacks для config_apply_mqtt
static mqtt_config_callback_t s_mqtt_config_cb = NULL;
static mqtt_command_callback_t s_mqtt_command_cb = NULL;
static mqtt_connection_callback_t s_mqtt_connection_cb = NULL;
static void *s_mqtt_user_ctx = NULL;
static const char *s_default_node_id = NULL;
static const char *s_default_gh_uid = NULL;
static const char *s_default_zone_uid = NULL;

/**
 * @brief Маскирует секретные поля в JSON перед логированием
 * 
 * @param json_str Исходная JSON строка
 * @param masked_buf Буфер для маскированной строки
 * @param buf_size Размер буфера
 * @return true если успешно, false при ошибке
 */
static bool mask_sensitive_json_fields(const char *json_str, char *masked_buf, size_t buf_size) {
    if (json_str == NULL || masked_buf == NULL || buf_size == 0) {
        return false;
    }
    
    cJSON *json = cJSON_Parse(json_str);
    if (json == NULL) {
        // Если не удалось распарсить, просто копируем строку (может быть не JSON)
        strncpy(masked_buf, json_str, buf_size - 1);
        masked_buf[buf_size - 1] = '\0';
        return true;
    }
    
    // Маскируем секретные поля
    const char *sensitive_fields[] = {"password", "pass", "pin", "token", "secret"};
    const size_t num_fields = sizeof(sensitive_fields) / sizeof(sensitive_fields[0]);
    
    for (size_t i = 0; i < num_fields; i++) {
        cJSON *item = cJSON_GetObjectItem(json, sensitive_fields[i]);
        if (item != NULL && cJSON_IsString(item)) {
            cJSON_SetValuestring(item, "[MASKED]");
        }
        
        // Также проверяем вложенные объекты (wifi.password, mqtt.password и т.д.)
        cJSON *wifi = cJSON_GetObjectItem(json, "wifi");
        if (wifi != NULL && cJSON_IsObject(wifi)) {
            cJSON *wifi_item = cJSON_GetObjectItem(wifi, sensitive_fields[i]);
            if (wifi_item != NULL && cJSON_IsString(wifi_item)) {
                cJSON_SetValuestring(wifi_item, "[MASKED]");
            }
        }
        
        cJSON *mqtt = cJSON_GetObjectItem(json, "mqtt");
        if (mqtt != NULL && cJSON_IsObject(mqtt)) {
            cJSON *mqtt_item = cJSON_GetObjectItem(mqtt, sensitive_fields[i]);
            if (mqtt_item != NULL && cJSON_IsString(mqtt_item)) {
                cJSON_SetValuestring(mqtt_item, "[MASKED]");
            }
        }
    }
    
    char *masked_json = cJSON_PrintUnformatted(json);
    if (masked_json != NULL) {
        strncpy(masked_buf, masked_json, buf_size - 1);
        masked_buf[buf_size - 1] = '\0';
        free(masked_json);
        cJSON_Delete(json);
        return true;
    }
    
    cJSON_Delete(json);
    return false;
}

void node_config_handler_process(
    const char *topic,
    const char *data,
    int data_len,
    void *user_ctx
) {
    if (data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid config parameters");
        node_config_handler_publish_response("ERROR", "Invalid parameters", NULL, 0);
        return;
    }

    // Безопасность: маскируем секретные поля перед логированием
    char masked_data[2048] = {0};
    if (data_len < sizeof(masked_data) && mask_sensitive_json_fields(data, masked_data, sizeof(masked_data))) {
        ESP_LOGI(TAG, "Config received on %s: %s", topic ? topic : "NULL", masked_data);
    } else {
        // Если не удалось замаскировать, логируем только топик и длину
        ESP_LOGI(TAG, "Config received on %s: [%d bytes]", topic ? topic : "NULL", data_len);
    }

    // Парсинг JSON
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        node_config_handler_publish_response("ERROR", "Invalid JSON", NULL, 0);
        return;
    }

    // Валидация
    char error_msg[256];
    esp_err_t validate_err = node_config_handler_validate(config, error_msg, sizeof(error_msg));
    if (validate_err != ESP_OK) {
        ESP_LOGE(TAG, "Config validation failed: %s", error_msg);
        cJSON_Delete(config);
        node_config_handler_publish_response("ERROR", error_msg, NULL, 0);
        return;
    }

    // Загрузка предыдущего конфига
    cJSON *previous_config = config_apply_load_previous_config();

    // Применение конфигурации с получением результата о перезапущенных компонентах
    config_apply_result_t result;
    config_apply_result_init(&result);
    
    esp_err_t apply_err = node_config_handler_apply_with_result(config, previous_config, &result);
    if (apply_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to apply config: %s", esp_err_to_name(apply_err));
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        node_config_handler_publish_response("ERROR", "Failed to apply config", NULL, 0);
        return;
    }

    // Успешное применение - публикуем ACK с информацией о перезапущенных компонентах
    // Используем result из config_apply
    const char *restarted[CONFIG_APPLY_MAX_COMPONENTS];
    size_t restarted_count = 0;
    
    // Копируем компоненты из result
    for (size_t i = 0; i < result.count && i < CONFIG_APPLY_MAX_COMPONENTS; i++) {
        restarted[i] = result.components[i];
        restarted_count++;
    }
    
    // Если ничего не перезапускалось, публикуем пустой массив
    node_config_handler_publish_response("ACK", NULL, 
                                         restarted_count > 0 ? restarted : NULL, 
                                         restarted_count);

    cJSON_Delete(config);
    if (previous_config) {
        cJSON_Delete(previous_config);
    }
}

esp_err_t node_config_handler_validate(
    const cJSON *config,
    char *error_msg,
    size_t error_msg_size
) {
    if (config == NULL || error_msg == NULL || error_msg_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    // Проверка обязательных полей
    cJSON *node_id = cJSON_GetObjectItem(config, "node_id");
    cJSON *version = cJSON_GetObjectItem(config, "version");
    cJSON *type = cJSON_GetObjectItem(config, "type");
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    cJSON *mqtt = cJSON_GetObjectItem(config, "mqtt");

    if (!cJSON_IsString(node_id)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid node_id");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsNumber(version)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid version");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsString(type)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid type");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsArray(channels)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid channels");
        return ESP_ERR_INVALID_ARG;
    }

    if (!cJSON_IsObject(mqtt)) {
        snprintf(error_msg, error_msg_size, "Missing or invalid mqtt");
        return ESP_ERR_INVALID_ARG;
    }

    // Валидация обязательных MQTT полей
    cJSON *mqtt_host = cJSON_GetObjectItem(mqtt, "host");
    if (!cJSON_IsString(mqtt_host) || mqtt_host->valuestring == NULL || mqtt_host->valuestring[0] == '\0') {
        snprintf(error_msg, error_msg_size, "Missing or invalid mqtt.host");
        return ESP_ERR_INVALID_ARG;
    }
    
    cJSON *mqtt_port = cJSON_GetObjectItem(mqtt, "port");
    if (!cJSON_IsNumber(mqtt_port) || cJSON_GetNumberValue(mqtt_port) <= 0 || cJSON_GetNumberValue(mqtt_port) > 65535) {
        snprintf(error_msg, error_msg_size, "Missing or invalid mqtt.port (must be 1-65535)");
        return ESP_ERR_INVALID_ARG;
    }
    
    cJSON *mqtt_keepalive = cJSON_GetObjectItem(mqtt, "keepalive");
    if (mqtt_keepalive != NULL && (!cJSON_IsNumber(mqtt_keepalive) || cJSON_GetNumberValue(mqtt_keepalive) <= 0 || cJSON_GetNumberValue(mqtt_keepalive) > 65535)) {
        snprintf(error_msg, error_msg_size, "Invalid mqtt.keepalive (must be 1-65535)");
        return ESP_ERR_INVALID_ARG;
    }

    // Дополнительная валидация через config_storage
    char *json_str = cJSON_PrintUnformatted(config);
    if (json_str) {
        char storage_error_msg[128];
        esp_err_t err = config_storage_validate(json_str, strlen(json_str), 
                                               storage_error_msg, sizeof(storage_error_msg));
        free(json_str);
        
        if (err != ESP_OK) {
            snprintf(error_msg, error_msg_size, "%s", storage_error_msg);
            return err;
        }
    }

    return ESP_OK;
}

esp_err_t node_config_handler_apply(
    const cJSON *config,
    const cJSON *previous_config
) {
    return node_config_handler_apply_with_result(config, previous_config, NULL);
}

esp_err_t node_config_handler_apply_with_result(
    const cJSON *config,
    const cJSON *previous_config,
    config_apply_result_t *result
) {
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // Сохранение конфига в NVS
    char *json_str = cJSON_PrintUnformatted(config);
    if (!json_str) {
        ESP_LOGE(TAG, "Failed to serialize config to JSON");
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = config_storage_save(json_str, strlen(json_str));
    free(json_str);

    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config to NVS: %s", esp_err_to_name(err));
        return err;
    }

    // Применение через config_apply
    config_apply_result_t local_result;
    config_apply_result_t *result_ptr = result ? result : &local_result;
    config_apply_result_init(result_ptr);

    // Подготовка MQTT параметров (если callbacks зарегистрированы)
    const config_apply_mqtt_params_t *mqtt_params = NULL;
    config_apply_mqtt_params_t mqtt_params_local = {0};
    if (s_mqtt_config_cb || s_mqtt_command_cb || s_mqtt_connection_cb) {
        mqtt_params_local = (config_apply_mqtt_params_t){
            .default_node_id = s_default_node_id ? s_default_node_id : "nd-unknown",
            .default_gh_uid = s_default_gh_uid ? s_default_gh_uid : "gh-1",
            .default_zone_uid = s_default_zone_uid ? s_default_zone_uid : "zn-1",
            .config_cb = s_mqtt_config_cb,
            .command_cb = s_mqtt_command_cb,
            .connection_cb = s_mqtt_connection_cb,
            .user_ctx = s_mqtt_user_ctx,
        };
        mqtt_params = &mqtt_params_local;
    }

    // Применение Wi-Fi конфига с автоматическим рестартом MQTT
    if (mqtt_params != NULL) {
        err = config_apply_wifi_with_mqtt_restart(config, previous_config, mqtt_params, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply Wi-Fi config: %s", esp_err_to_name(err));
        }
    } else {
        err = config_apply_wifi(config, previous_config, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply Wi-Fi config: %s", esp_err_to_name(err));
        }
    }

    // Применение MQTT конфига (если callbacks зарегистрированы)
    // Это нужно для случаев, когда меняются именно MQTT настройки (не Wi-Fi)
    if (mqtt_params != NULL) {
        err = config_apply_mqtt(config, previous_config, mqtt_params, result_ptr);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to apply MQTT config: %s", esp_err_to_name(err));
        }
    } else {
        ESP_LOGW(TAG, "MQTT callbacks not registered, skipping MQTT config apply");
    }

    // Применение насосов (после инициализации каналов через callback)
    err = config_apply_channels_pump(result_ptr);
    if (err != ESP_OK && err != ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "Failed to apply pump channels: %s", esp_err_to_name(err));
    }

    // Инициализация каналов через callback
    if (s_channel_init_cb) {
        cJSON *channels = cJSON_GetObjectItem(config, "channels");
        if (cJSON_IsArray(channels)) {
            cJSON *channel = NULL;
            cJSON_ArrayForEach(channel, channels) {
                if (cJSON_IsObject(channel)) {
                    cJSON *name = cJSON_GetObjectItem(channel, "name");
                    if (cJSON_IsString(name)) {
                        esp_err_t channel_err = s_channel_init_cb(
                            name->valuestring,
                            channel,
                            s_channel_init_ctx
                        );
                        if (channel_err != ESP_OK) {
                            ESP_LOGW(TAG, "Failed to init channel %s: %s", 
                                    name->valuestring, esp_err_to_name(channel_err));
                        }
                    }
                }
            }
        }
    }

    return ESP_OK;
}

esp_err_t node_config_handler_publish_response(
    const char *status,
    const char *error_msg,
    const char **restarted_components,
    size_t component_count
) {
    cJSON *response = cJSON_CreateObject();
    if (!response) {
        return ESP_ERR_NO_MEM;
    }

    cJSON_AddStringToObject(response, "status", status);
    cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());

    if (error_msg && strcmp(status, "ERROR") == 0) {
        cJSON_AddStringToObject(response, "error", error_msg);
    }

    if (restarted_components && component_count > 0 && strcmp(status, "ACK") == 0) {
        cJSON *restarted = cJSON_CreateArray();
        if (restarted) {
            for (size_t i = 0; i < component_count; i++) {
                cJSON_AddItemToArray(restarted, cJSON_CreateString(restarted_components[i]));
            }
            cJSON_AddItemToObject(response, "restarted", restarted);
        }
    }

    char *json_str = cJSON_PrintUnformatted(response);
    if (json_str) {
        esp_err_t err = mqtt_manager_publish_config_response(json_str);
        free(json_str);
        cJSON_Delete(response);
        return err;
    }

    cJSON_Delete(response);
    return ESP_ERR_NO_MEM;
}

// Функция для регистрации callback инициализации каналов (используется из node_framework)
// Объявлена в node_framework.h, реализована здесь
void node_config_handler_set_channel_init_callback(
    node_config_channel_callback_t callback,
    void *user_ctx
) {
    s_channel_init_cb = callback;
    s_channel_init_ctx = user_ctx;
}

void node_config_handler_set_mqtt_callbacks(
    mqtt_config_callback_t config_cb,
    mqtt_command_callback_t command_cb,
    mqtt_connection_callback_t connection_cb,
    void *user_ctx,
    const char *default_node_id,
    const char *default_gh_uid,
    const char *default_zone_uid
) {
    s_mqtt_config_cb = config_cb;
    s_mqtt_command_cb = command_cb;
    s_mqtt_connection_cb = connection_cb;
    s_mqtt_user_ctx = user_ctx;
    s_default_node_id = default_node_id;
    s_default_gh_uid = default_gh_uid;
    s_default_zone_uid = default_zone_uid;
}

