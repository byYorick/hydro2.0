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
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <strings.h>

static const char *TAG = "config_storage";
static const char *NVS_NAMESPACE = "node_config";
static const char *NVS_KEY = "config";
static const char *NVS_TEMP_KEY = "last_temp";

// Внутренний буфер для хранения JSON конфигурации
static char s_config_json[CONFIG_STORAGE_MAX_JSON_SIZE] = {0};
static bool s_config_loaded = false;
static nvs_handle_t s_nvs_handle = 0;
static SemaphoreHandle_t s_config_mutex = NULL;

static bool config_storage_lock(void) {
    if (s_config_mutex == NULL) {
        return false;
    }
    return (xSemaphoreTake(s_config_mutex, pdMS_TO_TICKS(2000)) == pdTRUE);
}

static void config_storage_unlock(void) {
    if (s_config_mutex != NULL) {
        xSemaphoreGive(s_config_mutex);
    }
}

esp_err_t config_storage_init(void) {
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace: %s", esp_err_to_name(err));
        return err;
    }

    if (s_config_mutex == NULL) {
        s_config_mutex = xSemaphoreCreateMutex();
        if (s_config_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create config storage mutex");
            return ESP_ERR_NO_MEM;
        }
    }
    
    ESP_LOGI(TAG, "Config storage initialized");
    return ESP_OK;
}

esp_err_t config_storage_load(void) {
    if (s_nvs_handle == 0) {
        ESP_LOGE(TAG, "Config storage not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (!config_storage_lock()) {
        ESP_LOGE(TAG, "Failed to lock config storage");
        return ESP_ERR_TIMEOUT;
    }
    
    size_t required_size = sizeof(s_config_json);
    esp_err_t err = nvs_get_str(s_nvs_handle, NVS_KEY, s_config_json, &required_size);
    
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "NodeConfig not found in NVS");
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read NodeConfig from NVS: %s", esp_err_to_name(err));
        s_config_loaded = false;
        config_storage_unlock();
        return err;
    }
    
    // Логируем размер загруженного конфига для диагностики
    ESP_LOGI(TAG, "Config loaded from NVS: %zu bytes", strlen(s_config_json));
    
    // Логируем первые 100 символов конфига для диагностики (безопасно, так как это JSON)
    if (strlen(s_config_json) > 0) {
        size_t preview_len = strlen(s_config_json) > 100 ? 100 : strlen(s_config_json);
        char preview[101] = {0};
        strncpy(preview, s_config_json, preview_len);
        preview[preview_len] = '\0';
        ESP_LOGI(TAG, "Config preview (first %zu chars): %s...", preview_len, preview);
    }
    
    // Валидация загруженного JSON (базовая проверка парсинга)
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "Failed to parse NodeConfig JSON - config may be corrupted");
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    // КРИТИЧНО: Проверяем наличие обязательных полей для минимальной валидности
    // Это необходимо, чтобы конфигурация, сохраненная в setup mode, корректно загружалась
    cJSON *wifi = cJSON_GetObjectItem(config, "wifi");
    cJSON *mqtt = cJSON_GetObjectItem(config, "mqtt");
    
    // Проверяем, что есть хотя бы WiFi или MQTT для работы системы
    // Если нет ни того, ни другого - конфигурация невалидна
    bool has_wifi = (wifi != NULL && cJSON_IsObject(wifi));
    bool has_mqtt = (mqtt != NULL && cJSON_IsObject(mqtt));
    
    if (!has_wifi && !has_mqtt) {
        ESP_LOGE(TAG, "Loaded config has neither WiFi nor MQTT configuration - invalid");
        cJSON_Delete(config);
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    // Если есть WiFi, проверяем наличие SSID для полноценной работы
    if (has_wifi) {
        cJSON *ssid = cJSON_GetObjectItem(wifi, "ssid");
        cJSON *configured = cJSON_GetObjectItem(wifi, "configured");
        bool wifi_configured = (configured != NULL && cJSON_IsBool(configured) && cJSON_IsTrue(configured));
        
        // Логируем состояние SSID для диагностики
        if (wifi_configured) {
            ESP_LOGI(TAG, "WiFi marked as configured, skipping SSID validation");
        } else if (!ssid) {
            ESP_LOGW(TAG, "WiFi config present but SSID field is missing - will trigger setup mode");
        } else if (!cJSON_IsString(ssid)) {
            ESP_LOGW(TAG, "WiFi config present but SSID is not a string (type=%d) - will trigger setup mode", ssid->type);
        } else if (ssid->valuestring == NULL) {
            ESP_LOGW(TAG, "WiFi config present but SSID value is NULL - will trigger setup mode");
        } else if (strlen(ssid->valuestring) == 0) {
            ESP_LOGW(TAG, "WiFi config present but SSID is empty string - will trigger setup mode");
            // КРИТИЧНО: Если SSID пустой, это может быть коррумпированный конфиг
            // Логируем часть конфига для диагностики
            char *config_preview = cJSON_Print(config);
            if (config_preview) {
                size_t preview_len = strlen(config_preview);
                if (preview_len > 200) {
                    config_preview[200] = '\0';
                    ESP_LOGE(TAG, "Config preview (first 200 chars): %s...", config_preview);
                } else {
                    ESP_LOGE(TAG, "Config preview: %s", config_preview);
                }
                free(config_preview);
            }
        } else {
            // SSID валиден
            ESP_LOGI(TAG, "WiFi SSID found in config: '%s' (len=%zu)", ssid->valuestring, strlen(ssid->valuestring));
        }
        
        if (!wifi_configured && (!ssid || !cJSON_IsString(ssid) || ssid->valuestring == NULL || strlen(ssid->valuestring) == 0)) {
            // Если SSID отсутствует или пустой, конфигурация неполная и нужно setup mode
            ESP_LOGW(TAG, "Invalid WiFi config detected - clearing corrupted config from NVS");
            
            // КРИТИЧНО: Удаляем коррумпированный конфиг из NVS, чтобы не зацикливаться на setup mode
            esp_err_t del_err = nvs_erase_key(s_nvs_handle, NVS_KEY);
            if (del_err == ESP_OK) {
                nvs_commit(s_nvs_handle);
                ESP_LOGI(TAG, "Corrupted config erased from NVS - setup mode will create new config");
            } else {
                ESP_LOGW(TAG, "Failed to erase corrupted config from NVS: %s", esp_err_to_name(del_err));
            }
            
            cJSON_Delete(config);
            s_config_loaded = false;
            config_storage_unlock();
            return ESP_FAIL;
        }
    }
    
    cJSON_Delete(config);
    s_config_loaded = true;
    ESP_LOGI(TAG, "NodeConfig loaded from NVS (WiFi: %s, MQTT: %s)", 
             has_wifi ? "yes" : "no", has_mqtt ? "yes" : "no");
    config_storage_unlock();
    return ESP_OK;
}

