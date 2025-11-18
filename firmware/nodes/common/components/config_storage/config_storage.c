/**
 * @file config_storage.c
 * @brief Реализация хранения и загрузки NodeConfig из NVS
 * 
 * Согласно firmware/NODE_CONFIG_SPEC.md раздел 6
 */

#include "config_storage.h"
#include "esp_log.h"
#include "nvs.h"
#include "cJSON.h"
#include <string.h>

static const char *TAG = "config_storage";
static const char *NVS_NAMESPACE = "node_config";
static const char *NVS_KEY = "config";

// Внутренний буфер для хранения JSON конфигурации
static char s_config_json[CONFIG_STORAGE_MAX_JSON_SIZE] = {0};
static bool s_config_loaded = false;
static nvs_handle_t s_nvs_handle = 0;

esp_err_t config_storage_init(void) {
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace: %s", esp_err_to_name(err));
        return err;
    }
    
    ESP_LOGI(TAG, "Config storage initialized");
    return ESP_OK;
}

esp_err_t config_storage_load(void) {
    if (s_nvs_handle == 0) {
        ESP_LOGE(TAG, "Config storage not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    size_t required_size = sizeof(s_config_json);
    esp_err_t err = nvs_get_str(s_nvs_handle, NVS_KEY, s_config_json, &required_size);
    
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "NodeConfig not found in NVS");
        s_config_loaded = false;
        return ESP_ERR_NOT_FOUND;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read NodeConfig from NVS: %s", esp_err_to_name(err));
        s_config_loaded = false;
        return err;
    }
    
    // Валидация загруженного JSON
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Failed to parse NodeConfig JSON");
        s_config_loaded = false;
        return ESP_FAIL;
    }
    
    cJSON_Delete(config);
    s_config_loaded = true;
    ESP_LOGI(TAG, "NodeConfig loaded from NVS");
    return ESP_OK;
}

