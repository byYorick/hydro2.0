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
#include "esp_efuse.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <errno.h>

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
// Конфигурация под крупные config/config_report payload'ы реальных нод.
// 2048 байт оказалось недостаточно уже для binding/config сообщения ~2337 байт.
#define MQTT_MANAGER_BUFFER_SIZE_BYTES 4096
#define MQTT_MANAGER_OUTBOX_LIMIT_BYTES (32 * 1024)
// MQTT callback может вызывать тяжёлые обработчики (config/apply/report), поэтому
// используем увеличенный stack mqtt_task для запаса.
#define MQTT_MANAGER_TASK_STACK_SIZE_BYTES (12 * 1024)

// Внутренние структуры
static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static mqtt_manager_config_t s_config = {0};
static mqtt_node_info_t s_node_info = {0};
static bool s_is_connected = false;
static bool s_client_started = false;
static bool s_was_connected = false;  // Флаг, что было хотя бы одно подключение
static char s_mqtt_uri[256] = {0};
static uint32_t s_reconnect_count = 0;  // Счетчик переподключений
static TaskHandle_t s_mqtt_event_task_handle = NULL;

// Callbacks
static mqtt_config_callback_t s_config_cb = NULL;
static mqtt_command_callback_t s_command_cb = NULL;
static mqtt_connection_callback_t s_connection_cb = NULL;
static void *s_config_user_ctx = NULL;
static void *s_command_user_ctx = NULL;
static void *s_connection_user_ctx = NULL;
static char s_rx_topic_buf[192] = {0};
static char s_rx_payload_buf[MQTT_MANAGER_BUFFER_SIZE_BYTES + 1] = {0};
static int s_rx_expected_len = 0;
static int s_rx_received_len = 0;
static bool s_rx_assembly_active = false;

// Mutex для защиты s_node_info и статических буферов от гонок данных
static SemaphoreHandle_t s_node_info_mutex = NULL;

// Forward declarations
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, 
                               int32_t event_id, void *event_data);
static esp_err_t mqtt_manager_publish_internal(const char *topic, const char *data, int qos, int retain);
static esp_err_t mqtt_manager_create_client(void);
static void mqtt_manager_reset_rx_assembly(void);
static void mqtt_manager_log_error_details(const esp_mqtt_error_codes_t *error_handle);

static bool mqtt_topic_has_suffix(const char *topic, const char *suffix) {
    if (topic == NULL || suffix == NULL) {
        return false;
    }

    size_t topic_len = strlen(topic);
    size_t suffix_len = strlen(suffix);
    if (topic_len <= suffix_len) {
        return false;
    }

    if (topic[topic_len - suffix_len - 1] != '/') {
        return false;
    }

    return strcmp(topic + topic_len - suffix_len, suffix) == 0;
}

static bool mqtt_extract_command_channel(const char *topic, char *channel_buf, size_t channel_buf_size) {
    if (topic == NULL || channel_buf == NULL || channel_buf_size < 2) {
        return false;
    }

    const char *suffix = "/command";
    size_t topic_len = strlen(topic);
    size_t suffix_len = strlen(suffix);
    if (topic_len <= suffix_len + 1 || strcmp(topic + topic_len - suffix_len, suffix) != 0) {
        return false;
    }

    const char *channel_end = topic + topic_len - suffix_len;
    const char *channel_start = channel_end;
    while (channel_start > topic && channel_start[-1] != '/') {
        channel_start--;
    }

    if (channel_start == channel_end) {
        return false;
    }

    size_t channel_len = (size_t)(channel_end - channel_start);
    if (channel_len >= channel_buf_size) {
        return false;
    }

    memcpy(channel_buf, channel_start, channel_len);
    channel_buf[channel_len] = '\0';
    return true;
}