esp_err_t config_storage_save(const char *json_config, size_t json_len) {
    if (s_nvs_handle == 0) {
        ESP_LOGE(TAG, "Config storage not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (!config_storage_lock()) {
        ESP_LOGE(TAG, "Failed to lock config storage");
        return ESP_ERR_TIMEOUT;
    }
    
    if (json_config == NULL || json_len == 0) {
        ESP_LOGE(TAG, "Invalid JSON config");
        config_storage_unlock();
        return ESP_ERR_INVALID_ARG;
    }
    
    if (json_len >= sizeof(s_config_json)) {
        ESP_LOGE(TAG, "JSON config too large: %d bytes (max: %d)", json_len, sizeof(s_config_json) - 1);
        config_storage_unlock();
        return ESP_ERR_INVALID_SIZE;
    }
    
    // Парсим новый конфиг для последующей нормализации (до валидации, чтобы можно было дорисовать недостающие поля)
    ESP_LOGI(TAG, "Parsing new config JSON (%zu bytes) for preservation check", json_len);
    cJSON *new_config = cJSON_Parse(json_config);
    if (new_config == NULL) {
        ESP_LOGE(TAG, "Failed to parse new config JSON");
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    cJSON *new_wifi = cJSON_GetObjectItem(new_config, "wifi");
    bool new_has_wifi = (new_wifi != NULL && cJSON_IsObject(new_wifi));
    bool new_has_valid_ssid = false;
    
    ESP_LOGI(TAG, "New config WiFi check: has_wifi=%s", new_has_wifi ? "yes" : "no");
    
    if (new_has_wifi) {
        cJSON *new_ssid = cJSON_GetObjectItem(new_wifi, "ssid");
        new_has_valid_ssid = (new_ssid != NULL && cJSON_IsString(new_ssid) && 
                             new_ssid->valuestring != NULL && strlen(new_ssid->valuestring) > 0);
        if (new_has_valid_ssid) {
            ESP_LOGI(TAG, "New config has valid WiFi SSID: '%s' (len=%zu)", 
                    new_ssid->valuestring, strlen(new_ssid->valuestring));
        } else {
            ESP_LOGW(TAG, "New config has WiFi section but SSID is invalid or empty");
        }
    }
    
    // КРИТИЧНО: Парсим старый конфиг один раз для сохранения WiFi и MQTT
    cJSON *old_config = NULL;
    if (s_config_loaded) {
        ESP_LOGI(TAG, "Old config is loaded, parsing for WiFi/MQTT preservation");
        old_config = cJSON_Parse(s_config_json);
        if (old_config == NULL) {
            ESP_LOGW(TAG, "Failed to parse old config JSON for preservation");
        }
    }
    
    // Если в новом конфиге нет валидного WiFi, пытаемся сохранить WiFi из старого конфига
    if (!new_has_valid_ssid && old_config != NULL) {
        ESP_LOGI(TAG, "New config has no valid WiFi, checking if old config has WiFi to preserve");
        cJSON *old_wifi = cJSON_GetObjectItem(old_config, "wifi");
        if (old_wifi != NULL && cJSON_IsObject(old_wifi)) {
            cJSON *old_ssid = cJSON_GetObjectItem(old_wifi, "ssid");
            if (old_ssid != NULL && cJSON_IsString(old_ssid) && 
                old_ssid->valuestring != NULL && strlen(old_ssid->valuestring) > 0) {
                // Сохраняем WiFi из старого конфига в новый
                ESP_LOGI(TAG, "Preserving WiFi config from existing config (SSID='%s', len=%zu)", 
                        old_ssid->valuestring, strlen(old_ssid->valuestring));
                
                // Удаляем существующую WiFi секцию из нового конфига (если есть)
                if (new_has_wifi) {
                    ESP_LOGI(TAG, "Removing invalid WiFi section from new config");
                    cJSON_DeleteItemFromObject(new_config, "wifi");
                }
                
                // Копируем WiFi секцию из старого конфига
                cJSON *wifi_copy = cJSON_Duplicate(old_wifi, 1);
                if (wifi_copy != NULL) {
                    cJSON_AddItemToObject(new_config, "wifi", wifi_copy);
                    ESP_LOGI(TAG, "WiFi config preserved in new config successfully");
                } else {
                    ESP_LOGE(TAG, "Failed to duplicate WiFi config from old config - memory error");
                    cJSON_Delete(old_config);
                    cJSON_Delete(new_config);
                    config_storage_unlock();
                    return ESP_ERR_NO_MEM;
                }
            } else {
                ESP_LOGW(TAG, "Old config has WiFi section but SSID is invalid or empty");
            }
        } else {
            ESP_LOGI(TAG, "Old config has no WiFi section to preserve");
        }
    } else if (!new_has_valid_ssid) {
        ESP_LOGI(TAG, "New config has no valid WiFi, but old config is not available");
    }
    
    // КРИТИЧНО: Аналогично проверяем MQTT конфиг - если в новом конфиге MQTT неполный или отсутствует,
    // сохраняем MQTT из старого конфига (если он есть)
    cJSON *new_mqtt = cJSON_GetObjectItem(new_config, "mqtt");
    bool new_has_mqtt = (new_mqtt != NULL && cJSON_IsObject(new_mqtt));
    bool new_has_valid_mqtt = false;
    
    ESP_LOGI(TAG, "New config MQTT check: has_mqtt=%s", new_has_mqtt ? "yes" : "no");
    
    if (new_has_mqtt) {
        cJSON *new_mqtt_host = cJSON_GetObjectItem(new_mqtt, "host");
        cJSON *new_mqtt_port = cJSON_GetObjectItem(new_mqtt, "port");
        new_has_valid_mqtt = (new_mqtt_host != NULL && cJSON_IsString(new_mqtt_host) && 
                             new_mqtt_host->valuestring != NULL && strlen(new_mqtt_host->valuestring) > 0 &&
                             new_mqtt_port != NULL && cJSON_IsNumber(new_mqtt_port));
        if (new_has_valid_mqtt) {
            ESP_LOGI(TAG, "New config has valid MQTT config: host='%s', port=%.0f", 
                    new_mqtt_host->valuestring, cJSON_GetNumberValue(new_mqtt_port));
        } else {
            ESP_LOGW(TAG, "New config has MQTT section but config is invalid or incomplete");
            if (new_mqtt_host) {
                ESP_LOGW(TAG, "  MQTT host: %s", cJSON_IsString(new_mqtt_host) && new_mqtt_host->valuestring ? new_mqtt_host->valuestring : "NULL");
            } else {
                ESP_LOGW(TAG, "  MQTT host field not found");
            }
        }
    }
    
    // Если в новом конфиге нет валидного MQTT, пытаемся сохранить MQTT из старого конфига
    if (!new_has_valid_mqtt && old_config != NULL) {
        ESP_LOGI(TAG, "New config has no valid MQTT, checking if old config has MQTT to preserve");
        cJSON *old_mqtt = cJSON_GetObjectItem(old_config, "mqtt");
        if (old_mqtt != NULL && cJSON_IsObject(old_mqtt)) {
            cJSON *old_mqtt_host = cJSON_GetObjectItem(old_mqtt, "host");
            cJSON *old_mqtt_port = cJSON_GetObjectItem(old_mqtt, "port");
            if (old_mqtt_host != NULL && cJSON_IsString(old_mqtt_host) && 
                old_mqtt_host->valuestring != NULL && strlen(old_mqtt_host->valuestring) > 0 &&
                old_mqtt_port != NULL && cJSON_IsNumber(old_mqtt_port)) {
                // Сохраняем MQTT из старого конфига в новый
                ESP_LOGI(TAG, "Preserving MQTT config from existing config (host='%s', port=%.0f)", 
                        old_mqtt_host->valuestring, cJSON_GetNumberValue(old_mqtt_port));
                
                // Удаляем существующую MQTT секцию из нового конфига (если есть)
                if (new_has_mqtt) {
                    ESP_LOGI(TAG, "Removing invalid MQTT section from new config");
                    cJSON_DeleteItemFromObject(new_config, "mqtt");
                }
                
                // Копируем MQTT секцию из старого конфига
                cJSON *mqtt_copy = cJSON_Duplicate(old_mqtt, 1);
                if (mqtt_copy != NULL) {
                    cJSON_AddItemToObject(new_config, "mqtt", mqtt_copy);
                    ESP_LOGI(TAG, "MQTT config preserved in new config successfully");
                } else {
                    ESP_LOGE(TAG, "Failed to duplicate MQTT config from old config - memory error");
                }
            } else {
                ESP_LOGW(TAG, "Old config has MQTT section but config is invalid or incomplete");
                if (old_mqtt_host) {
                    ESP_LOGW(TAG, "  Old MQTT host: %s", cJSON_IsString(old_mqtt_host) && old_mqtt_host->valuestring ? old_mqtt_host->valuestring : "NULL");
                } else {
                    ESP_LOGW(TAG, "  Old MQTT host field not found");
                }
            }
        } else {
            ESP_LOGI(TAG, "Old config has no MQTT section to preserve");
        }
    } else if (!new_has_valid_mqtt) {
        ESP_LOGI(TAG, "New config has no valid MQTT, but old config is not available");
    }
    
    // Сохраняем gh_uid/zone_uid из старого конфига, если новые отсутствуют
    bool new_has_valid_gh = false;
    bool new_has_valid_zone = false;

    cJSON *new_gh_uid = cJSON_GetObjectItem(new_config, "gh_uid");
    if (new_gh_uid && cJSON_IsString(new_gh_uid) && new_gh_uid->valuestring && strlen(new_gh_uid->valuestring) > 0) {
        new_has_valid_gh = true;
    } else {
        ESP_LOGW(TAG, "New config has invalid or missing gh_uid");
    }

    cJSON *new_zone_uid = cJSON_GetObjectItem(new_config, "zone_uid");
    if (new_zone_uid && cJSON_IsString(new_zone_uid) && new_zone_uid->valuestring && strlen(new_zone_uid->valuestring) > 0) {
        new_has_valid_zone = true;
    } else {
        ESP_LOGW(TAG, "New config has invalid or missing zone_uid");
    }

    const char *fallback_gh = NULL;
    const char *fallback_zone = NULL;

    if (old_config != NULL) {
        cJSON *old_gh_uid = cJSON_GetObjectItem(old_config, "gh_uid");
        if (old_gh_uid && cJSON_IsString(old_gh_uid) && old_gh_uid->valuestring && strlen(old_gh_uid->valuestring) > 0) {
            fallback_gh = old_gh_uid->valuestring;
        }

        cJSON *old_zone_uid = cJSON_GetObjectItem(old_config, "zone_uid");
        if (old_zone_uid && cJSON_IsString(old_zone_uid) && old_zone_uid->valuestring && strlen(old_zone_uid->valuestring) > 0) {
            fallback_zone = old_zone_uid->valuestring;
        }
    }

    if (!new_has_valid_gh) {
        const char *value = fallback_gh ? fallback_gh : "gh-temp";
        if (new_gh_uid) {
            cJSON_DeleteItemFromObject(new_config, "gh_uid");
        }
        cJSON_AddStringToObject(new_config, "gh_uid", value);
        ESP_LOGI(TAG, "Preserved gh_uid from %s config: %s", fallback_gh ? "old" : "default", value);
    }

    if (!new_has_valid_zone) {
        const char *value = fallback_zone ? fallback_zone : "zn-temp";
        if (new_zone_uid) {
            cJSON_DeleteItemFromObject(new_config, "zone_uid");
        }
        cJSON_AddStringToObject(new_config, "zone_uid", value);
        ESP_LOGI(TAG, "Preserved zone_uid from %s config: %s", fallback_zone ? "old" : "default", value);
    }

    // Освобождаем старый конфиг после использования
    if (old_config != NULL) {
        cJSON_Delete(old_config);
    }
    
    // Создаем обновленную JSON строку с сохраненным WiFi
    ESP_LOGI(TAG, "Generating final JSON config with preserved WiFi (if applicable)");
    char *final_json = cJSON_PrintUnformatted(new_config);
    cJSON_Delete(new_config);
    
    if (final_json == NULL) {
        ESP_LOGE(TAG, "Failed to generate final JSON config - memory error");
        config_storage_unlock();
        return ESP_ERR_NO_MEM;
    }
    
    size_t final_json_len = strlen(final_json);
    ESP_LOGI(TAG, "Final JSON config generated: %zu bytes (original: %zu bytes)", final_json_len, json_len);
    
    if (final_json_len >= sizeof(s_config_json)) {
        ESP_LOGE(TAG, "Final JSON config too large: %zu bytes (max: %zu)", final_json_len, sizeof(s_config_json) - 1);
        free(final_json);
        config_storage_unlock();
        return ESP_ERR_INVALID_SIZE;
    }

    // Финальная валидация: к этому моменту добавлены сохраненные поля gh_uid/zone_uid/WiFi/MQTT
    esp_err_t err = config_storage_validate(final_json, final_json_len, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Final config validation failed");
        free(final_json);
        config_storage_unlock();
        return err;
    }
    
    // Проверяем, что в финальном конфиге есть WiFi (если был добавлен)
    cJSON *verify_final_config = cJSON_Parse(final_json);
    if (verify_final_config) {
        cJSON *verify_final_wifi = cJSON_GetObjectItem(verify_final_config, "wifi");
        if (verify_final_wifi && cJSON_IsObject(verify_final_wifi)) {
            cJSON *verify_final_ssid = cJSON_GetObjectItem(verify_final_wifi, "ssid");
            if (verify_final_ssid && cJSON_IsString(verify_final_ssid) && 
                verify_final_ssid->valuestring && strlen(verify_final_ssid->valuestring) > 0) {
                ESP_LOGI(TAG, "Final config has valid WiFi SSID: '%s' (len=%zu)", 
                        verify_final_ssid->valuestring, strlen(verify_final_ssid->valuestring));
            } else {
                ESP_LOGW(TAG, "Final config has WiFi section but SSID is invalid or empty");
            }
        } else {
            ESP_LOGI(TAG, "Final config has no WiFi section (this is OK if WiFi already configured)");
        }
        cJSON_Delete(verify_final_config);
    }
    
    // Сохранение в NVS с сохраненным WiFi
    ESP_LOGI(TAG, "Saving final config to NVS (%zu bytes)", final_json_len);
    err = nvs_set_str(s_nvs_handle, NVS_KEY, final_json);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save NodeConfig to NVS: %s", esp_err_to_name(err));
        config_storage_unlock();
        return err;
    }
    
    // КРИТИЧНО: Коммит изменений в NVS - без этого данные могут быть потеряны при перезагрузке
    err = nvs_commit(s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to commit NVS: %s", esp_err_to_name(err));
        config_storage_unlock();
        return err;
    }
    
    // Обновление внутреннего буфера (используем final_json, а не json_config)
    strncpy(s_config_json, final_json, sizeof(s_config_json) - 1);
    s_config_json[sizeof(s_config_json) - 1] = '\0';
    s_config_loaded = true;
    
    ESP_LOGI(TAG, "NodeConfig saved to NVS (%zu bytes, committed)", final_json_len);
    
    // Освобождаем память
    free(final_json);
    
    // КРИТИЧНО: Проверяем, что сохраненная конфигурация может быть прочитана обратно
    // Это гарантирует, что после перезагрузки конфигурация будет доступна
    size_t verify_size = sizeof(s_config_json);
    char verify_buffer[CONFIG_STORAGE_MAX_JSON_SIZE];
    err = nvs_get_str(s_nvs_handle, NVS_KEY, verify_buffer, &verify_size);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CRITICAL: Failed to verify saved config: %s", esp_err_to_name(err));
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    // Проверяем соответствие сохраненного конфига (используем s_config_json, так как там уже сохранен final_json)
    if (strncmp(s_config_json, verify_buffer, strlen(s_config_json)) != 0) {
        ESP_LOGE(TAG, "CRITICAL: Saved config verification failed - data mismatch");
        ESP_LOGE(TAG, "Saved length: %zu, Verify length: %zu", strlen(s_config_json), strlen(verify_buffer));
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    // Дополнительная проверка: проверяем, что SSID присутствует в сохраненном конфиге
    // КРИТИЧНО: Если WiFi секция есть, то SSID должен быть валидным
    // Но если WiFi секции нет (конфиг от MQTT после setup), то это нормально - WiFi уже настроен
    cJSON *verify_config = cJSON_Parse(verify_buffer);
    if (verify_config) {
        cJSON *verify_wifi = cJSON_GetObjectItem(verify_config, "wifi");
        if (verify_wifi && cJSON_IsObject(verify_wifi)) {
            // Если WiFi секция присутствует, проверяем, что SSID валиден
            cJSON *verify_ssid = cJSON_GetObjectItem(verify_wifi, "ssid");
            if (!verify_ssid || !cJSON_IsString(verify_ssid) || 
                !verify_ssid->valuestring || strlen(verify_ssid->valuestring) == 0) {
                ESP_LOGE(TAG, "CRITICAL: Saved config verification failed - SSID missing or empty in saved config");
                cJSON_Delete(verify_config);
                s_config_loaded = false;
                config_storage_unlock();
                return ESP_FAIL;
            }
            ESP_LOGI(TAG, "Config saved and verified successfully (SSID='%s')", verify_ssid->valuestring);
        } else {
            // WiFi секции нет - это нормально для конфигов от MQTT после setup mode
            ESP_LOGI(TAG, "Config saved and verified successfully (no WiFi section - WiFi already configured)");
        }
        
        // Проверяем MQTT секцию в финальном конфиге
        cJSON *verify_final_mqtt = cJSON_GetObjectItem(verify_config, "mqtt");
        if (verify_final_mqtt && cJSON_IsObject(verify_final_mqtt)) {
            cJSON *verify_final_mqtt_host = cJSON_GetObjectItem(verify_final_mqtt, "host");
            if (verify_final_mqtt_host && cJSON_IsString(verify_final_mqtt_host) && 
                verify_final_mqtt_host->valuestring && strlen(verify_final_mqtt_host->valuestring) > 0) {
                cJSON *verify_final_mqtt_port = cJSON_GetObjectItem(verify_final_mqtt, "port");
                ESP_LOGI(TAG, "Final config has valid MQTT config: host='%s', port=%.0f", 
                        verify_final_mqtt_host->valuestring, 
                        verify_final_mqtt_port ? cJSON_GetNumberValue(verify_final_mqtt_port) : 0);
            } else {
                ESP_LOGW(TAG, "Final config has MQTT section but host is invalid or empty");
            }
        } else {
            ESP_LOGW(TAG, "Final config has no MQTT section (this may cause issues)");
        }
        cJSON_Delete(verify_config);
    } else {
        ESP_LOGE(TAG, "CRITICAL: Failed to parse saved config for verification");
        s_config_loaded = false;
        config_storage_unlock();
        return ESP_FAIL;
    }
    config_storage_unlock();
    return ESP_OK;
}

bool config_storage_exists(void) {
    if (s_nvs_handle == 0) {
        return false;
    }
    
    // Проверяем, что конфигурация не только существует в NVS, но и загружена и валидна
    if (!config_storage_lock()) {
        return false;
    }
    if (s_config_loaded) {
        config_storage_unlock();
        return true;
    }
    config_storage_unlock();
    
    // Если не загружена, пытаемся проверить наличие в NVS
    size_t required_size = 0;
    esp_err_t err = nvs_get_str(s_nvs_handle, NVS_KEY, NULL, &required_size);
    if (err == ESP_OK && required_size > 0) {
        // Конфигурация существует в NVS, но не загружена - пытаемся загрузить
        // Это может помочь, если загрузка не была вызвана ранее
        esp_err_t load_err = config_storage_load();
        return (load_err == ESP_OK);
    }
    
    return false;
}

esp_err_t config_storage_get_json(char *buffer, size_t buffer_size) {
    if (buffer == NULL || buffer_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!config_storage_lock()) {
        return ESP_ERR_TIMEOUT;
    }
    if (!s_config_loaded) {
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    size_t copy_size = (strlen(s_config_json) < buffer_size - 1) ? 
                       strlen(s_config_json) : buffer_size - 1;
    strncpy(buffer, s_config_json, copy_size);
    buffer[copy_size] = '\0';
    config_storage_unlock();
    
    return ESP_OK;
}

static esp_err_t get_json_string_field(const char *field_name, char *buffer, size_t buffer_size) {
    if (!config_storage_lock()) {
        return ESP_ERR_TIMEOUT;
    }
    if (!s_config_loaded) {
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    cJSON *item = cJSON_GetObjectItem(config, field_name);
    if (item == NULL || !cJSON_IsString(item)) {
        cJSON_Delete(config);
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    strncpy(buffer, item->valuestring, buffer_size - 1);
    buffer[buffer_size - 1] = '\0';
    
    cJSON_Delete(config);
    config_storage_unlock();
    return ESP_OK;
}

static esp_err_t get_json_number_field(const char *field_name, int *value) {
    if (!config_storage_lock()) {
        return ESP_ERR_TIMEOUT;
    }
    if (!s_config_loaded) {
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    cJSON *item = cJSON_GetObjectItem(config, field_name);
    if (item == NULL || !cJSON_IsNumber(item)) {
        cJSON_Delete(config);
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    *value = (int)cJSON_GetNumberValue(item);
    cJSON_Delete(config);
    config_storage_unlock();
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
    
    if (!config_storage_lock()) {
        return ESP_ERR_TIMEOUT;
    }
    if (!s_config_loaded) {
        ESP_LOGW(TAG, "config_storage_get_mqtt: Config not loaded");
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    ESP_LOGI(TAG, "config_storage_get_mqtt: Parsing config JSON (%zu bytes)", strlen(s_config_json));
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        ESP_LOGE(TAG, "config_storage_get_mqtt: Failed to parse config JSON");
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    cJSON *mqtt_obj = cJSON_GetObjectItem(config, "mqtt");
    if (mqtt_obj == NULL || !cJSON_IsObject(mqtt_obj)) {
        ESP_LOGW(TAG, "config_storage_get_mqtt: MQTT section not found in config");
        cJSON_Delete(config);
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    ESP_LOGI(TAG, "config_storage_get_mqtt: MQTT section found, extracting fields");
    
    // Заполнение структуры с значениями по умолчанию
    memset(mqtt, 0, sizeof(config_storage_mqtt_t));
    
    cJSON *item;
    if ((item = cJSON_GetObjectItem(mqtt_obj, "host")) && cJSON_IsString(item)) {
        if (item->valuestring && strlen(item->valuestring) > 0) {
            strncpy(mqtt->host, item->valuestring, sizeof(mqtt->host) - 1);
            mqtt->host[sizeof(mqtt->host) - 1] = '\0';
            ESP_LOGI(TAG, "config_storage_get_mqtt: MQTT host='%s' (len=%zu)", 
                    mqtt->host, strlen(mqtt->host));
        } else {
            ESP_LOGW(TAG, "config_storage_get_mqtt: MQTT host field is empty string");
        }
    } else {
        ESP_LOGW(TAG, "config_storage_get_mqtt: MQTT host field not found or invalid");
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
    
    // Используем "password" вместо "pass" для унификации с config_apply
    if ((item = cJSON_GetObjectItem(mqtt_obj, "password")) && cJSON_IsString(item)) {
        strncpy(mqtt->password, item->valuestring, sizeof(mqtt->password) - 1);
        mqtt->password[sizeof(mqtt->password) - 1] = '\0';  // Гарантируем null-termination
    }
    // Поддержка старого формата "pass" для обратной совместимости
    else if ((item = cJSON_GetObjectItem(mqtt_obj, "pass")) && cJSON_IsString(item)) {
        strncpy(mqtt->password, item->valuestring, sizeof(mqtt->password) - 1);
        mqtt->password[sizeof(mqtt->password) - 1] = '\0';  // Гарантируем null-termination
    }
    
    // Используем "use_tls" вместо "tls" для унификации с config_apply
    if ((item = cJSON_GetObjectItem(mqtt_obj, "use_tls")) && cJSON_IsBool(item)) {
        mqtt->use_tls = cJSON_IsTrue(item);
    }
    // Поддержка старого формата "tls" для обратной совместимости
    else if ((item = cJSON_GetObjectItem(mqtt_obj, "tls")) && cJSON_IsBool(item)) {
        mqtt->use_tls = cJSON_IsTrue(item);
    }
    
    cJSON_Delete(config);
    config_storage_unlock();
    return ESP_OK;
}

esp_err_t config_storage_get_wifi(config_storage_wifi_t *wifi) {
    if (wifi == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!config_storage_lock()) {
        return ESP_ERR_TIMEOUT;
    }
    if (!s_config_loaded) {
        config_storage_unlock();
        return ESP_ERR_NOT_FOUND;
    }
    
    cJSON *config = cJSON_Parse(s_config_json);
    if (config == NULL) {
        config_storage_unlock();
        return ESP_FAIL;
    }
    
    cJSON *wifi_obj = cJSON_GetObjectItem(config, "wifi");
    if (wifi_obj == NULL || !cJSON_IsObject(wifi_obj)) {
        cJSON_Delete(config);
        config_storage_unlock();
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
    config_storage_unlock();
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
    
    if (wifi != NULL && !cJSON_IsObject(wifi)) {
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

    if (cJSON_IsObject(wifi)) {
        cJSON *wifi_configured = cJSON_GetObjectItem(wifi, "configured");
        bool is_configured = (wifi_configured != NULL &&
                              cJSON_IsBool(wifi_configured) &&
                              cJSON_IsTrue(wifi_configured));
        if (!is_configured) {
            cJSON *wifi_ssid = cJSON_GetObjectItem(wifi, "ssid");
            if (!cJSON_IsString(wifi_ssid) || wifi_ssid->valuestring == NULL || wifi_ssid->valuestring[0] == '\0') {
                cJSON_Delete(config);
                if (error_msg && error_msg_size > 0) {
                    strncpy(error_msg, "Missing or invalid wifi.ssid", error_msg_size - 1);
                }
                return ESP_ERR_INVALID_ARG;
            }
        }
    }
    
    // ВАЖНО: Если mqtt содержит только {"configured": true}, значит нода уже подключена
    // и backend НЕ хочет менять MQTT настройки. Пропускаем валидацию полей.
    cJSON *mqtt_configured = cJSON_GetObjectItem(mqtt, "configured");
    if (cJSON_IsBool(mqtt_configured) && cJSON_IsTrue(mqtt_configured)) {
        // Backend указал, что MQTT уже настроен - пропускаем валидацию host/port
        ESP_LOGI("config_storage", "MQTT marked as 'configured', preserving existing settings");
    } else {
        // Валидация обязательных MQTT полей только если это полная конфигурация
        cJSON *mqtt_host = cJSON_GetObjectItem(mqtt, "host");
        if (!cJSON_IsString(mqtt_host) || mqtt_host->valuestring == NULL || mqtt_host->valuestring[0] == '\0') {
            cJSON_Delete(config);
            if (error_msg && error_msg_size > 0) {
                strncpy(error_msg, "Missing or invalid mqtt.host", error_msg_size - 1);
            }
            return ESP_ERR_INVALID_ARG;
        }
        
        cJSON *mqtt_port = cJSON_GetObjectItem(mqtt, "port");
        if (!cJSON_IsNumber(mqtt_port) || cJSON_GetNumberValue(mqtt_port) <= 0 || cJSON_GetNumberValue(mqtt_port) > 65535) {
            cJSON_Delete(config);
            if (error_msg && error_msg_size > 0) {
                strncpy(error_msg, "Missing or invalid mqtt.port (must be 1-65535)", error_msg_size - 1);
            }
            return ESP_ERR_INVALID_ARG;
        }
        
        cJSON *mqtt_keepalive = cJSON_GetObjectItem(mqtt, "keepalive");
        if (mqtt_keepalive != NULL && (!cJSON_IsNumber(mqtt_keepalive) || cJSON_GetNumberValue(mqtt_keepalive) <= 0 || cJSON_GetNumberValue(mqtt_keepalive) > 65535)) {
            cJSON_Delete(config);
            if (error_msg && error_msg_size > 0) {
                strncpy(error_msg, "Invalid mqtt.keepalive (must be 1-65535)", error_msg_size - 1);
            }
            return ESP_ERR_INVALID_ARG;
        }
    }
    
    // Дополнительная валидация каналов: relay_type обязателен для реле-актуаторов
    int channels_count = cJSON_GetArraySize(channels);
    for (int i = 0; i < channels_count; i++) {
        cJSON *channel = cJSON_GetArrayItem(channels, i);
        if (channel == NULL || !cJSON_IsObject(channel)) {
            continue;
        }

        cJSON *type_item = cJSON_GetObjectItem(channel, "type");
        if (!cJSON_IsString(type_item) || type_item->valuestring == NULL) {
            continue;
        }
        if (strcasecmp(type_item->valuestring, "ACTUATOR") != 0) {
            continue;
        }

        cJSON *actuator_type_item = cJSON_GetObjectItem(channel, "actuator_type");
        if (!cJSON_IsString(actuator_type_item) || actuator_type_item->valuestring == NULL) {
            continue;
        }

        const char *act_type = actuator_type_item->valuestring;
        bool requires_relay_type =
            (strcasecmp(act_type, "RELAY") == 0 ||
             strcasecmp(act_type, "VALVE") == 0 ||
             strcasecmp(act_type, "FAN") == 0 ||
             strcasecmp(act_type, "HEATER") == 0);

        if (!requires_relay_type) {
            continue;
        }

        cJSON *relay_type_item = cJSON_GetObjectItem(channel, "relay_type");
        if (!cJSON_IsString(relay_type_item) || relay_type_item->valuestring == NULL ||
            relay_type_item->valuestring[0] == '\0') {
            const char *name = NULL;
            cJSON *name_item = cJSON_GetObjectItem(channel, "name");
            if (cJSON_IsString(name_item) && name_item->valuestring) {
                name = name_item->valuestring;
            }
            if (error_msg && error_msg_size > 0) {
                if (name) {
                    snprintf(error_msg, error_msg_size,
                             "Missing relay_type for actuator channel '%s'", name);
                } else {
                    snprintf(error_msg, error_msg_size,
                             "Missing relay_type for actuator channel");
                }
            }
            cJSON_Delete(config);
            return ESP_ERR_INVALID_ARG;
        }

        if (strcasecmp(relay_type_item->valuestring, "NC") != 0 &&
            strcasecmp(relay_type_item->valuestring, "NO") != 0) {
            const char *name = NULL;
            cJSON *name_item = cJSON_GetObjectItem(channel, "name");
            if (cJSON_IsString(name_item) && name_item->valuestring) {
                name = name_item->valuestring;
            }
            if (error_msg && error_msg_size > 0) {
                if (name) {
                    snprintf(error_msg, error_msg_size,
                             "Invalid relay_type for actuator channel '%s' (expected NC/NO)", name);
                } else {
                    snprintf(error_msg, error_msg_size,
                             "Invalid relay_type for actuator channel (expected NC/NO)");
                }
            }
            cJSON_Delete(config);
            return ESP_ERR_INVALID_ARG;
        }
    }

    cJSON_Delete(config);
    return ESP_OK;
}

esp_err_t config_storage_set_last_temperature(float temperature) {
    if (s_nvs_handle == 0) {
        ESP_LOGE(TAG, "Config storage not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = nvs_set_blob(s_nvs_handle, NVS_TEMP_KEY, &temperature, sizeof(temperature));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save last temperature: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_commit(s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to commit last temperature: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGD(TAG, "Stored last EC temperature: %.2f C", temperature);
    return ESP_OK;
}

esp_err_t config_storage_get_last_temperature(float *temperature) {
    if (temperature == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_nvs_handle == 0) {
        return ESP_ERR_INVALID_STATE;
    }

    size_t length = sizeof(float);
    esp_err_t err = nvs_get_blob(s_nvs_handle, NVS_TEMP_KEY, temperature, &length);
    if (err != ESP_OK) {
        return err;
    }

    if (length != sizeof(float)) {
        return ESP_ERR_INVALID_SIZE;
    }

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