esp_err_t config_storage_save(const char *json_config, size_t json_len) {
    if (s_nvs_handle == 0) {
        ESP_LOGE(TAG, "Config storage not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    if (json_config == NULL || json_len == 0) {
        ESP_LOGE(TAG, "Invalid JSON config");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (json_len >= sizeof(s_config_json)) {
        ESP_LOGE(TAG, "JSON config too large: %d bytes (max: %d)", json_len, sizeof(s_config_json) - 1);
        return ESP_ERR_INVALID_SIZE;
    }
    
    // Валидация перед сохранением
    esp_err_t err = config_storage_validate(json_config, json_len, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Config validation failed");
        return err;
    }
    
    // Сохранение в NVS
    err = nvs_set_str(s_nvs_handle, NVS_KEY, json_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save NodeConfig to NVS: %s", esp_err_to_name(err));
        return err;
    }
    
    err = nvs_commit(s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to commit NVS: %s", esp_err_to_name(err));
        return err;
    }
    
    // Обновление внутреннего буфера
    strncpy(s_config_json, json_config, sizeof(s_config_json) - 1);
    s_config_json[sizeof(s_config_json) - 1] = '\0';
    s_config_loaded = true;
    
    ESP_LOGI(TAG, "NodeConfig saved to NVS");
    return ESP_OK;
}

bool config_storage_exists(void) {
    if (s_nvs_handle == 0) {
        return false;
    }
    
    size_t required_size = 0;
    esp_err_t err = nvs_get_str(s_nvs_handle, NVS_KEY, NULL, &required_size);
    return (err == ESP_OK);
}

esp_err_t config_storage_get_json(char *buffer, size_t buffer_size) {
    if (buffer == NULL || buffer_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!s_config_loaded) {
        return ESP_ERR_NOT_FOUND;
    }
    
    size_t copy_size = (strlen(s_config_json) < buffer_size - 1) ? 
                       strlen(s_config_json) : buffer_size - 1;
    strncpy(buffer, s_config_json, copy_size);
    buffer[copy_size] = '\0';
    
    return ESP_OK;
}

static esp_err_t get_json_string_field(const char *field_name, char *buffer, size_t buffer_size) {
    if (!s_config_loaded) {
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        return ESP_FAIL;
    }
    
    cJSON *item = cJSON_GetObjectItem(config, field_name);
    if (item == NULL || !cJSON_IsString(item)) {
        cJSON_Delete(config);
        return ESP_ERR_NOT_FOUND;
    }
    
    strncpy(buffer, item->valuestring, buffer_size - 1);
    buffer[buffer_size - 1] = '\0';
    
    cJSON_Delete(config);
    return ESP_OK;
}

static esp_err_t get_json_number_field(const char *field_name, int *value) {
    if (!s_config_loaded) {
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        return ESP_FAIL;
    }
    
    cJSON *item = cJSON_GetObjectItem(config, field_name);
    if (item == NULL || !cJSON_IsNumber(item)) {
        cJSON_Delete(config);
        return ESP_ERR_NOT_FOUND;
    }
    
    *value = (int)cJSON_GetNumberValue(item);
    cJSON_Delete(config);
    return ESP_OK;
}

esp_err_t config_storage_get_node_id(char *node_id, size_t node_id_size) {
    return get_json_string_field("node_id", node_id, node_id_size);
}

esp_err_t config_storage_get_type(char *type, size_t type_size) {
    return get_json_string_field("type", type, type_size);
}

esp_err_t config_storage_get_version(int *version) {
    return get_json_number_field("version", version);
}

esp_err_t config_storage_get_gh_uid(char *gh_uid, size_t gh_uid_size) {
    return get_json_string_field("gh_uid", gh_uid, gh_uid_size);
}

esp_err_t config_storage_get_zone_uid(char *zone_uid, size_t zone_uid_size) {
    return get_json_string_field("zone_uid", zone_uid, zone_uid_size);
}

esp_err_t config_storage_get_mqtt(config_storage_mqtt_t *mqtt) {
    if (mqtt == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!s_config_loaded) {
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        return ESP_FAIL;
    }
    
    cJSON *mqtt_obj = cJSON_GetObjectItem(config, "mqtt");
    if (mqtt_obj == NULL || !cJSON_IsObject(mqtt_obj)) {
        cJSON_Delete(config);
        return ESP_ERR_NOT_FOUND;
    }
    
    // Заполнение структуры с значениями по умолчанию
    memset(mqtt, 0, sizeof(config_storage_mqtt_t));
    
    cJSON *item;
    if ((item = cJSON_GetObjectItem(mqtt_obj, "host")) && cJSON_IsString(item)) {
        strncpy(mqtt->host, item->valuestring, sizeof(mqtt->host) - 1);
    }
    
    if ((item = cJSON_GetObjectItem(mqtt_obj, "port")) && cJSON_IsNumber(item)) {
        mqtt->port = (uint16_t)cJSON_GetNumberValue(item);
    }
    
    if ((item = cJSON_GetObjectItem(mqtt_obj, "keepalive")) && cJSON_IsNumber(item)) {
        mqtt->keepalive = (uint16_t)cJSON_GetNumberValue(item);
    }
    
    if ((item = cJSON_GetObjectItem(mqtt_obj, "username")) && cJSON_IsString(item)) {
        strncpy(mqtt->username, item->valuestring, sizeof(mqtt->username) - 1);
    }
    
    if ((item = cJSON_GetObjectItem(mqtt_obj, "pass")) && cJSON_IsString(item)) {
        strncpy(mqtt->password, item->valuestring, sizeof(mqtt->password) - 1);
    }
    
    if ((item = cJSON_GetObjectItem(mqtt_obj, "tls")) && cJSON_IsBool(item)) {
        mqtt->use_tls = cJSON_IsTrue(item);
    }
    
    cJSON_Delete(config);
    return ESP_OK;
}

esp_err_t config_storage_get_wifi(config_storage_wifi_t *wifi) {
    if (wifi == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!s_config_loaded) {
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        return ESP_FAIL;
    }
    
    cJSON *wifi_obj = cJSON_GetObjectItem(config, "wifi");
    if (wifi_obj == NULL || !cJSON_IsObject(wifi_obj)) {
        cJSON_Delete(config);
        return ESP_ERR_NOT_FOUND;
    }
    
    // Заполнение структуры с значениями по умолчанию
    memset(wifi, 0, sizeof(config_storage_wifi_t));
    wifi->auto_reconnect = true;
    wifi->timeout_sec = 30;
    
    cJSON *item;
    if ((item = cJSON_GetObjectItem(wifi_obj, "ssid")) && cJSON_IsString(item)) {
        strncpy(wifi->ssid, item->valuestring, sizeof(wifi->ssid) - 1);
    }
    
    if ((item = cJSON_GetObjectItem(wifi_obj, "pass")) && cJSON_IsString(item)) {
        strncpy(wifi->password, item->valuestring, sizeof(wifi->password) - 1);
    }
    
    if ((item = cJSON_GetObjectItem(wifi_obj, "auto_reconnect")) && cJSON_IsBool(item)) {
        wifi->auto_reconnect = cJSON_IsTrue(item);
    }
    
    if ((item = cJSON_GetObjectItem(wifi_obj, "timeout_sec")) && cJSON_IsNumber(item)) {
        wifi->timeout_sec = (uint16_t)cJSON_GetNumberValue(item);
    }
    
    cJSON_Delete(config);
    return ESP_OK;
}

esp_err_t config_storage_validate(const char *json_config, size_t json_len,
                                  char *error_msg, size_t error_msg_size) {
    if (json_config == NULL || json_len == 0) {
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Invalid JSON config", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    cJSON *config = cJSON_ParseWithLength(json_config, json_len);
    if (config == NULL) {
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Invalid JSON format", error_msg_size - 1);
        }
        return ESP_FAIL;
    }
    
    // Проверка обязательных полей согласно NODE_CONFIG_SPEC.md
    cJSON *node_id = cJSON_GetObjectItem(config, "node_id");
    cJSON *version = cJSON_GetObjectItem(config, "version");
    cJSON *type = cJSON_GetObjectItem(config, "type");
    cJSON *gh_uid = cJSON_GetObjectItem(config, "gh_uid");
    cJSON *zone_uid = cJSON_GetObjectItem(config, "zone_uid");
    cJSON *channels = cJSON_GetObjectItem(config, "channels");
    cJSON *wifi = cJSON_GetObjectItem(config, "wifi");
    cJSON *mqtt = cJSON_GetObjectItem(config, "mqtt");
    
    if (!cJSON_IsString(node_id)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid node_id", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsNumber(version)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid version", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsString(type)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid type", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsString(gh_uid)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid gh_uid", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsString(zone_uid)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid zone_uid", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsArray(channels)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid channels", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsObject(wifi)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid wifi", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!cJSON_IsObject(mqtt)) {
        cJSON_Delete(config);
        if (error_msg && error_msg_size > 0) {
            strncpy(error_msg, "Missing or invalid mqtt", error_msg_size - 1);
        }
        return ESP_ERR_INVALID_ARG;
    }
    
    cJSON_Delete(config);
    return ESP_OK;
}

void config_storage_deinit(void) {
    if (s_nvs_handle != 0) {
        nvs_close(s_nvs_handle);
        s_nvs_handle = 0;
    }
    s_config_loaded = false;
    memset(s_config_json, 0, sizeof(s_config_json));
}

