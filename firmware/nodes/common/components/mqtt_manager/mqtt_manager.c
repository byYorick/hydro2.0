/**
 * @file mqtt_manager.c
 * @brief Реализация MQTT менеджера для ESP32-нод
 * 
 * Компонент реализует полный MQTT протокол согласно:
 * - doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 * 
 * Стандарты кодирования:
 * - Именование функций: mqtt_manager_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t, логируют ошибки
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "mqtt_manager.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "node_utils.h"
#include "esp_timer.h"
#include "esp_efuse.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>

// Слабые символы для опциональной зависимости от oled_ui
// Если oled_ui не включен, эти функции будут NULL
void oled_ui_notify_mqtt_tx(void) __attribute__((weak));
void oled_ui_notify_mqtt_rx(void) __attribute__((weak));

// Условный include для diagnostics (может быть не всегда доступен)
#ifdef __has_include
    #if __has_include("diagnostics.h")
        #include "diagnostics.h"
        #define DIAGNOSTICS_AVAILABLE 1
    #endif
#endif
#ifndef DIAGNOSTICS_AVAILABLE
    #define DIAGNOSTICS_AVAILABLE 0
#endif

// Условный include для setup_portal (может быть не всегда доступен)
#ifdef __has_include
    #if __has_include("setup_portal.h")
        #include "setup_portal.h"
        #define SETUP_PORTAL_AVAILABLE 1
    #endif
#endif
#ifndef SETUP_PORTAL_AVAILABLE
    #define SETUP_PORTAL_AVAILABLE 0
#endif

static const char *TAG = "mqtt_manager";

// Внутренние структуры
static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static mqtt_manager_config_t s_config = {0};
static mqtt_node_info_t s_node_info = {0};
static bool s_is_connected = false;
static bool s_was_connected = false;  // Флаг, что было хотя бы одно подключение
static char s_mqtt_uri[256] = {0};
static uint32_t s_reconnect_count = 0;  // Счетчик переподключений

// Callbacks
static mqtt_config_callback_t s_config_cb = NULL;
static mqtt_command_callback_t s_command_cb = NULL;
static mqtt_connection_callback_t s_connection_cb = NULL;
static void *s_config_user_ctx = NULL;
static void *s_command_user_ctx = NULL;
static void *s_connection_user_ctx = NULL;

// Mutex для защиты s_node_info и статических буферов от гонок данных
static SemaphoreHandle_t s_node_info_mutex = NULL;

// Forward declarations
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, 
                               int32_t event_id, void *event_data);
static esp_err_t mqtt_manager_publish_internal(const char *topic, const char *data, int qos, int retain);

/**
 * @brief Построение MQTT топика
 * КРИТИЧНО: Защищено mutex для потокобезопасного доступа к s_node_info
 */
