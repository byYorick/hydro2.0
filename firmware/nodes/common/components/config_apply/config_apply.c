#include "config_apply.h"

#include "config_storage.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"
#include "node_utils.h"
#include "pump_driver.h"
#include "relay_driver.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <stdlib.h>
#include <string.h>

static const char *TAG = "config_apply";

static char s_wifi_ssid[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_wifi_password[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_mqtt_host[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_mqtt_username[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_mqtt_password[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_node_id[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_gh_uid[CONFIG_STORAGE_MAX_STRING_LEN];
static char s_zone_uid[CONFIG_STORAGE_MAX_STRING_LEN];

// Mutex для защиты статического буфера в config_apply_load_previous_config
static SemaphoreHandle_t s_load_config_mutex = NULL;

static void config_apply_result_add(config_apply_result_t *result, const char *component) {
    if (result == NULL || component == NULL) {
        return;
    }

    if (result->count >= CONFIG_APPLY_MAX_COMPONENTS) {
        ESP_LOGW(TAG, "Restarted components list is full");
        return;
    }

    strlcpy(result->components[result->count], component, CONFIG_APPLY_COMPONENT_NAME_MAX_LEN);
    result->count++;
}

void config_apply_result_init(config_apply_result_t *result) {
    if (result == NULL) {
        return;
    }

    memset(result, 0, sizeof(*result));
}

cJSON *config_apply_load_previous_config(void) {
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    // ВАЖНО: Защищаем mutex для потокобезопасности (может вызываться из разных задач)
    static char json_buffer[CONFIG_STORAGE_MAX_JSON_SIZE];
    
    // Инициализация mutex при первом вызове
    if (s_load_config_mutex == NULL) {
        s_load_config_mutex = xSemaphoreCreateMutex();
        if (s_load_config_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create load_config mutex");
            // Продолжаем без защиты (небезопасно, но лучше чем упасть)
        }
    }
    
    // Захватываем mutex для защиты статического буфера
    bool mutex_taken = false;
    if (s_load_config_mutex != NULL && 
        xSemaphoreTake(s_load_config_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        mutex_taken = true;
    }
    
    esp_err_t err = config_storage_get_json(json_buffer, sizeof(json_buffer));
    cJSON *result = NULL;
    
    if (err == ESP_OK) {
        result = cJSON_Parse(json_buffer);
        if (result == NULL) {
            ESP_LOGE(TAG, "Failed to parse previous config JSON");
        }
    } else {
        ESP_LOGE(TAG, "Failed to load previous config: %s", esp_err_to_name(err));
    }
    
    // Освобождаем mutex
    if (mutex_taken) {
        xSemaphoreGive(s_load_config_mutex);
    }
    
    return result;
}

static const cJSON *config_apply_get_section(const cJSON *config, const char *name) {
    if (config == NULL || name == NULL) {
        return NULL;
    }

    const cJSON *section = cJSON_GetObjectItem(config, name);
    if (section == NULL || !cJSON_IsObject(section)) {
        return NULL;
    }

    return section;
}

static const char *config_apply_get_string(const cJSON *object, const char *field) {
    if (object == NULL || field == NULL) {
        return NULL;
    }

    const cJSON *item = cJSON_GetObjectItem(object, field);
    if (item == NULL || !cJSON_IsString(item)) {
        return NULL;
    }

    return item->valuestring;
}

static bool config_apply_bool_field_changed(const cJSON *previous, const cJSON *current, const char *field) {
    const cJSON *prev_item = previous ? cJSON_GetObjectItem(previous, field) : NULL;
    const cJSON *curr_item = current ? cJSON_GetObjectItem(current, field) : NULL;

    if (prev_item == NULL && curr_item == NULL) {
        return false;
    }

    if (prev_item == NULL || curr_item == NULL) {
        return true;
    }

    if (!cJSON_IsBool(prev_item) || !cJSON_IsBool(curr_item)) {
        return true;
    }

    return cJSON_IsTrue(prev_item) != cJSON_IsTrue(curr_item);
}

static bool config_apply_number_field_changed(const cJSON *previous, const cJSON *current, const char *field) {
    const cJSON *prev_item = previous ? cJSON_GetObjectItem(previous, field) : NULL;
    const cJSON *curr_item = current ? cJSON_GetObjectItem(current, field) : NULL;

    if (prev_item == NULL && curr_item == NULL) {
        return false;
    }

    if (prev_item == NULL || curr_item == NULL) {
        return true;
    }

    if (!cJSON_IsNumber(prev_item) || !cJSON_IsNumber(curr_item)) {
        return true;
    }

    return cJSON_GetNumberValue(prev_item) != cJSON_GetNumberValue(curr_item);
}

static bool config_apply_string_field_changed(const cJSON *previous, const cJSON *current, const char *field) {
    const char *prev_val = config_apply_get_string(previous, field);
    const char *curr_val = config_apply_get_string(current, field);

    if (prev_val == NULL && curr_val == NULL) {
        return false;
    }

    if (prev_val == NULL || curr_val == NULL) {
        return true;
    }

    return strcmp(prev_val, curr_val) != 0;
}

static bool config_apply_wifi_changed(const cJSON *previous_config, const cJSON *new_config) {
    const cJSON *prev_wifi = config_apply_get_section(previous_config, "wifi");
    const cJSON *new_wifi = config_apply_get_section(new_config, "wifi");

    if (prev_wifi == NULL && new_wifi == NULL) {
        return false;
    }

    if (new_wifi == NULL) {
        return false;
    }

    if (prev_wifi == NULL) {
        // Если предыдущего конфига нет, но новый есть - проверяем, есть ли в новом явные настройки
        // Если в новом конфиге только {"configured": true} без ssid/pass, то не меняем настройки
        const cJSON *new_ssid = cJSON_GetObjectItem(new_wifi, "ssid");
        const cJSON *new_pass = cJSON_GetObjectItem(new_wifi, "pass");
        // Если есть явные настройки ssid или pass, то применяем их
        if (new_ssid != NULL || new_pass != NULL) {
            return true;
        }
        // Если только {"configured": true}, то не меняем настройки
        return false;
    }

    // Оба конфига существуют - проверяем изменения только явных полей
    // Если в новом конфиге нет явного поля (например, только {"configured": true}),
    // то это поле считается неизменным
    
    // Проверяем ssid только если он явно указан в новом конфиге
    const cJSON *new_ssid = cJSON_GetObjectItem(new_wifi, "ssid");
    if (new_ssid != NULL && config_apply_string_field_changed(prev_wifi, new_wifi, "ssid")) {
        return true;
    }

    // Проверяем pass только если он явно указан в новом конфиге
    const cJSON *new_pass = cJSON_GetObjectItem(new_wifi, "pass");
    if (new_pass != NULL && config_apply_string_field_changed(prev_wifi, new_wifi, "pass")) {
        return true;
    }

    // Проверяем auto_reconnect только если он явно указан в новом конфиге
    const cJSON *new_auto_reconnect = cJSON_GetObjectItem(new_wifi, "auto_reconnect");
    if (new_auto_reconnect != NULL && config_apply_bool_field_changed(prev_wifi, new_wifi, "auto_reconnect")) {
        return true;
    }

    // Проверяем timeout_sec только если он явно указан в новом конфиге
    const cJSON *new_timeout = cJSON_GetObjectItem(new_wifi, "timeout_sec");
    if (new_timeout != NULL && config_apply_number_field_changed(prev_wifi, new_wifi, "timeout_sec")) {
        return true;
    }

    // Если в новом конфиге нет явных полей (только {"configured": true}),
    // то настройки не изменились
    return false;
}

static bool config_apply_mqtt_changed(const cJSON *previous_config, const cJSON *new_config) {
    const cJSON *prev_mqtt = config_apply_get_section(previous_config, "mqtt");
    const cJSON *new_mqtt = config_apply_get_section(new_config, "mqtt");

    if (prev_mqtt == NULL && new_mqtt == NULL) {
        // Нет MQTT секции вообще -> настройки не изменились
        return false;
    }

    if (new_mqtt == NULL) {
        return false;
    }

    if (prev_mqtt == NULL) {
        return true;
    }

    if (config_apply_string_field_changed(prev_mqtt, new_mqtt, "host")) {
        return true;
    }

    if (config_apply_number_field_changed(prev_mqtt, new_mqtt, "port")) {
        return true;
    }

    if (config_apply_number_field_changed(prev_mqtt, new_mqtt, "keepalive")) {
        return true;
    }

    if (config_apply_string_field_changed(prev_mqtt, new_mqtt, "username")) {
        return true;
    }

    if (config_apply_string_field_changed(prev_mqtt, new_mqtt, "password")) {
        return true;
    }

    if (config_apply_bool_field_changed(prev_mqtt, new_mqtt, "use_tls")) {
        return true;
    }

    // Также нужно перезапускать MQTT менеджер, если изменились идентификаторы ноды.
    // Именно эти поля формируют MQTT-топики (hydro/{gh}/{zone}/{node}/...).
    if (config_apply_string_field_changed(previous_config, new_config, "node_id")) {
        return true;
    }

    if (config_apply_string_field_changed(previous_config, new_config, "gh_uid")) {
        return true;
    }

    if (config_apply_string_field_changed(previous_config, new_config, "zone_uid")) {
        return true;
    }

    return false;
}

esp_err_t config_apply_wifi(const cJSON *new_config,
                            const cJSON *previous_config,
                            config_apply_result_t *result) {
    if (!config_apply_wifi_changed(previous_config, new_config)) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Wi-Fi settings changed, reapplying configuration");

    if (mqtt_manager_is_connected()) {
        ESP_LOGI(TAG, "Stopping MQTT before Wi-Fi reconnect");
        mqtt_manager_stop();
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    wifi_manager_disconnect();
    vTaskDelay(pdMS_TO_TICKS(500));

    config_storage_wifi_t wifi_cfg;
    esp_err_t err = config_storage_get_wifi(&wifi_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read Wi-Fi config from storage: %s", esp_err_to_name(err));
        return err;
    }

    strlcpy(s_wifi_ssid, wifi_cfg.ssid, sizeof(s_wifi_ssid));
    strlcpy(s_wifi_password, wifi_cfg.password, sizeof(s_wifi_password));

    wifi_manager_config_t wifi_config = {
        .ssid = s_wifi_ssid,
        .password = s_wifi_password,
    };

    err = wifi_manager_connect(&wifi_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to connect Wi-Fi: %s", esp_err_to_name(err));
        return err;
    }

    config_apply_result_add(result, "wifi");
    ESP_LOGI(TAG, "Wi-Fi reconnected successfully");
    return ESP_OK;
}

// Forward declarations
static void config_apply_populate_node_info(mqtt_node_info_t *node_info,
                                            const config_apply_mqtt_params_t *params);
static esp_err_t config_apply_populate_mqtt_config(mqtt_manager_config_t *mqtt_config);

esp_err_t config_apply_wifi_with_mqtt_restart(const cJSON *new_config,
                                                const cJSON *previous_config,
                                                const config_apply_mqtt_params_t *mqtt_params,
                                                config_apply_result_t *result) {
    // Сначала применяем Wi-Fi конфиг
    esp_err_t err = config_apply_wifi(new_config, previous_config, result);
    if (err != ESP_OK) {
        return err;
    }

    // Если MQTT был остановлен перед Wi-Fi реконнектом, принудительно перезапускаем его
    // даже если MQTT настройки не изменились
    if (mqtt_params != NULL) {
        ESP_LOGI(TAG, "Restarting MQTT after Wi-Fi reconnection");
        
        // Проверяем, был ли MQTT остановлен (если он не подключен, значит был остановлен)
        bool mqtt_was_stopped = !mqtt_manager_is_connected();
        
        if (mqtt_was_stopped) {
            // Принудительно перезапускаем MQTT
            mqtt_manager_deinit();
            vTaskDelay(pdMS_TO_TICKS(200));

            mqtt_manager_config_t mqtt_config = {0};
            err = config_apply_populate_mqtt_config(&mqtt_config);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to populate MQTT config: %s", esp_err_to_name(err));
                return err;
            }

            mqtt_node_info_t node_info = {0};
            config_apply_populate_node_info(&node_info, mqtt_params);

            err = mqtt_manager_init(&mqtt_config, &node_info);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to init MQTT manager: %s", esp_err_to_name(err));
                return err;
            }

            if (mqtt_params->config_cb) {
                mqtt_manager_register_config_cb(mqtt_params->config_cb, mqtt_params->user_ctx);
            }
            if (mqtt_params->command_cb) {
                mqtt_manager_register_command_cb(mqtt_params->command_cb, mqtt_params->user_ctx);
            }
            if (mqtt_params->connection_cb) {
                mqtt_manager_register_connection_cb(mqtt_params->connection_cb, mqtt_params->user_ctx);
            }

            err = mqtt_manager_start();
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to start MQTT manager: %s", esp_err_to_name(err));
                return err;
            }

            config_apply_result_add(result, "mqtt");
            ESP_LOGI(TAG, "MQTT client restarted after Wi-Fi reconnection");
        }
    }

    return ESP_OK;
}

static void config_apply_populate_node_info(mqtt_node_info_t *node_info,
                                            const config_apply_mqtt_params_t *params) {
    if (node_info == NULL || params == NULL) {
        return;
    }

    bool node_id_set = false;
    if (config_storage_get_node_id(s_node_id, sizeof(s_node_id)) == ESP_OK &&
        strlen(s_node_id) > 0 && strcmp(s_node_id, "node-temp") != 0) {
        node_id_set = true;
    }

    if (!node_id_set) {
        char hw_id[32] = {0};
        if (node_utils_get_hardware_id(hw_id, sizeof(hw_id)) == ESP_OK) {
            strlcpy(s_node_id, hw_id, sizeof(s_node_id));
            ESP_LOGW(TAG, "Node ID not set, using hardware_id: %s", s_node_id);
        } else {
            strlcpy(s_node_id, params->default_node_id, sizeof(s_node_id));
            ESP_LOGW(TAG, "Node ID not set, using default: %s", s_node_id);
        }
    }
    node_info->node_uid = s_node_id;

    if (config_storage_get_gh_uid(s_gh_uid, sizeof(s_gh_uid)) == ESP_OK) {
        node_info->gh_uid = s_gh_uid;
    } else {
        strlcpy(s_gh_uid, params->default_gh_uid, sizeof(s_gh_uid));
        node_info->gh_uid = s_gh_uid;
    }

    if (config_storage_get_zone_uid(s_zone_uid, sizeof(s_zone_uid)) == ESP_OK) {
        node_info->zone_uid = s_zone_uid;
    } else {
        strlcpy(s_zone_uid, params->default_zone_uid, sizeof(s_zone_uid));
        node_info->zone_uid = s_zone_uid;
    }
}

static esp_err_t config_apply_populate_mqtt_config(mqtt_manager_config_t *mqtt_config) {
    if (mqtt_config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    config_storage_mqtt_t storage_cfg;
    esp_err_t err = config_storage_get_mqtt(&storage_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read MQTT config: %s", esp_err_to_name(err));
        return err;
    }

    strlcpy(s_mqtt_host, storage_cfg.host, sizeof(s_mqtt_host));
    strlcpy(s_mqtt_username, storage_cfg.username, sizeof(s_mqtt_username));
    strlcpy(s_mqtt_password, storage_cfg.password, sizeof(s_mqtt_password));

    mqtt_config->host = s_mqtt_host;
    mqtt_config->port = storage_cfg.port;
    mqtt_config->keepalive = storage_cfg.keepalive;
    mqtt_config->client_id = NULL;
    mqtt_config->username = (strlen(s_mqtt_username) > 0) ? s_mqtt_username : NULL;
    mqtt_config->password = (strlen(s_mqtt_password) > 0) ? s_mqtt_password : NULL;
    mqtt_config->use_tls = storage_cfg.use_tls;

    return ESP_OK;
}

esp_err_t config_apply_mqtt(const cJSON *new_config,
                            const cJSON *previous_config,
                            const config_apply_mqtt_params_t *params,
                            config_apply_result_t *result) {
    if (params == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!config_apply_mqtt_changed(previous_config, new_config)) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "MQTT settings changed, reinitializing client");

    if (mqtt_manager_is_connected()) {
        mqtt_manager_stop();
        vTaskDelay(pdMS_TO_TICKS(300));
    }

    mqtt_manager_deinit();
    vTaskDelay(pdMS_TO_TICKS(200));

    mqtt_manager_config_t mqtt_config = {0};
    esp_err_t err = config_apply_populate_mqtt_config(&mqtt_config);
    if (err != ESP_OK) {
        return err;
    }

    mqtt_node_info_t node_info = {0};
    config_apply_populate_node_info(&node_info, params);

    err = mqtt_manager_init(&mqtt_config, &node_info);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to init MQTT manager: %s", esp_err_to_name(err));
        return err;
    }

    if (params->config_cb) {
        mqtt_manager_register_config_cb(params->config_cb, params->user_ctx);
    }
    if (params->command_cb) {
        mqtt_manager_register_command_cb(params->command_cb, params->user_ctx);
    }
    if (params->connection_cb) {
        mqtt_manager_register_connection_cb(params->connection_cb, params->user_ctx);
    }

    err = mqtt_manager_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT manager: %s", esp_err_to_name(err));
        return err;
    }

    config_apply_result_add(result, "mqtt");
    ESP_LOGI(TAG, "MQTT client restarted successfully");
    return ESP_OK;
}

esp_err_t config_apply_channels_pump(config_apply_result_t *result) {
    esp_err_t err = pump_driver_deinit();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "pump_driver_deinit failed: %s", esp_err_to_name(err));
    }

    err = pump_driver_init_from_config();
    if (err == ESP_OK) {
        config_apply_result_add(result, "pump_driver");
        ESP_LOGI(TAG, "Pump driver reinitialized");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No pump channels found in config");
        err = ESP_OK;
    } else {
        ESP_LOGE(TAG, "Failed to init pump driver: %s", esp_err_to_name(err));
    }

    return err;
}

esp_err_t config_apply_channels_relay(config_apply_result_t *result) {
    esp_err_t err = relay_driver_deinit();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "relay_driver_deinit failed: %s", esp_err_to_name(err));
    }

    err = relay_driver_init_from_config();
    if (err == ESP_OK) {
        config_apply_result_add(result, "relay_driver");
        ESP_LOGI(TAG, "Relay driver reinitialized");
    } else if (err == ESP_ERR_NOT_FOUND) {
        ESP_LOGW(TAG, "No relay channels found in config");
        err = ESP_OK;
    } else {
        ESP_LOGE(TAG, "Failed to init relay driver: %s", esp_err_to_name(err));
    }

    return err;
}

esp_err_t config_apply_publish_ack(const config_apply_result_t *result) {
    if (result == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    cJSON *ack = cJSON_CreateObject();
    if (ack == NULL) {
        return ESP_ERR_NO_MEM;
    }

    cJSON_AddStringToObject(ack, "status", "ACK");
    cJSON_AddNumberToObject(ack, "applied_at", (double)node_utils_get_timestamp_seconds());

    cJSON *restarted = cJSON_AddArrayToObject(ack, "restarted");
    if (restarted == NULL) {
        cJSON_Delete(ack);
        return ESP_ERR_NO_MEM;
    }

    for (size_t i = 0; i < result->count; i++) {
        cJSON_AddItemToArray(restarted, cJSON_CreateString(result->components[i]));
    }

    char *json_str = cJSON_PrintUnformatted(ack);
    if (json_str == NULL) {
        cJSON_Delete(ack);
        return ESP_ERR_NO_MEM;
    }

    esp_err_t err = mqtt_manager_publish_config_response(json_str);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to publish config ACK: %s", esp_err_to_name(err));
    }

    free(json_str);
    cJSON_Delete(ack);
    return err;
}
