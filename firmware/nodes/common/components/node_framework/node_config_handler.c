/**
 * @file node_config_handler.c
 * @brief Реализация обработчика NodeConfig
 */

#include "node_config_handler.h"
#include "node_framework.h"
#include "config_storage.h"
#include "config_apply.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static const char *TAG = "node_config_handler";

// Глобальная ссылка на callback для инициализации каналов
static node_config_channel_callback_t s_channel_init_cb = NULL;
static void *s_channel_init_ctx = NULL;

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

    ESP_LOGI(TAG, "Config received on %s: %.*s", topic ? topic : "NULL", data_len, data);

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

    // Применение конфигурации
    esp_err_t apply_err = node_config_handler_apply(config, previous_config);
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
    // Компоненты будут добавлены в result через config_apply
    config_apply_result_t result;
    config_apply_result_init(&result);
    
    // Собираем список перезапущенных компонентов
    const char *restarted[CONFIG_APPLY_MAX_COMPONENTS];
    size_t restarted_count = 0;
    
    // Добавляем компоненты из result (если они есть)
    // Пока используем базовый список
    if (restarted_count == 0) {
        restarted[0] = "config_storage";
        restarted_count = 1;
    }
    
    node_config_handler_publish_response("ACK", NULL, restarted, restarted_count);

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
    config_apply_result_t result;
    config_apply_result_init(&result);

    // Применение Wi-Fi конфига
    err = config_apply_wifi(config, previous_config, &result);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to apply Wi-Fi config: %s", esp_err_to_name(err));
    }

    // Применение насосов (после инициализации каналов через callback)
    err = config_apply_channels_pump(&result);
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
    cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));

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