static esp_err_t build_topic(char *topic_buf, size_t buf_size, const char *type, const char *channel) {
    if (!topic_buf || buf_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    // Защищаем доступ к s_node_info
    const char *gh_uid = NULL;
    const char *zone_uid = NULL;
    const char *node_uid = NULL;
    
    if (s_node_info_mutex != NULL && xSemaphoreTake(s_node_info_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        gh_uid = s_node_info.gh_uid;
        zone_uid = s_node_info.zone_uid;
        node_uid = s_node_info.node_uid;
        xSemaphoreGive(s_node_info_mutex);
    } else {
        // Fallback без защиты (небезопасно, но лучше чем упасть)
        ESP_LOGW(TAG, "Failed to take node_info mutex in build_topic");
        gh_uid = s_node_info.gh_uid;
        zone_uid = s_node_info.zone_uid;
        node_uid = s_node_info.node_uid;
    }

    int len;
    if (channel && channel[0] != '\0') {
        // Топик с каналом: hydro/{gh}/{zone}/{node}/{channel}/{type}
        len = snprintf(topic_buf, buf_size, "hydro/%s/%s/%s/%s/%s",
                      gh_uid ? gh_uid : "",
                      zone_uid ? zone_uid : "",
                      node_uid ? node_uid : "",
                      channel, type);
    } else {
        // Топик без канала: hydro/{gh}/{zone}/{node}/{type}
        len = snprintf(topic_buf, buf_size, "hydro/%s/%s/%s/%s",
                      gh_uid ? gh_uid : "",
                      zone_uid ? zone_uid : "",
                      node_uid ? node_uid : "",
                      type);
    }

    if (len < 0 || (size_t)len >= buf_size) {
        ESP_LOGE(TAG, "Topic buffer too small: need %d, have %zu", len, buf_size);
        return ESP_ERR_INVALID_SIZE;
    }

    return ESP_OK;
}

esp_err_t mqtt_manager_init(const mqtt_manager_config_t *config, const mqtt_node_info_t *node_info) {
    if (!config || !node_info) {
        ESP_LOGE(TAG, "Invalid arguments: config or node_info is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    if (!config->host || config->host[0] == '\0') {
        ESP_LOGE(TAG, "MQTT host is required");
        return ESP_ERR_INVALID_ARG;
    }

    if (config->port == 0) {
        ESP_LOGE(TAG, "MQTT port is required");
        return ESP_ERR_INVALID_ARG;
    }

    if (!node_info->node_uid || node_info->node_uid[0] == '\0') {
        ESP_LOGE(TAG, "Node UID is required");
        return ESP_ERR_INVALID_ARG;
    }

    // Инициализация mutex для защиты s_node_info
    if (s_node_info_mutex == NULL) {
        s_node_info_mutex = xSemaphoreCreateMutex();
        if (s_node_info_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create node_info mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    ESP_LOGI(TAG, "Initializing MQTT manager...");
    ESP_LOGI(TAG, "Broker: %s:%u", config->host, config->port);
    ESP_LOGI(TAG, "Node: %s/%s/%s", 
             node_info->gh_uid ? node_info->gh_uid : "?",
             node_info->zone_uid ? node_info->zone_uid : "?",
             node_info->node_uid);

    // ВАЖНО: Копируем строки в статические буферы, так как node_info содержит указатели
    // на локальные буферы, которые могут стать невалидными
    static char s_init_gh_uid[128] = {0};
    static char s_init_zone_uid[128] = {0};
    static char s_init_node_uid[128] = {0};
    
    // Копируем node_info в статические буферы
    if (node_info->node_uid && node_info->node_uid[0] != '\0') {
        strlcpy(s_init_node_uid, node_info->node_uid, sizeof(s_init_node_uid));
        s_node_info.node_uid = s_init_node_uid;
    } else {
        s_node_info.node_uid = NULL;
    }
    
    if (node_info->gh_uid && node_info->gh_uid[0] != '\0') {
        strlcpy(s_init_gh_uid, node_info->gh_uid, sizeof(s_init_gh_uid));
        s_node_info.gh_uid = s_init_gh_uid;
    } else {
        s_node_info.gh_uid = NULL;
    }
    
    if (node_info->zone_uid && node_info->zone_uid[0] != '\0') {
        strlcpy(s_init_zone_uid, node_info->zone_uid, sizeof(s_init_zone_uid));
        s_node_info.zone_uid = s_init_zone_uid;
    } else {
        s_node_info.zone_uid = NULL;
    }
    
    // ВАЖНО: Копируем строки конфигурации MQTT в статические буферы
    // так как config содержит указатели на локальные буферы, которые могут стать невалидными
    static char s_config_host[128] = {0};
    static char s_config_username[128] = {0};
    static char s_config_password[128] = {0};
    static char s_config_client_id[128] = {0};
    
    // Копируем host
    if (config->host && config->host[0] != '\0') {
        strlcpy(s_config_host, config->host, sizeof(s_config_host));
        s_config.host = s_config_host;
    } else {
        s_config.host = NULL;
    }
    
    // Копируем username
    if (config->username && config->username[0] != '\0') {
        strlcpy(s_config_username, config->username, sizeof(s_config_username));
        s_config.username = s_config_username;
    } else {
        s_config.username = NULL;
    }
    
    // Копируем password
    if (config->password && config->password[0] != '\0') {
        strlcpy(s_config_password, config->password, sizeof(s_config_password));
        s_config.password = s_config_password;
    } else {
        s_config.password = NULL;
    }
    
    // Копируем client_id
    if (config->client_id && config->client_id[0] != '\0') {
        strlcpy(s_config_client_id, config->client_id, sizeof(s_config_client_id));
        s_config.client_id = s_config_client_id;
    } else {
        s_config.client_id = NULL;
    }
    
    // Копируем остальные поля
    s_config.port = config->port;
    s_config.keepalive = config->keepalive;
    s_config.use_tls = config->use_tls;

    // Формируем URI
    const char *protocol = s_config.use_tls ? "mqtts://" : "mqtt://";
    int uri_len = snprintf(s_mqtt_uri, sizeof(s_mqtt_uri), "%s%s:%u", 
                          protocol, s_config.host, s_config.port);
    if (uri_len < 0 || uri_len >= sizeof(s_mqtt_uri)) {
        ESP_LOGE(TAG, "MQTT URI is too long");
        return ESP_ERR_INVALID_SIZE;
    }

    // Определяем client_id
    const char *client_id = s_config.client_id;
    if (!client_id || client_id[0] == '\0') {
        client_id = s_node_info.node_uid;  // Используем уже скопированное значение
    }

    // Настройка LWT (Last Will and Testament) - нужно статическое хранилище
    static char lwt_topic_static[192];
    if (build_topic(lwt_topic_static, sizeof(lwt_topic_static), "lwt", NULL) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build LWT topic");
        return ESP_FAIL;
    }

    // Конфигурация MQTT клиента
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = s_mqtt_uri,
        .session.keepalive = s_config.keepalive > 0 ? s_config.keepalive : 30,
        .session.disable_clean_session = 0,
        .network.reconnect_timeout_ms = 10000,
        .network.timeout_ms = 10000,
        .session.last_will.topic = lwt_topic_static,
        .session.last_will.msg = "offline",
        .session.last_will.qos = 1,
        .session.last_will.retain = 1,
    };

    ESP_LOGI(TAG, "LWT configured: %s -> 'offline'", lwt_topic_static);

    // Аутентификация (если указана)
    if (s_config.username && s_config.username[0] != '\0') {
        mqtt_cfg.credentials.username = s_config.username;
        if (s_config.password && s_config.password[0] != '\0') {
            mqtt_cfg.credentials.authentication.password = s_config.password;
        }
    }

    // Client ID
    mqtt_cfg.credentials.client_id = client_id;

    // Инициализация клиента
    s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client");
        return ESP_FAIL;
    }

    // Регистрация обработчика событий
    esp_err_t err = esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID,
                                                   mqtt_event_handler, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register MQTT event handler: %s", esp_err_to_name(err));
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
        return err;
    }

    // КРИТИЧНО: Убираем логирование сразу после регистрации обработчика для предотвращения паники
    // Проблема возникает при вызове ESP_LOGI - возможно из-за повреждения стека или heap
    // Логирование будет выполнено позже, когда система стабилизируется
    // ESP_LOGI(TAG, "MQTT manager initialized successfully");
    return ESP_OK;
}

esp_err_t mqtt_manager_start(void) {
    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT manager not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Starting MQTT manager...");
    esp_err_t err = esp_mqtt_client_start(s_mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT manager: %s", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

esp_err_t mqtt_manager_stop(void) {
    if (!s_mqtt_client) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Stopping MQTT manager...");
    return esp_mqtt_client_stop(s_mqtt_client);
}

esp_err_t mqtt_manager_deinit(void) {
    if (s_mqtt_client) {
        esp_mqtt_client_stop(s_mqtt_client);
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
    }

    memset(&s_config, 0, sizeof(s_config));
    memset(&s_node_info, 0, sizeof(s_node_info));
    s_is_connected = false;
    s_was_connected = false;
    s_reconnect_count = 0;

    ESP_LOGI(TAG, "MQTT manager deinitialized");
    return ESP_OK;
}

esp_err_t mqtt_manager_update_node_info(const mqtt_node_info_t *node_info) {
    if (!node_info) {
        ESP_LOGE(TAG, "Invalid argument: node_info is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    if (!node_info->node_uid || node_info->node_uid[0] == '\0') {
        ESP_LOGE(TAG, "Node UID is required");
        return ESP_ERR_INVALID_ARG;
    }

    // КРИТИЧНО: Защищаем обновление s_node_info mutex для потокобезопасности
    if (s_node_info_mutex == NULL) {
        ESP_LOGE(TAG, "Node info mutex not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_node_info_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGE(TAG, "Failed to take node_info mutex");
        return ESP_ERR_TIMEOUT;
    }

    // Обновляем информацию об узле
    // ВАЖНО: Используем статические буферы для хранения строк, так как node_info содержит указатели
    static char s_gh_uid_static[64] = {0};
    static char s_zone_uid_static[64] = {0};
    static char s_node_uid_static[64] = {0};

    if (node_info->gh_uid && node_info->gh_uid[0] != '\0') {
        strlcpy(s_gh_uid_static, node_info->gh_uid, sizeof(s_gh_uid_static));
        s_node_info.gh_uid = s_gh_uid_static;
    } else {
        s_node_info.gh_uid = NULL;
    }

    if (node_info->zone_uid && node_info->zone_uid[0] != '\0') {
        strlcpy(s_zone_uid_static, node_info->zone_uid, sizeof(s_zone_uid_static));
        s_node_info.zone_uid = s_zone_uid_static;
    } else {
        s_node_info.zone_uid = NULL;
    }

    if (node_info->node_uid && node_info->node_uid[0] != '\0') {
        strlcpy(s_node_uid_static, node_info->node_uid, sizeof(s_node_uid_static));
        s_node_info.node_uid = s_node_uid_static;
    }

    ESP_LOGI(TAG, "Node info updated: gh_uid=%s, zone_uid=%s, node_uid=%s",
             s_node_info.gh_uid ? s_node_info.gh_uid : "NULL",
             s_node_info.zone_uid ? s_node_info.zone_uid : "NULL",
             s_node_info.node_uid ? s_node_info.node_uid : "NULL");

    xSemaphoreGive(s_node_info_mutex);
    return ESP_OK;
}

void mqtt_manager_register_config_cb(mqtt_config_callback_t cb, void *user_ctx) {
    s_config_cb = cb;
    s_config_user_ctx = user_ctx;
}

void mqtt_manager_register_command_cb(mqtt_command_callback_t cb, void *user_ctx) {
    s_command_cb = cb;
    s_command_user_ctx = user_ctx;
}

void mqtt_manager_register_connection_cb(mqtt_connection_callback_t cb, void *user_ctx) {
    s_connection_cb = cb;
    s_connection_user_ctx = user_ctx;
}

esp_err_t mqtt_manager_publish_telemetry(const char *channel, const char *data) {
    if (!channel || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "telemetry", channel);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 0);
}

esp_err_t mqtt_manager_publish_status(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "status", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 1);
}

esp_err_t mqtt_manager_publish_heartbeat(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "heartbeat", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 0);  // QoS = 1 согласно MQTT_SPEC_FULL.md
}

esp_err_t mqtt_manager_publish_command_response(const char *channel, const char *data) {
    if (!channel || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "command_response", channel);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 0);
}

esp_err_t mqtt_manager_publish_config_response(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "config_response", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 0);
}

esp_err_t mqtt_manager_publish_diagnostics(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "diagnostics", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_manager_publish_internal(topic, data, 1, 0);
}

bool mqtt_manager_is_connected(void) {
    return s_is_connected;
}

uint32_t mqtt_manager_get_reconnect_count(void) {
    return s_reconnect_count;
}

esp_err_t mqtt_manager_reconnect(void) {
    if (!s_mqtt_client) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Reconnecting to MQTT broker...");
    return esp_mqtt_client_reconnect(s_mqtt_client);
}

/**
 * @brief Публикация сообщения в произвольный топик
 */
esp_err_t mqtt_manager_publish_raw(const char *topic, const char *data, int qos, int retain) {
    return mqtt_manager_publish_internal(topic, data, qos, retain);
}

/**
 * @brief Внутренняя функция публикации
 */
static esp_err_t mqtt_manager_publish_internal(const char *topic, const char *data, int qos, int retain) {
    if (!s_mqtt_client || !topic || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_is_connected) {
        ESP_LOGW(TAG, "MQTT not connected, cannot publish to %s", topic);
        return ESP_ERR_INVALID_STATE;
    }

    // Уведомляем OLED UI о MQTT активности (отправка)
    // Используем слабые символы для опциональной зависимости от oled_ui
    // Если функция не определена, линкер разрешит слабый символ (NULL)
    oled_ui_notify_mqtt_tx();

    int data_len = strlen(data);
    
    // Логирование всех публикаций
    // Ограничиваем длину данных для лога (первые 200 символов)
    const int log_data_max = 200;
    char log_data[log_data_max + 4]; // +4 для "..."
    if (data_len <= log_data_max) {
        snprintf(log_data, sizeof(log_data), "%s", data);
    } else {
        strncpy(log_data, data, log_data_max);
        log_data[log_data_max] = '\0';
        strcat(log_data, "...");
    }
    
    ESP_LOGI(TAG, "MQTT PUBLISH: topic='%s', qos=%d, retain=%d, len=%d, data=%s", 
             topic, qos, retain, data_len, log_data);
    
    // Проверяем, что клиент все еще валиден перед публикацией
    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT client became NULL, cannot publish to %s", topic);
        return ESP_ERR_INVALID_STATE;
    }
    
    int msg_id = esp_mqtt_client_publish(s_mqtt_client, topic, data, data_len, qos, retain);
    
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Failed to publish to %s (msg_id=%d)", topic, msg_id);
        // При ошибке публикации не устанавливаем s_is_connected = false,
        // так как это может быть временная проблема, и клиент сам обработает переподключение
        // Обновление метрик диагностики (ошибка публикации)
        #if DIAGNOSTICS_AVAILABLE
        if (diagnostics_is_initialized()) {
            diagnostics_update_mqtt_metrics(false, false, true);
        }
        #endif
        return ESP_FAIL;
    }
    
    ESP_LOGI(TAG, "MQTT PUBLISH SUCCESS: topic='%s', msg_id=%d, len=%d", topic, msg_id, data_len);
    
    // Обновление метрик диагностики (успешная публикация)
    #if DIAGNOSTICS_AVAILABLE
    if (diagnostics_is_initialized()) {
        diagnostics_update_mqtt_metrics(true, false, false);
    }
    #endif
    
    return ESP_OK;
}