static void mqtt_manager_log_error_details(const esp_mqtt_error_codes_t *error_handle) {
    if (error_handle == NULL) {
        return;
    }

    ESP_LOGE(
        TAG,
        "MQTT error details: type=%d tls_last_esp_err=0x%x tls_stack_err=%d cert_flags=0x%x connect_rc=%d"
#ifdef CONFIG_MQTT_PROTOCOL_5
        " disconnect_rc=%d"
#endif
        " sock_errno=%d (%s)",
        error_handle->error_type,
        (unsigned)error_handle->esp_tls_last_esp_err,
        error_handle->esp_tls_stack_err,
        error_handle->esp_tls_cert_verify_flags,
        error_handle->connect_return_code,
#ifdef CONFIG_MQTT_PROTOCOL_5
        error_handle->disconnect_return_code,
#endif
        error_handle->esp_transport_sock_errno,
        error_handle->esp_transport_sock_errno != 0 ? strerror(error_handle->esp_transport_sock_errno) : "n/a"
    );
}

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

static esp_err_t mqtt_manager_create_client(void) {
    if (s_mqtt_client != NULL) {
        ESP_LOGE(TAG, "MQTT client already created");
        return ESP_ERR_INVALID_STATE;
    }

    if (!s_config.host || s_config.host[0] == '\0' || s_config.port == 0) {
        ESP_LOGE(TAG, "MQTT config is incomplete");
        return ESP_ERR_INVALID_STATE;
    }

    if (!s_node_info.node_uid || s_node_info.node_uid[0] == '\0') {
        ESP_LOGE(TAG, "Node UID is not configured");
        return ESP_ERR_INVALID_STATE;
    }

    const char *protocol = s_config.use_tls ? "mqtts://" : "mqtt://";
    int uri_len = snprintf(s_mqtt_uri, sizeof(s_mqtt_uri), "%s%s:%u",
                           protocol, s_config.host, s_config.port);
    if (uri_len < 0 || uri_len >= sizeof(s_mqtt_uri)) {
        ESP_LOGE(TAG, "MQTT URI is too long");
        return ESP_ERR_INVALID_SIZE;
    }

    const char *client_id = s_config.client_id;
    static char client_id_fallback[32] = {0};
    if (!client_id || client_id[0] == '\0') {
        uint8_t mac[6] = {0};
        if (esp_efuse_mac_get_default(mac) == ESP_OK) {
            snprintf(
                client_id_fallback,
                sizeof(client_id_fallback),
                "esp32-%02x%02x%02x%02x%02x%02x",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
            );
            client_id = client_id_fallback;
        } else {
            client_id = s_node_info.node_uid;
        }
    }

    static char lwt_topic_static[192];
    if (build_topic(lwt_topic_static, sizeof(lwt_topic_static), "lwt", NULL) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to build LWT topic");
        return ESP_FAIL;
    }

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = s_mqtt_uri,
        .session.keepalive = s_config.keepalive > 0 ? s_config.keepalive : 60,
        .session.disable_clean_session = 0,
        .network.reconnect_timeout_ms = 5000,
        .network.timeout_ms = 30000,
        .network.disable_auto_reconnect = false,
        .task.stack_size = MQTT_MANAGER_TASK_STACK_SIZE_BYTES,
        .buffer.size = MQTT_MANAGER_BUFFER_SIZE_BYTES,
        .buffer.out_size = MQTT_MANAGER_BUFFER_SIZE_BYTES,
        .outbox.limit = MQTT_MANAGER_OUTBOX_LIMIT_BYTES,
        .session.last_will.topic = lwt_topic_static,
        .session.last_will.msg = "offline",
        .session.last_will.qos = 1,
        .session.last_will.retain = 1,
    };

    ESP_LOGI(TAG, "LWT configured: %s -> 'offline'", lwt_topic_static);
    ESP_LOGI(TAG, "MQTT task stack: %d bytes", MQTT_MANAGER_TASK_STACK_SIZE_BYTES);
    ESP_LOGI(TAG, "MQTT buffers: in/out=%d bytes, outbox_limit=%llu bytes",
             MQTT_MANAGER_BUFFER_SIZE_BYTES,
             (unsigned long long)MQTT_MANAGER_OUTBOX_LIMIT_BYTES);

    if (s_config.username && s_config.username[0] != '\0') {
        mqtt_cfg.credentials.username = s_config.username;
        if (s_config.password && s_config.password[0] != '\0') {
            mqtt_cfg.credentials.authentication.password = s_config.password;
        }
    }

    mqtt_cfg.credentials.client_id = client_id;
    s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client");
        return ESP_FAIL;
    }

    esp_err_t err = esp_mqtt_client_register_event(
        s_mqtt_client,
        ESP_EVENT_ANY_ID,
        mqtt_event_handler,
        NULL
    );
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register MQTT event handler: %s", esp_err_to_name(err));
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
        return err;
    }

    return ESP_OK;
}

