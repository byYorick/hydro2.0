/**
 * @file node_utils.c
 * @brief Реализация утилит для работы с нодами
 */

#include "node_utils.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include <string.h>
#include <time.h>
#include <sys/time.h>
#include "cJSON.h"

static const char *TAG = "node_utils";

// Смещение времени для нормализации Unix timestamp
// time_offset_us = host_ts_us - esp_timer_get_time()
// Используется для преобразования esp_timer_get_time() в Unix timestamp
static int64_t s_time_offset_us = 0;
static bool s_time_synced = false;

esp_err_t node_utils_strncpy_safe(char *dest, const char *src, size_t dest_size) {
    if (dest == NULL || src == NULL || dest_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    strncpy(dest, src, dest_size - 1);
    dest[dest_size - 1] = '\0';  // Гарантируем null-termination
    
    return ESP_OK;
}

esp_err_t node_utils_get_hardware_id(char *hardware_id, size_t size) {
    if (hardware_id == NULL || size < 8) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t mac[6] = {0};
    esp_err_t err = esp_efuse_mac_get_default(mac);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get MAC address: %s", esp_err_to_name(err));
        return err;
    }

    snprintf(hardware_id, size, "esp32-%02x%02x%02x%02x%02x%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    return ESP_OK;
}

esp_err_t node_utils_init_wifi_config(
    wifi_manager_config_t *wifi_config,
    char *wifi_ssid,
    char *wifi_password
) {
    if (wifi_config == NULL || wifi_ssid == NULL || wifi_password == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    config_storage_wifi_t wifi_cfg;
    esp_err_t err = config_storage_get_wifi(&wifi_cfg);
    if (err != ESP_OK) {
        return ESP_ERR_NOT_FOUND;
    }
    
    node_utils_strncpy_safe(wifi_ssid, wifi_cfg.ssid, CONFIG_STORAGE_MAX_STRING_LEN);
    node_utils_strncpy_safe(wifi_password, wifi_cfg.password, CONFIG_STORAGE_MAX_STRING_LEN);
    
    wifi_config->ssid = wifi_ssid;
    wifi_config->password = wifi_password;
    
    ESP_LOGI(TAG, "WiFi config loaded: %s", wifi_cfg.ssid);
    return ESP_OK;
}

esp_err_t node_utils_init_mqtt_config(
    mqtt_manager_config_t *mqtt_config,
    mqtt_node_info_t *node_info,
    char *mqtt_host,
    char *mqtt_username,
    char *mqtt_password,
    char *node_id,
    char *gh_uid,
    char *zone_uid,
    const char *default_gh_uid,
    const char *default_zone_uid,
    const char *default_node_id
) {
    if (mqtt_config == NULL || node_info == NULL || 
        mqtt_host == NULL || mqtt_username == NULL || mqtt_password == NULL ||
        node_id == NULL || gh_uid == NULL || zone_uid == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    config_storage_mqtt_t mqtt_cfg;
    esp_err_t err = config_storage_get_mqtt(&mqtt_cfg);
    
    if (err == ESP_OK) {
        // Загружаем из config_storage
        node_utils_strncpy_safe(mqtt_host, mqtt_cfg.host, CONFIG_STORAGE_MAX_STRING_LEN);
        mqtt_config->host = mqtt_host;
        mqtt_config->port = mqtt_cfg.port;
        mqtt_config->keepalive = mqtt_cfg.keepalive;
        mqtt_config->client_id = NULL;
        
        if (strlen(mqtt_cfg.username) > 0) {
            node_utils_strncpy_safe(mqtt_username, mqtt_cfg.username, CONFIG_STORAGE_MAX_STRING_LEN);
            mqtt_config->username = mqtt_username;
        } else {
            mqtt_config->username = NULL;
        }
        
        if (strlen(mqtt_cfg.password) > 0) {
            node_utils_strncpy_safe(mqtt_password, mqtt_cfg.password, CONFIG_STORAGE_MAX_STRING_LEN);
            mqtt_config->password = mqtt_password;
        } else {
            mqtt_config->password = NULL;
        }
        
        mqtt_config->use_tls = mqtt_cfg.use_tls;
        ESP_LOGI(TAG, "MQTT config from storage: %s:%d", mqtt_cfg.host, mqtt_cfg.port);
    } else {
        // Используем дефолтные значения
        node_utils_strncpy_safe(mqtt_host, "192.168.1.10", CONFIG_STORAGE_MAX_STRING_LEN);
        mqtt_config->host = mqtt_host;
        mqtt_config->port = 1883;
        mqtt_config->keepalive = 30;
        mqtt_config->client_id = NULL;
        mqtt_config->username = NULL;
        mqtt_config->password = NULL;
        mqtt_config->use_tls = false;
        ESP_LOGW(TAG, "Using default MQTT config");
    }
    
    // Получение node_id
    bool node_id_set = false;
    if (config_storage_get_node_id(node_id, 64) == ESP_OK && strlen(node_id) > 0) {
        node_info->node_uid = node_id;
        node_id_set = true;
        ESP_LOGI(TAG, "Node ID from config: %s", node_id);
    }

    if (!node_id_set) {
        char hw_id[32] = {0};
        if (node_utils_get_hardware_id(hw_id, sizeof(hw_id)) == ESP_OK) {
            node_utils_strncpy_safe(node_id, hw_id, 64);
            ESP_LOGW(TAG, "Node ID not found, using hardware_id: %s", node_id);
        } else {
            node_utils_strncpy_safe(node_id, default_node_id, 64);
            ESP_LOGW(TAG, "Node ID not found, using default: %s", default_node_id);
        }
        node_info->node_uid = node_id;
    }
    
    // Получение gh_uid
    if (config_storage_get_gh_uid(gh_uid, CONFIG_STORAGE_MAX_STRING_LEN) == ESP_OK) {
        node_info->gh_uid = gh_uid;
        ESP_LOGI(TAG, "GH UID from config: %s", gh_uid);
    } else {
        node_utils_strncpy_safe(gh_uid, default_gh_uid, CONFIG_STORAGE_MAX_STRING_LEN);
        node_info->gh_uid = gh_uid;
        ESP_LOGW(TAG, "GH UID not found in config, using default: %s", default_gh_uid);
    }
    
    // Получение zone_uid
    if (config_storage_get_zone_uid(zone_uid, CONFIG_STORAGE_MAX_STRING_LEN) == ESP_OK) {
        node_info->zone_uid = zone_uid;
        ESP_LOGI(TAG, "Zone UID from config: %s", zone_uid);
    } else {
        node_utils_strncpy_safe(zone_uid, default_zone_uid, CONFIG_STORAGE_MAX_STRING_LEN);
        node_info->zone_uid = zone_uid;
        ESP_LOGW(TAG, "Zone UID not found in config, using default: %s", default_zone_uid);
    }
    
    return ESP_OK;
}

esp_err_t node_utils_bootstrap_network_stack(void) {
    // NVS init with erase fallback for corrupted pages
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init NVS: %s", esp_err_to_name(ret));
        return ret;
    }

    // esp_netif + default loop (idempotent)
    ret = esp_netif_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init esp_netif: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = esp_event_loop_create_default();
    if (ret != ESP_OK && ret != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "Failed to create default event loop: %s", esp_err_to_name(ret));
        return ret;
    }

    // Wi‑Fi station bring-up (ignore if already started)
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ret = esp_wifi_init(&cfg);
    if (ret != ESP_OK && ret != ESP_ERR_WIFI_INIT_STATE) {
        ESP_LOGE(TAG, "Failed to init Wi-Fi: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = esp_wifi_set_mode(WIFI_MODE_STA);
    if (ret != ESP_OK && ret != ESP_ERR_WIFI_NOT_INIT) {  // NOT_INIT happens if init failed
        ESP_LOGE(TAG, "Failed to set Wi-Fi mode: %s", esp_err_to_name(ret));
        return ret;
    }

    ret = esp_wifi_start();
    if (ret != ESP_OK && ret != ESP_ERR_WIFI_CONN) {  // CONN means already started
        ESP_LOGE(TAG, "Failed to start Wi-Fi: %s", esp_err_to_name(ret));
        return ret;
    }

    return ESP_OK;
}

int64_t node_utils_get_timestamp_seconds(void) {
    return node_utils_now_epoch();
}

/**
 * @brief Получение текущего Unix timestamp в секундах с учетом смещения
 * 
 * Использует смещение времени (time_offset_us), установленное через set_time,
 * для преобразования esp_timer_get_time() в Unix timestamp.
 * 
 * @return Unix timestamp в секундах, или аптайм если время не синхронизировано
 */
int64_t node_utils_now_epoch(void) {
    if (s_time_synced && s_time_offset_us != 0) {
        // Используем смещение для получения Unix timestamp
        int64_t current_time_us = esp_timer_get_time() + s_time_offset_us;
        return current_time_us / 1000000;
    }
    
    // Время не синхронизировано - возвращаем аптайм
    // Это позволяет работать даже без синхронизации, но history-logger должен понимать,
    // что это аптайм, а не Unix timestamp
    return esp_timer_get_time() / 1000000;
}

/**
 * @brief Установка времени через смещение
 * 
 * Вычисляет и сохраняет смещение времени для преобразования esp_timer_get_time()
 * в Unix timestamp.
 * 
 * @param unix_ts_sec Unix timestamp в секундах (UTC)
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_set_time(int64_t unix_ts_sec) {
    if (unix_ts_sec < 1000000000) {  // Примерно 2001-09-09 (разумная дата для проверки)
        ESP_LOGE(TAG, "Invalid Unix timestamp: %lld", (long long)unix_ts_sec);
        return ESP_ERR_INVALID_ARG;
    }
    
    int64_t current_uptime_us = esp_timer_get_time();
    int64_t unix_ts_us = unix_ts_sec * 1000000;
    
    // Вычисляем смещение: time_offset_us = host_ts_us - esp_timer_get_time()
    s_time_offset_us = unix_ts_us - current_uptime_us;
    s_time_synced = true;
    
    ESP_LOGI(TAG, "Time set: Unix timestamp=%lld, offset_us=%lld", 
             (long long)unix_ts_sec, (long long)s_time_offset_us);
    
    // Также устанавливаем системное время через clock_settime (если доступно)
    struct timespec ts;
    ts.tv_sec = unix_ts_sec;
    ts.tv_nsec = 0;
    clock_settime(CLOCK_REALTIME, &ts);
    
    return ESP_OK;
}

int64_t node_utils_get_unix_timestamp(void) {
    time_t now;
    time(&now);
    
    // Проверяем, что время синхронизировано (не 0 и не слишком маленькое)
    // Если время не синхронизировано, time() может вернуть 0 или очень маленькое значение
    if (now > 1000000000) {  // Примерно 2001-09-09 (разумная дата для проверки)
        return (int64_t)now;
    }
    
    // Время не синхронизировано - возвращаем 0
    // Это сигнализирует, что нужно использовать аптайм
    return 0;
}

bool node_utils_is_time_synced(void) {
    return s_time_synced;
}

esp_err_t node_utils_publish_node_hello(
    const char *node_type,
    const char *capabilities[],
    size_t capabilities_count
) {
    if (node_type == NULL || capabilities == NULL || capabilities_count == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Получаем MAC адрес как hardware_id
    char hardware_id[32];
    esp_err_t err = node_utils_get_hardware_id(hardware_id, sizeof(hardware_id));
    if (err != ESP_OK) {
        return err;
    }
    
    // Получаем версию прошивки
    char fw_version[64];
    const char *idf_ver = esp_get_idf_version();
    snprintf(fw_version, sizeof(fw_version), "%s", idf_ver);
    
    // Создаем JSON сообщение node_hello
    cJSON *hello = cJSON_CreateObject();
    if (!hello) {
        ESP_LOGE(TAG, "Failed to create node_hello JSON");
        return ESP_ERR_NO_MEM;
    }
    
    cJSON_AddStringToObject(hello, "message_type", "node_hello");
    cJSON_AddStringToObject(hello, "hardware_id", hardware_id);
    cJSON_AddStringToObject(hello, "node_type", node_type);
    cJSON_AddStringToObject(hello, "fw_version", fw_version);
    
    // Добавляем capabilities
    cJSON *capabilities_array = cJSON_CreateArray();
    if (capabilities_array) {
        for (size_t i = 0; i < capabilities_count; i++) {
            if (capabilities[i] != NULL) {
                cJSON_AddItemToArray(capabilities_array, cJSON_CreateString(capabilities[i]));
            }
        }
        cJSON_AddItemToObject(hello, "capabilities", capabilities_array);
    }
    
    // Публикуем в общий топик для регистрации
    char *json_str = cJSON_PrintUnformatted(hello);
    if (json_str == NULL) {
        cJSON_Delete(hello);
        ESP_LOGE(TAG, "Failed to serialize node_hello JSON");
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "Publishing node_hello: hardware_id=%s, node_type=%s", hardware_id, node_type);

    // Публикуем через mqtt_manager_publish_raw
    esp_err_t pub_err = mqtt_manager_publish_raw("hydro/node_hello", json_str, 1, 0);
    if (pub_err == ESP_OK) {
        ESP_LOGI(TAG, "node_hello published successfully");
    } else {
        ESP_LOGE(TAG, "Failed to publish node_hello: %s", esp_err_to_name(pub_err));
    }

    free(json_str);
    cJSON_Delete(hello);
    return pub_err;
}

esp_err_t node_utils_publish_config_report(void) {
    static char config_json[CONFIG_STORAGE_MAX_JSON_SIZE];

    esp_err_t err = config_storage_get_json(config_json, sizeof(config_json));
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to load NodeConfig for config_report: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Publishing config_report (%zu bytes)", strlen(config_json));
    err = mqtt_manager_publish_config_report(config_json);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to publish config_report: %s", esp_err_to_name(err));
    }

    return err;
}

/**
 * @brief Запрос времени у сервера через MQTT
 * 
 * Публикует запрос времени в топик hydro/time/request
 * Сервер должен ответить командой set_time
 */
esp_err_t node_utils_request_time(void) {
    if (!mqtt_manager_is_connected()) {
        ESP_LOGW(TAG, "MQTT not connected, cannot request time");
        return ESP_ERR_INVALID_STATE;
    }
    
    // Создаем JSON запрос времени
    cJSON *request = cJSON_CreateObject();
    if (!request) {
        ESP_LOGE(TAG, "Failed to create time request JSON");
        return ESP_ERR_NO_MEM;
    }
    
    cJSON_AddStringToObject(request, "message_type", "time_request");
    cJSON_AddNumberToObject(request, "uptime", (double)(esp_timer_get_time() / 1000000));
    
    char *json_str = cJSON_PrintUnformatted(request);
    if (json_str) {
        ESP_LOGI(TAG, "Requesting time from server");
        esp_err_t err = mqtt_manager_publish_raw("hydro/time/request", json_str, 1, 0);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to publish time request: %s", esp_err_to_name(err));
        }
        free(json_str);
    }
    
    cJSON_Delete(request);
    return ESP_OK;
}