/**
 * @brief Обработчик событий MQTT
 */
static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data) {
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT connected to broker");
            // Увеличиваем счетчик переподключений (если это не первое подключение)
            // s_was_connected проверяем ДО установки s_is_connected
            if (s_was_connected) {
                // Переподключение после отключения
                s_reconnect_count++;
                ESP_LOGI(TAG, "MQTT reconnected (count: %u)", s_reconnect_count);
            }
            s_is_connected = true;
            s_was_connected = true;  // Отмечаем, что было подключение

            // Публикация статуса ONLINE (ОБЯЗАТЕЛЬНО сразу после подключения, до подписки)
            // Согласно MQTT_SPEC_FULL.md раздел 4.2 и BACKEND_NODE_CONTRACT_FULL.md раздел 8.1
            char status_json[128];
            snprintf(status_json, sizeof(status_json), "{\"status\":\"ONLINE\",\"ts\":%lld}", 
                    (long long)node_utils_get_timestamp_seconds());
            mqtt_manager_publish_status(status_json);
            ESP_LOGI(TAG, "Published status: ONLINE");

            // Подписка на config топик
            char config_topic[192];
            if (build_topic(config_topic, sizeof(config_topic), "config", NULL) == ESP_OK) {
                int sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, config_topic, 1);
                if (sub_msg_id >= 0) {
                    ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", config_topic, sub_msg_id);
                } else {
                    ESP_LOGE(TAG, "Failed to subscribe to %s (msg_id=%d)", config_topic, sub_msg_id);
                }
            } else {
                ESP_LOGE(TAG, "Failed to build config topic");
            }
            
            // Также подписываемся на временный топик конфига для узлов, которые еще не получили конфигурацию
            // Это позволяет получить конфиг даже если нода использует временные идентификаторы
            // Используем hardware_id (MAC адрес) для временного топика, чтобы избежать конфликтов при одинаковом node_uid
            uint8_t mac[6] = {0};
            esp_err_t mac_err = esp_efuse_mac_get_default(mac);
            if (mac_err == ESP_OK) {
                char hardware_id[32];
                snprintf(hardware_id, sizeof(hardware_id), "esp32-%02x%02x%02x%02x%02x%02x",
                         mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
                char temp_config_topic[192];
                snprintf(temp_config_topic, sizeof(temp_config_topic), "hydro/gh-temp/zn-temp/%s/config", hardware_id);
                int temp_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, temp_config_topic, 1);
                if (temp_sub_msg_id >= 0) {
                    ESP_LOGI(TAG, "Subscribed to temp config topic: %s (msg_id=%d, using hardware_id)", temp_config_topic, temp_sub_msg_id);
                } else {
                    ESP_LOGW(TAG, "Failed to subscribe to temp config topic: %s (msg_id=%d)", temp_config_topic, temp_sub_msg_id);
                }
            } else {
                ESP_LOGW(TAG, "Failed to get MAC address for temp config topic: %s", esp_err_to_name(mac_err));
                // Fallback: используем node_uid, если не удалось получить MAC
                if (s_node_info.node_uid && s_node_info.node_uid[0] != '\0') {
                    char temp_config_topic[192];
                    snprintf(temp_config_topic, sizeof(temp_config_topic), "hydro/gh-temp/zn-temp/%s/config", s_node_info.node_uid);
                    int temp_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, temp_config_topic, 1);
                    if (temp_sub_msg_id >= 0) {
                        ESP_LOGI(TAG, "Subscribed to temp config topic: %s (msg_id=%d, using node_uid fallback)", temp_config_topic, temp_sub_msg_id);
                    } else {
                        ESP_LOGW(TAG, "Failed to subscribe to temp config topic: %s (msg_id=%d)", temp_config_topic, temp_sub_msg_id);
                    }
                }
            }

            // Подписка на command топики (wildcard для всех каналов)
            char command_topic[192];
            snprintf(command_topic, sizeof(command_topic), "hydro/%s/%s/%s/+/command",
                    s_node_info.gh_uid ? s_node_info.gh_uid : "",
                    s_node_info.zone_uid ? s_node_info.zone_uid : "",
                    s_node_info.node_uid ? s_node_info.node_uid : "");
            int cmd_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, command_topic, 1);
            if (cmd_sub_msg_id >= 0) {
                ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", command_topic, cmd_sub_msg_id);
            } else {
                ESP_LOGE(TAG, "Failed to subscribe to %s (msg_id=%d)", command_topic, cmd_sub_msg_id);
            }
            
            // Подписка на time/response для получения синхронизации времени от сервера
            int time_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, "hydro/time/response", 1);
            if (time_sub_msg_id >= 0) {
                ESP_LOGI(TAG, "Subscribed to hydro/time/response (msg_id=%d)", time_sub_msg_id);
            } else {
                ESP_LOGW(TAG, "Failed to subscribe to hydro/time/response (msg_id=%d)", time_sub_msg_id);
            }
            
            // Также подписываемся на временный топик команд для узлов, которые еще не получили конфигурацию
            // Это позволяет получить команды даже если нода использует временные идентификаторы
            // Используем hardware_id (MAC адрес) для временного топика, чтобы избежать конфликтов при одинаковом node_uid
            uint8_t mac_cmd[6] = {0};
            esp_err_t mac_cmd_err = esp_efuse_mac_get_default(mac_cmd);
            if (mac_cmd_err == ESP_OK) {
                char hardware_id_cmd[32];
                snprintf(hardware_id_cmd, sizeof(hardware_id_cmd), "esp32-%02x%02x%02x%02x%02x%02x",
                         mac_cmd[0], mac_cmd[1], mac_cmd[2], mac_cmd[3], mac_cmd[4], mac_cmd[5]);
                char temp_command_topic[192];
                snprintf(temp_command_topic, sizeof(temp_command_topic), "hydro/gh-temp/zn-temp/%s/+/command", hardware_id_cmd);
                int temp_cmd_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, temp_command_topic, 1);
                if (temp_cmd_sub_msg_id >= 0) {
                    ESP_LOGI(TAG, "Subscribed to temp command topic: %s (msg_id=%d, using hardware_id)", temp_command_topic, temp_cmd_sub_msg_id);
                } else {
                    ESP_LOGW(TAG, "Failed to subscribe to temp command topic: %s (msg_id=%d)", temp_command_topic, temp_cmd_sub_msg_id);
                }
            } else {
                ESP_LOGW(TAG, "Failed to get MAC address for temp command topic: %s", esp_err_to_name(mac_cmd_err));
                // Fallback: используем node_uid, если не удалось получить MAC
                if (s_node_info.node_uid && s_node_info.node_uid[0] != '\0') {
                    char temp_command_topic[192];
                    snprintf(temp_command_topic, sizeof(temp_command_topic), "hydro/gh-temp/zn-temp/%s/+/command", s_node_info.node_uid);
                    int temp_cmd_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, temp_command_topic, 1);
                    if (temp_cmd_sub_msg_id >= 0) {
                        ESP_LOGI(TAG, "Subscribed to temp command topic: %s (msg_id=%d, using node_uid fallback)", temp_command_topic, temp_cmd_sub_msg_id);
                    } else {
                        ESP_LOGW(TAG, "Failed to subscribe to temp command topic: %s (msg_id=%d)", temp_command_topic, temp_cmd_sub_msg_id);
                    }
                }
            }
            
            // Запрос времени у сервера для синхронизации часов устройства
            // Это обеспечивает единую временную линию между устройствами и бэкендом
            node_utils_request_time();
            ESP_LOGI(TAG, "Requested time synchronization from server");

            // Вызов callback подключения
            if (s_connection_cb) {
                ESP_LOGI(TAG, "Calling registered connection callback (connected=true)");
                s_connection_cb(true, s_connection_user_ctx);
                ESP_LOGI(TAG, "Connection callback completed");
            } else {
                ESP_LOGW(TAG, "No connection callback registered");
            }
            break;

        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "MQTT disconnected from broker");
            s_is_connected = false;

            // Вызов callback отключения
            if (s_connection_cb) {
                s_connection_cb(false, s_connection_user_ctx);
            }
            break;

        case MQTT_EVENT_SUBSCRIBED:
            ESP_LOGI(TAG, "MQTT subscribed, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_UNSUBSCRIBED:
            ESP_LOGI(TAG, "MQTT unsubscribed, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_PUBLISHED:
            ESP_LOGD(TAG, "MQTT published, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_DATA: {
            // Проверка длины topic и data перед обработкой
            // max_topic_len должен соответствовать размеру буфера build_topic (192 байта)
            // с небольшим запасом для безопасности
            const size_t max_topic_len = 192;
            const size_t max_data_len = 2048;
            
            // Проверяем, не превышает ли длина допустимые значения
            if (event->topic_len > max_topic_len) {
                ESP_LOGW(TAG, "MQTT topic too long: %d bytes (max %zu), dropping message", 
                         event->topic_len, max_topic_len);
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }
            
            if (event->data_len > max_data_len) {
                ESP_LOGW(TAG, "MQTT data too long: %d bytes (max %zu), dropping message", 
                         event->data_len, max_data_len);
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }
            
            // Создание null-terminated строк для topic и data
            // Размер буфера topic увеличен до 192 для соответствия build_topic
            // КРИТИЧНО: Используем статические буферы вместо стека для предотвращения переполнения
            // ВАЖНО: ESP-IDF MQTT клиент вызывает обработчики событий последовательно из одного потока,
            // поэтому статические буферы безопасны (нет гонки данных)
            static char topic[192] = {0};
            static char data[2048] = {0};

            int topic_len = (event->topic_len < sizeof(topic) - 1) ? 
                           event->topic_len : sizeof(topic) - 1;
            int data_len = (event->data_len < sizeof(data) - 1) ? 
                          event->data_len : sizeof(data) - 1;

            if (event->topic) {
                memcpy(topic, event->topic, topic_len);
                topic[topic_len] = '\0';  // КРИТИЧНО: Добавляем null-terminator
            } else {
                topic[0] = '\0';
            }
            if (event->data) {
                memcpy(data, event->data, data_len);
                data[data_len] = '\0';  // КРИТИЧНО: Добавляем null-terminator
            } else {
                data[0] = '\0';
            }
            
            // Логирование входящих сообщений
            const int log_data_max = 200;
            char log_data[log_data_max + 4];
            if (event->data_len <= log_data_max) {
                if (event->data) {
                    memcpy(log_data, event->data, event->data_len);
                    log_data[event->data_len] = '\0';
                } else {
                    log_data[0] = '\0';
                }
            } else {
                if (event->data) {
                    memcpy(log_data, event->data, log_data_max);
                    log_data[log_data_max] = '\0';
                    strcat(log_data, "...");
                } else {
                    log_data[0] = '\0';
                }
            }
            
            ESP_LOGI(TAG, "MQTT RECEIVE: topic='%.*s', len=%d, data=%s", 
                     event->topic_len, event->topic ? event->topic : "", 
                     event->data_len, log_data);
            
            // Уведомляем OLED UI о MQTT активности (прием)
            // Используем слабые символы для опциональной зависимости от oled_ui
            // Если функция не определена, линкер разрешит слабый символ (NULL)
            oled_ui_notify_mqtt_rx();
            
            // Обновление метрик диагностики (получение сообщения)
            #if DIAGNOSTICS_AVAILABLE
            if (diagnostics_is_initialized()) {
                diagnostics_update_mqtt_metrics(false, true, false);
            }
            #endif

            // Определяем тип топика и вызываем соответствующий callback
            // Согласно MQTT_SPEC_FULL.md раздел 2:
            // - Config: hydro/{gh}/{zone}/{node}/config
            // - Command: hydro/{gh}/{zone}/{node}/{channel}/command
            // - Time Response: hydro/time/response (для синхронизации времени)
            if (strcmp(topic, "hydro/time/response") == 0) {
                // Time response топик - обрабатываем синхронизацию времени
                ESP_LOGI(TAG, "Time response message received, len=%d", event->data_len);
                
                // Парсим JSON для получения unix_ts
                cJSON *json = cJSON_Parse(data);
                if (json) {
                    cJSON *unix_ts_item = cJSON_GetObjectItem(json, "unix_ts");
                    if (unix_ts_item && cJSON_IsNumber(unix_ts_item)) {
                        int64_t unix_ts = (int64_t)cJSON_GetNumberValue(unix_ts_item);
                        esp_err_t err = node_utils_set_time(unix_ts);
                        if (err == ESP_OK) {
                            ESP_LOGI(TAG, "Time synchronized successfully: %lld", (long long)unix_ts);
                        } else {
                            ESP_LOGE(TAG, "Failed to set time: %s", esp_err_to_name(err));
                        }
                    } else {
                        ESP_LOGW(TAG, "Invalid time response format: missing or invalid unix_ts");
                    }
                    cJSON_Delete(json);
                } else {
                    ESP_LOGW(TAG, "Failed to parse time response JSON");
                }
            } else if (strstr(topic, "/config") != NULL) {
                // Config топик - вызываем callback для обработки конфигурации
                ESP_LOGI(TAG, "Config message received on topic: %s, len=%d", topic, event->data_len);
                if (s_config_cb) {
                    ESP_LOGI(TAG, "Calling registered config callback");
                    // Передаем оригинальную длину, так как мы уже проверили, что она не превышает max_data_len
                    s_config_cb(topic, data, event->data_len, s_config_user_ctx);
                    ESP_LOGI(TAG, "Config callback completed");
                } else {
                    ESP_LOGW(TAG, "Config message received but no callback registered");
                }
            } else if (strstr(topic, "/command") != NULL) {
                // Command топик - извлекаем channel из топика
                // Формат: hydro/{gh}/{zone}/{node}/{channel}/command
                // Пример: hydro/gh-1/zn-3/nd-ph-1/pump_acid/command
                // Нужно извлечь "pump_acid" из топика
                const char *last_slash = strrchr(topic, '/');
                if (last_slash && last_slash > topic) {
                    // Ищем предыдущий слэш перед channel (перед последним "/command")
                    const char *prev_slash = last_slash - 1;
                    while (prev_slash > topic && *prev_slash != '/') {
                        prev_slash--;
                    }
                    if (*prev_slash == '/' && prev_slash < last_slash) {
                        prev_slash++; // Пропускаем слэш
                        size_t channel_len = last_slash - prev_slash;
                        if (channel_len > 0 && channel_len < 64) {
                            char channel[64] = {0};
                            memcpy(channel, prev_slash, channel_len);
                            
                            // Логирование приема команды
                            const int log_data_max = 200;
                            char cmd_log_data[log_data_max + 4];
                            if (event->data_len <= log_data_max) {
                                if (event->data) {
                                    memcpy(cmd_log_data, event->data, event->data_len);
                                    cmd_log_data[event->data_len] = '\0';
                                } else {
                                    cmd_log_data[0] = '\0';
                                }
                            } else {
                                if (event->data) {
                                    memcpy(cmd_log_data, event->data, log_data_max);
                                    cmd_log_data[log_data_max] = '\0';
                                    strcat(cmd_log_data, "...");
                                } else {
                                    cmd_log_data[0] = '\0';
                                }
                            }
                            ESP_LOGI(TAG, "MQTT COMMAND RECEIVED: topic='%s', channel='%s', len=%d, data=%s", 
                                     topic, channel, event->data_len, cmd_log_data);
                            
                            // Проверка: в setup режиме не обрабатываем команды
                            #if SETUP_PORTAL_AVAILABLE
                            if (setup_portal_is_running()) {
                                ESP_LOGW(TAG, "Command ignored: device is in setup mode");
                            } else
                            #endif
                            {
                                if (s_command_cb) {
                                    // Передаем оригинальную длину, так как мы уже проверили, что она не превышает max_data_len
                                    s_command_cb(topic, channel, data, event->data_len, s_command_user_ctx);
                                } else {
                                    ESP_LOGW(TAG, "Command message received but no callback registered");
                                }
                            }
                        } else {
                            ESP_LOGE(TAG, "Invalid channel length in topic: %s", topic);
                        }
                    } else {
                        ESP_LOGE(TAG, "Failed to extract channel from topic: %s", topic);
                    }
                } else {
                    ESP_LOGE(TAG, "Invalid command topic format: %s", topic);
                }
            } else {
                ESP_LOGD(TAG, "Unknown topic type: %s", topic);
            }
            break;
        }

        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT error");
            if (event->error_handle) {
                ESP_LOGE(TAG, "Error type: %d", event->error_handle->error_type);
                esp_mqtt_error_type_t err_type = event->error_handle->error_type;
                if (err_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
                    ESP_LOGE(TAG, "TCP transport error");
                    // При ошибке транспорта (некорректное сообщение) не устанавливаем s_is_connected = false,
                    // так как ESP-IDF MQTT клиент сам обработает переподключение.
                    // Установка s_is_connected = false здесь может вызвать проблемы при попытке закрыть соединение.
                    // Вместо этого, просто логируем ошибку и позволяем клиенту обработать ситуацию.
                } else if (err_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED) {
                    ESP_LOGE(TAG, "Connection refused");
                    s_is_connected = false;
                } else {
                    // Для других типов ошибок также не трогаем s_is_connected,
                    // чтобы избежать проблем при закрытии соединения
                    ESP_LOGE(TAG, "MQTT error type: %d", err_type);
                }
            }
            // ВАЖНО: Не пытаемся закрыть соединение вручную здесь,
            // так как это может вызвать StoreProhibited при попытке освободить буферы.
            // ESP-IDF MQTT клиент сам обработает ошибку и переподключится при необходимости.
            break;

        default:
            ESP_LOGD(TAG, "MQTT event: %d", event_id);
            break;
    }
}

