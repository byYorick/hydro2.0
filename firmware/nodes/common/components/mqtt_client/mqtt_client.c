/**
 * @file mqtt_client.c
 * @brief Реализация MQTT клиента для ESP32-нод
 * 
 * Компонент реализует полный MQTT протокол согласно:
 * - doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 * 
 * Стандарты кодирования:
 * - Именование функций: mqtt_client_* (префикс компонента)
 * - Обработка ошибок: все функции возвращают esp_err_t, логируют ошибки
 * - Логирование: ESP_LOGE для ошибок, ESP_LOGI для ключевых событий
 */

#include "mqtt_client.h"
#include "esp_log.h"
#include "esp_mqtt.h"
#include "esp_timer.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "mqtt_client";

// Внутренние структуры
static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static mqtt_client_config_t s_config = {0};
static mqtt_node_info_t s_node_info = {0};
static bool s_is_connected = false;
static char s_mqtt_uri[256] = {0};

// Callbacks
static mqtt_config_callback_t s_config_cb = NULL;
static mqtt_command_callback_t s_command_cb = NULL;
static mqtt_connection_callback_t s_connection_cb = NULL;
static void *s_config_user_ctx = NULL;
static void *s_command_user_ctx = NULL;
static void *s_connection_user_ctx = NULL;

// Forward declarations
static void mqtt_event_handler(void *handler_args, esp_event_base_t base, 
                               int32_t event_id, void *event_data);
static esp_err_t mqtt_client_publish_internal(const char *topic, const char *data, int qos, int retain);

/**
 * @brief Построение MQTT топика
 */