static void mqtt_manager_reset_rx_assembly(void) {
    s_rx_topic_buf[0] = '\0';
    s_rx_payload_buf[0] = '\0';
    s_rx_expected_len = 0;
    s_rx_received_len = 0;
    s_rx_assembly_active = false;
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

    esp_err_t err = mqtt_manager_create_client();
    if (err != ESP_OK) {
        return err;
    }

    return ESP_OK;
}

esp_err_t mqtt_manager_start(void) {
    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT manager not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (s_client_started) {
        ESP_LOGW(TAG, "MQTT manager already started");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Starting MQTT manager...");
    esp_err_t err = esp_mqtt_client_start(s_mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT manager: %s", esp_err_to_name(err));
        return err;
    }

    s_client_started = true;
    return ESP_OK;
}

esp_err_t mqtt_manager_stop(void) {
    if (!s_mqtt_client) {
        return ESP_ERR_INVALID_STATE;
    }

    if (!s_client_started) {
        ESP_LOGW(TAG, "MQTT manager stop requested, but client was not started");
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Stopping MQTT manager...");
    esp_err_t err = esp_mqtt_client_stop(s_mqtt_client);
    if (err == ESP_OK) {
        s_client_started = false;
    }
    return err;
}

esp_err_t mqtt_manager_deinit(void) {
    TaskHandle_t current_task = xTaskGetCurrentTaskHandle();

    if (s_mqtt_event_task_handle != NULL && current_task == s_mqtt_event_task_handle) {
        ESP_LOGE(TAG, "MQTT manager deinit from MQTT task is forbidden");
        return ESP_ERR_INVALID_STATE;
    }

    if (s_mqtt_client) {
        if (s_client_started) {
            esp_err_t stop_err = mqtt_manager_stop();
            if (stop_err != ESP_OK) {
                ESP_LOGE(TAG, "MQTT manager deinit aborted: stop failed: %s", esp_err_to_name(stop_err));
                return stop_err;
            }
        }
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
    }
    if (s_node_info_mutex) {
        vSemaphoreDelete(s_node_info_mutex);
        s_node_info_mutex = NULL;
    }

    memset(&s_config, 0, sizeof(s_config));
    memset(&s_node_info, 0, sizeof(s_node_info));
    memset(s_mqtt_uri, 0, sizeof(s_mqtt_uri));
    s_is_connected = false;
    s_client_started = false;
    s_was_connected = false;
    s_reconnect_count = 0;
    s_mqtt_event_task_handle = NULL;
    s_config_cb = NULL;
    s_command_cb = NULL;
    s_connection_cb = NULL;
    s_config_user_ctx = NULL;
    s_command_user_ctx = NULL;
    s_connection_user_ctx = NULL;
    mqtt_manager_reset_rx_assembly();

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

    ESP_LOGD(TAG, "Node info updated: gh_uid=%s, zone_uid=%s, node_uid=%s",
             s_node_info.gh_uid ? s_node_info.gh_uid : "NULL",
             s_node_info.zone_uid ? s_node_info.zone_uid : "NULL",
             s_node_info.node_uid ? s_node_info.node_uid : "NULL");

    xSemaphoreGive(s_node_info_mutex);
    return ESP_OK;
}

esp_err_t mqtt_manager_get_node_info(mqtt_node_info_t *node_info) {
    if (node_info == NULL) {
        ESP_LOGE(TAG, "Invalid argument: node_info is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    if (s_node_info_mutex == NULL) {
        ESP_LOGW(TAG, "Node info mutex is not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(s_node_info_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take node_info mutex");
        return ESP_ERR_TIMEOUT;
    }

    node_info->gh_uid = s_node_info.gh_uid;
    node_info->zone_uid = s_node_info.zone_uid;
    node_info->node_uid = s_node_info.node_uid;
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

esp_err_t mqtt_manager_publish_config_report(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "config_report", NULL);
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

    if (s_is_connected) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Manual reconnect requested");
    return esp_mqtt_client_reconnect(s_mqtt_client);
}

/**
 * @brief Публикация сообщения в произвольный топик
 */
esp_err_t mqtt_manager_publish_raw(const char *topic, const char *data, int qos, int retain) {
    return mqtt_manager_publish_internal(topic, data, qos, retain);
}

esp_err_t mqtt_manager_subscribe_raw(const char *topic, int qos) {
    if (!topic || topic[0] == '\0') {
        ESP_LOGE(TAG, "Invalid subscribe topic");
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT manager not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    int msg_id = esp_mqtt_client_subscribe(s_mqtt_client, topic, qos);
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Failed to subscribe raw topic: %s", topic);
        return ESP_FAIL;
    }

    ESP_LOGD(TAG, "Subscribed to raw topic: %s (msg_id=%d)", topic, msg_id);
    return ESP_OK;
}

esp_err_t mqtt_manager_unsubscribe_raw(const char *topic) {
    if (!topic || topic[0] == '\0') {
        ESP_LOGE(TAG, "Invalid unsubscribe topic");
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT manager not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    int msg_id = esp_mqtt_client_unsubscribe(s_mqtt_client, topic);
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Failed to unsubscribe raw topic: %s", topic);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Unsubscribed from raw topic: %s (msg_id=%d)", topic, msg_id);
    return ESP_OK;
}

/**
 * @brief Внутренняя функция публикации
 */
static esp_err_t mqtt_manager_publish_internal(const char *topic, const char *data, int qos, int retain) {
    if (!s_mqtt_client || !topic || !data) {
        ESP_LOGE(TAG, "Invalid publish arguments: client=%p topic=%p data=%p", (void *)s_mqtt_client, (void *)topic, (void *)data);
        return ESP_ERR_INVALID_ARG;
    }

    if (topic[0] == '\0') {
        ESP_LOGE(TAG, "Refusing to publish to empty topic");
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_is_connected) {
        ESP_LOGW(TAG, "MQTT not connected, cannot publish to %s", topic);
        return ESP_ERR_INVALID_STATE;
    }

    // Уведомляем OLED UI о MQTT активности (отправка)
    // Используем слабые символы для опциональной зависимости от oled_ui
    // Если функция не определена, линкер разрешит слабый символ (NULL)
    if (oled_ui_notify_mqtt_tx) {
        oled_ui_notify_mqtt_tx();
    }

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
    
    ESP_LOGD(TAG, "MQTT PUBLISH: topic='%s', qos=%d, retain=%d, len=%d, data=%s", 
             topic, qos, retain, data_len, log_data);
    
    // Проверяем, что клиент все еще валиден перед публикацией
    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT client became NULL, cannot publish to %s", topic);
        return ESP_ERR_INVALID_STATE;
    }
    
    int msg_id = esp_mqtt_client_publish(s_mqtt_client, topic, data, data_len, qos, retain);
    
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Failed to publish to %s (msg_id=%d)", topic, msg_id);
        // Не форсируем s_is_connected=false здесь:
        // msg_id<0 может быть временной ошибкой очереди/outbox.
        // Обновление метрик диагностики (ошибка публикации)
        #if DIAGNOSTICS_AVAILABLE
        if (diagnostics_is_initialized()) {
            diagnostics_update_mqtt_metrics(false, false, true);
        }
        #endif
        return ESP_FAIL;
    }
    
    ESP_LOGD(TAG, "MQTT PUBLISH SUCCESS: topic='%s', msg_id=%d, len=%d", topic, msg_id, data_len);
    
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
    if (s_mqtt_event_task_handle == NULL) {
        s_mqtt_event_task_handle = xTaskGetCurrentTaskHandle();
    }

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
            ESP_LOGD(TAG, "Published status: ONLINE");

            // Подписка на config топик
            char config_topic[192];
            if (build_topic(config_topic, sizeof(config_topic), "config", NULL) == ESP_OK) {
                int sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, config_topic, 1);
                if (sub_msg_id >= 0) {
                    ESP_LOGD(TAG, "Subscribed to %s (msg_id=%d)", config_topic, sub_msg_id);
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
                    ESP_LOGD(TAG, "Subscribed to temp config topic: %s (msg_id=%d, using hardware_id)", temp_config_topic, temp_sub_msg_id);
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
                        ESP_LOGD(TAG, "Subscribed to temp config topic: %s (msg_id=%d, using node_uid fallback)", temp_config_topic, temp_sub_msg_id);
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
                ESP_LOGD(TAG, "Subscribed to %s (msg_id=%d)", command_topic, cmd_sub_msg_id);
            } else {
                ESP_LOGE(TAG, "Failed to subscribe to %s (msg_id=%d)", command_topic, cmd_sub_msg_id);
            }
            
            // Подписка на time/response для получения синхронизации времени от сервера
            int time_sub_msg_id = esp_mqtt_client_subscribe(s_mqtt_client, "hydro/time/response", 1);
            if (time_sub_msg_id >= 0) {
                ESP_LOGD(TAG, "Subscribed to hydro/time/response (msg_id=%d)", time_sub_msg_id);
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
                    ESP_LOGD(TAG, "Subscribed to temp command topic: %s (msg_id=%d, using hardware_id)", temp_command_topic, temp_cmd_sub_msg_id);
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
                        ESP_LOGD(TAG, "Subscribed to temp command topic: %s (msg_id=%d, using node_uid fallback)", temp_command_topic, temp_cmd_sub_msg_id);
                    } else {
                        ESP_LOGW(TAG, "Failed to subscribe to temp command topic: %s (msg_id=%d)", temp_command_topic, temp_cmd_sub_msg_id);
                    }
                }
            }
            
            // Запрос времени у сервера для синхронизации часов устройства
            // Это обеспечивает единую временную линию между устройствами и бэкендом
            esp_err_t time_req_err = node_utils_request_time();
            if (time_req_err == ESP_OK) {
                ESP_LOGD(TAG, "Requested time synchronization from server");
            } else {
                ESP_LOGW(
                    TAG,
                    "Time synchronization request skipped/failed: err=0x%x (%s)",
                    (unsigned)time_req_err,
                    esp_err_to_name(time_req_err)
                );
            }

            if (!s_is_connected) {
                ESP_LOGW(TAG, "MQTT disconnected before connection callback, skip connected callback");
                break;
            }

            // Вызов callback подключения
            if (s_connection_cb) {
                ESP_LOGD(TAG, "Calling registered connection callback (connected=true)");
                s_connection_cb(true, s_connection_user_ctx);
                ESP_LOGD(TAG, "Connection callback completed");
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
            ESP_LOGD(TAG, "MQTT subscribed, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_UNSUBSCRIBED:
            ESP_LOGD(TAG, "MQTT unsubscribed, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_PUBLISHED:
            ESP_LOGD(TAG, "MQTT published, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_DATA: {
            const size_t max_topic_len = sizeof(s_rx_topic_buf) - 1;
            const size_t max_data_len = sizeof(s_rx_payload_buf) - 1;
            int total_data_len = (event->total_data_len > 0) ? event->total_data_len : event->data_len;
            int current_offset = event->current_data_offset;

            if (event->data_len < 0 || total_data_len < 0 || current_offset < 0) {
                ESP_LOGW(
                    TAG,
                    "Invalid MQTT chunk lengths: data_len=%d total_data_len=%d offset=%d",
                    event->data_len,
                    total_data_len,
                    current_offset
                );
                mqtt_manager_reset_rx_assembly();
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }

            if ((size_t)total_data_len > max_data_len) {
                ESP_LOGW(TAG, "MQTT data too long: %d bytes (max %zu), dropping message",
                         total_data_len, max_data_len);
                mqtt_manager_reset_rx_assembly();
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }

            if (current_offset == 0) {
                if (s_rx_assembly_active && s_rx_received_len < s_rx_expected_len) {
                    ESP_LOGW(
                        TAG,
                        "Dropping incomplete MQTT assembly: topic='%s' received=%d expected=%d",
                        s_rx_topic_buf,
                        s_rx_received_len,
                        s_rx_expected_len
                    );
                }

                if (!event->topic || event->topic_len <= 0 || (size_t)event->topic_len > max_topic_len) {
                    ESP_LOGW(
                        TAG,
                        "Invalid MQTT topic for first chunk: topic_len=%d (max %zu)",
                        event->topic_len,
                        max_topic_len
                    );
                    mqtt_manager_reset_rx_assembly();
                    #if DIAGNOSTICS_AVAILABLE
                    if (diagnostics_is_initialized()) {
                        diagnostics_update_mqtt_metrics(false, true, false);
                    }
                    #endif
                    break;
                }

                memcpy(s_rx_topic_buf, event->topic, event->topic_len);
                s_rx_topic_buf[event->topic_len] = '\0';
                memset(s_rx_payload_buf, 0, sizeof(s_rx_payload_buf));
                s_rx_expected_len = total_data_len;
                s_rx_received_len = 0;
                s_rx_assembly_active = true;
            } else {
                if (!s_rx_assembly_active) {
                    ESP_LOGW(
                        TAG,
                        "MQTT chunk without active assembly: offset=%d data_len=%d",
                        current_offset,
                        event->data_len
                    );
                    break;
                }

                if (total_data_len != s_rx_expected_len) {
                    ESP_LOGW(
                        TAG,
                        "MQTT chunk total_len mismatch: chunk=%d expected=%d",
                        total_data_len,
                        s_rx_expected_len
                    );
                    mqtt_manager_reset_rx_assembly();
                    #if DIAGNOSTICS_AVAILABLE
                    if (diagnostics_is_initialized()) {
                        diagnostics_update_mqtt_metrics(false, true, false);
                    }
                    #endif
                    break;
                }

                if (current_offset != s_rx_received_len) {
                    ESP_LOGW(
                        TAG,
                        "MQTT chunk order mismatch: topic='%s' offset=%d expected_offset=%d chunk_len=%d",
                        s_rx_topic_buf,
                        current_offset,
                        s_rx_received_len,
                        event->data_len
                    );
                    mqtt_manager_reset_rx_assembly();
                    #if DIAGNOSTICS_AVAILABLE
                    if (diagnostics_is_initialized()) {
                        diagnostics_update_mqtt_metrics(false, true, false);
                    }
                    #endif
                    break;
                }

                if (event->topic && event->topic_len > 0) {
                    size_t current_topic_len = strlen(s_rx_topic_buf);
                    if ((size_t)event->topic_len > max_topic_len ||
                        current_topic_len != (size_t)event->topic_len ||
                        memcmp(s_rx_topic_buf, event->topic, event->topic_len) != 0) {
                        ESP_LOGW(TAG, "MQTT topic changed across chunks, dropping message");
                        mqtt_manager_reset_rx_assembly();
                        #if DIAGNOSTICS_AVAILABLE
                        if (diagnostics_is_initialized()) {
                            diagnostics_update_mqtt_metrics(false, true, false);
                        }
                        #endif
                        break;
                    }
                }
            }

            if (!event->data && event->data_len > 0) {
                ESP_LOGW(TAG, "MQTT chunk has NULL data pointer with len=%d", event->data_len);
                mqtt_manager_reset_rx_assembly();
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }

            if ((size_t)(current_offset + event->data_len) > max_data_len ||
                (current_offset + event->data_len) > s_rx_expected_len) {
                ESP_LOGW(
                    TAG,
                    "MQTT chunk out of bounds: offset=%d data_len=%d expected=%d max=%zu",
                    current_offset,
                    event->data_len,
                    s_rx_expected_len,
                    max_data_len
                );
                mqtt_manager_reset_rx_assembly();
                #if DIAGNOSTICS_AVAILABLE
                if (diagnostics_is_initialized()) {
                    diagnostics_update_mqtt_metrics(false, true, false);
                }
                #endif
                break;
            }

            if (event->data_len > 0 && event->data) {
                memcpy(s_rx_payload_buf + current_offset, event->data, event->data_len);
            }
            if ((current_offset + event->data_len) > s_rx_received_len) {
                s_rx_received_len = current_offset + event->data_len;
            }

            if (s_rx_received_len < s_rx_expected_len) {
                ESP_LOGD(
                    TAG,
                    "MQTT chunk buffered: topic='%s' offset=%d chunk_len=%d total=%d",
                    s_rx_topic_buf,
                    current_offset,
                    event->data_len,
                    s_rx_expected_len
                );
                break;
            }

            s_rx_payload_buf[s_rx_expected_len] = '\0';

            const char *topic = s_rx_topic_buf;
            const char *data = s_rx_payload_buf;
            int payload_len = s_rx_expected_len;

            const int log_data_max = 200;
            char log_data[log_data_max + 4];
            if (payload_len <= log_data_max) {
                memcpy(log_data, data, payload_len);
                log_data[payload_len] = '\0';
            } else {
                memcpy(log_data, data, log_data_max);
                log_data[log_data_max] = '\0';
                strcat(log_data, "...");
            }

            ESP_LOGD(TAG, "MQTT RECEIVE: topic='%s', len=%d, data=%s",
                     topic, payload_len, log_data);
            
            // Уведомляем OLED UI о MQTT активности (прием)
            // Используем слабые символы для опциональной зависимости от oled_ui
            // Если функция не определена, линкер разрешит слабый символ (NULL)
            if (oled_ui_notify_mqtt_rx) {
                oled_ui_notify_mqtt_rx();
            }
            
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
                ESP_LOGD(TAG, "Time response message received, len=%d", payload_len);
                
                // Парсим JSON для получения unix_ts
                cJSON *json = cJSON_ParseWithLength(data, payload_len);
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
	            } else if (mqtt_topic_has_suffix(topic, "config")) {
	                // Config топик - вызываем callback для обработки конфигурации
	                ESP_LOGI(TAG, "Config message received on topic: %s, len=%d", topic, payload_len);
	                if (s_config_cb) {
	                    ESP_LOGI(TAG, "Calling registered config callback");
	                    s_config_cb(topic, data, payload_len, s_config_user_ctx);
	                    ESP_LOGI(TAG, "Config callback completed");
	                } else {
	                    ESP_LOGW(TAG, "Config message received but no callback registered");
	                }
	            } else if (mqtt_topic_has_suffix(topic, "command")) {
	                // Command топик - извлекаем channel из топика
	                // Формат: hydro/{gh}/{zone}/{node}/{channel}/command
	                // Пример: hydro/gh-1/zn-3/nd-ph-1/pump_acid/command
	                // Нужно извлечь "pump_acid" из топика
	                char channel[64] = {0};
	                if (mqtt_extract_command_channel(topic, channel, sizeof(channel))) {
	                    // Логирование приема команды
	                    const int log_data_max = 200;
	                    char cmd_log_data[log_data_max + 4];
	                    if (payload_len <= log_data_max) {
	                        memcpy(cmd_log_data, data, payload_len);
	                        cmd_log_data[payload_len] = '\0';
	                    } else {
	                        memcpy(cmd_log_data, data, log_data_max);
	                        cmd_log_data[log_data_max] = '\0';
	                        strcat(cmd_log_data, "...");
	                    }
	                    ESP_LOGI(TAG, "MQTT COMMAND RECEIVED: topic='%s', channel='%s', len=%d, data=%s",
	                             topic, channel, payload_len, cmd_log_data);

	                    // Проверка: в setup режиме не обрабатываем команды
	                    #if SETUP_PORTAL_AVAILABLE
	                    if (setup_portal_is_running()) {
	                        ESP_LOGW(TAG, "Command ignored: device is in setup mode");
	                    } else
	                    #endif
	                    {
	                        if (s_command_cb) {
	                            s_command_cb(topic, channel, data, payload_len, s_command_user_ctx);
	                        } else {
	                            ESP_LOGW(TAG, "Command message received but no callback registered");
	                        }
	                    }
	                } else {
	                    ESP_LOGE(TAG, "Invalid command topic format: %s", topic);
	                }
	            } else {
	                ESP_LOGD(TAG, "Unknown topic type: %s", topic);
	            }

            mqtt_manager_reset_rx_assembly();
            break;
        }

        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT error");
            if (event->error_handle) {
                const esp_mqtt_error_codes_t *error_handle = event->error_handle;
                ESP_LOGE(TAG, "Error type: %d", error_handle->error_type);
                mqtt_manager_log_error_details(error_handle);
                esp_mqtt_error_type_t err_type = error_handle->error_type;
                if (err_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
                    ESP_LOGE(TAG, "TCP transport error");
                    // Для TCP ошибок считаем соединение потерянным и ждём reconnect
                    // от ESP-IDF MQTT клиента.
                    s_is_connected = false;
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