static esp_err_t build_topic(char *topic_buf, size_t buf_size, const char *type, const char *channel) {
    if (!topic_buf || buf_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    int len;
    if (channel && channel[0] != '\0') {
        // Топик с каналом: hydro/{gh}/{zone}/{node}/{channel}/{type}
        len = snprintf(topic_buf, buf_size, "hydro/%s/%s/%s/%s/%s",
                      s_node_info.gh_uid ? s_node_info.gh_uid : "",
                      s_node_info.zone_uid ? s_node_info.zone_uid : "",
                      s_node_info.node_uid ? s_node_info.node_uid : "",
                      channel, type);
    } else {
        // Топик без канала: hydro/{gh}/{zone}/{node}/{type}
        len = snprintf(topic_buf, buf_size, "hydro/%s/%s/%s/%s",
                      s_node_info.gh_uid ? s_node_info.gh_uid : "",
                      s_node_info.zone_uid ? s_node_info.zone_uid : "",
                      s_node_info.node_uid ? s_node_info.node_uid : "",
                      type);
    }

    if (len < 0 || (size_t)len >= buf_size) {
        ESP_LOGE(TAG, "Topic buffer too small: need %d, have %zu", len, buf_size);
        return ESP_ERR_INVALID_SIZE;
    }

    return ESP_OK;
}

esp_err_t mqtt_client_init(const mqtt_client_config_t *config, const mqtt_node_info_t *node_info) {
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

    ESP_LOGI(TAG, "Initializing MQTT client...");
    ESP_LOGI(TAG, "Broker: %s:%u", config->host, config->port);
    ESP_LOGI(TAG, "Node: %s/%s/%s", 
             node_info->gh_uid ? node_info->gh_uid : "?",
             node_info->zone_uid ? node_info->zone_uid : "?",
             node_info->node_uid);

    // Сохраняем конфигурацию (сначала node_info, чтобы build_topic работал)
    memcpy(&s_node_info, node_info, sizeof(mqtt_node_info_t));
    memcpy(&s_config, config, sizeof(mqtt_client_config_t));

    // Формируем URI
    const char *protocol = config->use_tls ? "mqtts://" : "mqtt://";
    int uri_len = snprintf(s_mqtt_uri, sizeof(s_mqtt_uri), "%s%s:%u", 
                          protocol, config->host, config->port);
    if (uri_len < 0 || uri_len >= sizeof(s_mqtt_uri)) {
        ESP_LOGE(TAG, "MQTT URI is too long");
        return ESP_ERR_INVALID_SIZE;
    }

    // Определяем client_id
    const char *client_id = config->client_id;
    if (!client_id || client_id[0] == '\0') {
        client_id = node_info->node_uid;
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
        .session.keepalive = config->keepalive > 0 ? config->keepalive : 30,
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
    if (config->username && config->username[0] != '\0') {
        mqtt_cfg.credentials.username = config->username;
        if (config->password && config->password[0] != '\0') {
            mqtt_cfg.credentials.authentication.password = config->password;
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

    ESP_LOGI(TAG, "MQTT client initialized successfully");
    return ESP_OK;
}

esp_err_t mqtt_client_start(void) {
    if (!s_mqtt_client) {
        ESP_LOGE(TAG, "MQTT client not initialized");
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Starting MQTT client...");
    esp_err_t err = esp_mqtt_client_start(s_mqtt_client);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start MQTT client: %s", esp_err_to_name(err));
        return err;
    }

    return ESP_OK;
}

esp_err_t mqtt_client_stop(void) {
    if (!s_mqtt_client) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Stopping MQTT client...");
    return esp_mqtt_client_stop(s_mqtt_client);
}

esp_err_t mqtt_client_deinit(void) {
    if (s_mqtt_client) {
        esp_mqtt_client_stop(s_mqtt_client);
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
    }

    memset(&s_config, 0, sizeof(s_config));
    memset(&s_node_info, 0, sizeof(s_node_info));
    s_is_connected = false;

    ESP_LOGI(TAG, "MQTT client deinitialized");
    return ESP_OK;
}

void mqtt_client_register_config_cb(mqtt_config_callback_t cb, void *user_ctx) {
    s_config_cb = cb;
    s_config_user_ctx = user_ctx;
}

void mqtt_client_register_command_cb(mqtt_command_callback_t cb, void *user_ctx) {
    s_command_cb = cb;
    s_command_user_ctx = user_ctx;
}

void mqtt_client_register_connection_cb(mqtt_connection_callback_t cb, void *user_ctx) {
    s_connection_cb = cb;
    s_connection_user_ctx = user_ctx;
}

esp_err_t mqtt_client_publish_telemetry(const char *channel, const char *data) {
    if (!channel || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "telemetry", channel);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_client_publish_internal(topic, data, 1, 0);
}

esp_err_t mqtt_client_publish_status(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "status", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_client_publish_internal(topic, data, 1, 1);
}

esp_err_t mqtt_client_publish_heartbeat(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "heartbeat", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_client_publish_internal(topic, data, 0, 0);
}

esp_err_t mqtt_client_publish_command_response(const char *channel, const char *data) {
    if (!channel || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "command_response", channel);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_client_publish_internal(topic, data, 1, 0);
}

esp_err_t mqtt_client_publish_config_response(const char *data) {
    if (!data) {
        return ESP_ERR_INVALID_ARG;
    }

    char topic[192];
    esp_err_t err = build_topic(topic, sizeof(topic), "config_response", NULL);
    if (err != ESP_OK) {
        return err;
    }

    return mqtt_client_publish_internal(topic, data, 1, 0);
}

bool mqtt_client_is_connected(void) {
    return s_is_connected;
}

esp_err_t mqtt_client_reconnect(void) {
    if (!s_mqtt_client) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(TAG, "Reconnecting to MQTT broker...");
    return esp_mqtt_client_reconnect(s_mqtt_client);
}

/**
 * @brief Внутренняя функция публикации
 */
static esp_err_t mqtt_client_publish_internal(const char *topic, const char *data, int qos, int retain) {
    if (!s_mqtt_client || !topic || !data) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_is_connected) {
        ESP_LOGW(TAG, "MQTT not connected, cannot publish to %s", topic);
        return ESP_ERR_INVALID_STATE;
    }

    int data_len = strlen(data);
    int msg_id = esp_mqtt_client_publish(s_mqtt_client, topic, data, data_len, qos, retain);
    
    if (msg_id < 0) {
        ESP_LOGE(TAG, "Failed to publish to %s", topic);
        return ESP_FAIL;
    }

    ESP_LOGD(TAG, "Published to %s (msg_id=%d, len=%d, qos=%d, retain=%d)", 
             topic, msg_id, data_len, qos, retain);
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
            s_is_connected = true;

            // Подписка на config топик
            char config_topic[192];
            if (build_topic(config_topic, sizeof(config_topic), "config", NULL) == ESP_OK) {
                esp_mqtt_client_subscribe(s_mqtt_client, config_topic, 1);
                ESP_LOGI(TAG, "Subscribed to %s", config_topic);
            }

            // Подписка на command топики (wildcard для всех каналов)
            char command_topic[192];
            snprintf(command_topic, sizeof(command_topic), "hydro/%s/%s/%s/+/command",
                    s_node_info.gh_uid ? s_node_info.gh_uid : "",
                    s_node_info.zone_uid ? s_node_info.zone_uid : "",
                    s_node_info.node_uid ? s_node_info.node_uid : "");
            esp_mqtt_client_subscribe(s_mqtt_client, command_topic, 1);
            ESP_LOGI(TAG, "Subscribed to %s", command_topic);

            // Публикация статуса ONLINE
            char status_json[128];
            snprintf(status_json, sizeof(status_json), "{\"status\":\"ONLINE\",\"ts\":%lld}", 
                    (long long)(esp_timer_get_time() / 1000000));
            mqtt_client_publish_status(status_json);

            // Вызов callback подключения
            if (s_connection_cb) {
                s_connection_cb(true, s_connection_user_ctx);
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
            ESP_LOGI(TAG, "MQTT data received on topic: %.*s", event->topic_len, event->topic);
            
            // Создание null-terminated строк для topic и data
            char topic[128] = {0};
            char data[2048] = {0};

            int topic_len = (event->topic_len < sizeof(topic) - 1) ? 
                           event->topic_len : sizeof(topic) - 1;
            int data_len = (event->data_len < sizeof(data) - 1) ? 
                          event->data_len : sizeof(data) - 1;

            memcpy(topic, event->topic, topic_len);
            memcpy(data, event->data, data_len);

            // Определяем тип топика и вызываем соответствующий callback
            // Согласно MQTT_SPEC_FULL.md раздел 2:
            // - Config: hydro/{gh}/{zone}/{node}/config
            // - Command: hydro/{gh}/{zone}/{node}/{channel}/command
            if (strstr(topic, "/config") != NULL) {
                // Config топик - вызываем callback для обработки конфигурации
                if (s_config_cb) {
                    s_config_cb(topic, data, data_len, s_config_user_ctx);
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
                            if (s_command_cb) {
                                s_command_cb(topic, channel, data, data_len, s_command_user_ctx);
                            } else {
                                ESP_LOGW(TAG, "Command message received but no callback registered");
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
                if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
                    ESP_LOGE(TAG, "TCP transport error");
                } else if (event->error_handle->error_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED) {
                    ESP_LOGE(TAG, "Connection refused");
                }
            }
            break;

        default:
            ESP_LOGD(TAG, "MQTT event: %d", event_id);
            break;
    }
}

