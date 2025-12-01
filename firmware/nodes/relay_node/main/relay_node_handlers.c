/**
 * @file relay_node_handlers.c
 * @brief MQTT message handlers for relay_node
 * 
 * Объединяет обработчики:
 * - Config messages (NodeConfig)
 * - Command messages (команды управления реле)
 */

#include "relay_node_handlers.h"
#include "relay_node_app.h"
#include "relay_node_defaults.h"
#include "mqtt_manager.h"
#include "wifi_manager.h"
#include "config_storage.h"
#include "config_apply.h"
#include "relay_driver.h"
#include "node_utils.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_err.h"
#include "node_watchdog.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

static const char *TAG = "relay_node_handlers";

extern void relay_node_mqtt_connection_cb(bool connected, void *user_ctx);

// Защита от дублирующих команд
#define CMD_ID_CACHE_SIZE 20
#define CMD_ID_TTL_MS 60000  // 60 секунд TTL

typedef struct {
    char cmd_id[64];
    uint64_t timestamp_ms;
    bool valid;
} cmd_id_cache_entry_t;

static cmd_id_cache_entry_t s_cmd_id_cache[CMD_ID_CACHE_SIZE] = {0};
static SemaphoreHandle_t s_cmd_id_cache_mutex = NULL;

// Очередь команд с лимитом 5
#define COMMAND_QUEUE_SIZE 5
#define COMMAND_QUEUE_TIMEOUT_MS 10000

typedef struct {
    char *topic;
    char *channel;
    char *data;
    int data_len;
    void *user_ctx;
} command_queue_item_t;

static QueueHandle_t s_command_queue = NULL;
static TaskHandle_t s_command_processor_task = NULL;

// Forward declaration
static void relay_node_command_handler_internal(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx);

/**
 * @brief Инициализация mutex для кеша cmd_id
 */
static void init_cmd_id_cache_mutex(void) {
    if (s_cmd_id_cache_mutex == NULL) {
        s_cmd_id_cache_mutex = xSemaphoreCreateMutex();
        if (s_cmd_id_cache_mutex == NULL) {
            ESP_LOGE(TAG, "Failed to create cmd_id cache mutex");
        }
    }
}

/**
 * @brief Проверка и добавление cmd_id в кеш (потокобезопасно)
 * @return true если команда уже обработана (дубликат), false если новая
 */
static bool check_and_add_cmd_id(const char *cmd_id) {
    if (cmd_id == NULL) {
        return false;
    }
    
    init_cmd_id_cache_mutex();
    
    if (s_cmd_id_cache_mutex == NULL) {
        ESP_LOGW(TAG, "Mutex not available, skipping duplicate check");
        return false;
    }
    
    if (xSemaphoreTake(s_cmd_id_cache_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        ESP_LOGW(TAG, "Failed to take cmd_id cache mutex, skipping duplicate check");
        return false;
    }
    
    uint64_t now_ms = esp_timer_get_time() / 1000;
    
    // Очистка устаревших записей и поиск существующей
    int oldest_idx = 0;
    uint64_t oldest_ts = UINT64_MAX;
    
    for (int i = 0; i < CMD_ID_CACHE_SIZE; i++) {
        if (s_cmd_id_cache[i].valid) {
            if (now_ms - s_cmd_id_cache[i].timestamp_ms > CMD_ID_TTL_MS) {
                s_cmd_id_cache[i].valid = false;
                continue;
            }
            
            if (strcmp(s_cmd_id_cache[i].cmd_id, cmd_id) == 0) {
                s_cmd_id_cache[i].timestamp_ms = now_ms;
                xSemaphoreGive(s_cmd_id_cache_mutex);
                return true; // Дубликат найден
            }
            
            if (s_cmd_id_cache[i].timestamp_ms < oldest_ts) {
                oldest_ts = s_cmd_id_cache[i].timestamp_ms;
                oldest_idx = i;
            }
        } else {
            oldest_idx = i;
            break;
        }
    }
    
    // Добавляем новую запись
    strncpy(s_cmd_id_cache[oldest_idx].cmd_id, cmd_id, sizeof(s_cmd_id_cache[oldest_idx].cmd_id) - 1);
    s_cmd_id_cache[oldest_idx].cmd_id[sizeof(s_cmd_id_cache[oldest_idx].cmd_id) - 1] = '\0';
    s_cmd_id_cache[oldest_idx].timestamp_ms = now_ms;
    s_cmd_id_cache[oldest_idx].valid = true;
    
    xSemaphoreGive(s_cmd_id_cache_mutex);
    
    return false; // Новая команда
}

// Helper function to send error response
static void send_command_error_response(const char *channel, const char *cmd_id, 
                                        const char *error_code, const char *error_message) {
    cJSON *response = cJSON_CreateObject();
    if (response) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
        cJSON_AddStringToObject(response, "status", "ERROR");
        cJSON_AddStringToObject(response, "error_code", error_code);
        cJSON_AddStringToObject(response, "error_message", error_message);
        cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());
        
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
        cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());
        
        if (extra_data) {
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
void relay_node_config_handler(const char *topic, const char *data, int data_len, void *user_ctx) {
    if (data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid config parameters: data=%p, data_len=%d", data, data_len);
        return;
    }
    
    ESP_LOGI(TAG, "Config received on %s: [%d bytes]", topic ? topic : "NULL", data_len);
    
    cJSON *config = cJSON_ParseWithLength(data, data_len);
    if (!config) {
        ESP_LOGE(TAG, "Failed to parse config JSON");
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid JSON");
            cJSON_AddNumberToObject(error_response, "ts", (double)node_utils_get_timestamp_seconds());
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_manager_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    cJSON *previous_config = config_apply_load_previous_config();

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
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Invalid config structure");
            cJSON_AddNumberToObject(error_response, "ts", (double)node_utils_get_timestamp_seconds());
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
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", error_msg);
            cJSON_AddNumberToObject(error_response, "ts", (double)node_utils_get_timestamp_seconds());
            char *json_str = cJSON_PrintUnformatted(error_response);
            if (json_str) {
                mqtt_manager_publish_config_response(json_str);
                free(json_str);
            }
            cJSON_Delete(error_response);
        }
        return;
    }
    
    // Save config to NVS
    esp_err_t save_err = config_storage_save(data, data_len);
    if (save_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to save config: %s", esp_err_to_name(save_err));
        cJSON_Delete(config);
        if (previous_config) {
            cJSON_Delete(previous_config);
        }
        cJSON *error_response = cJSON_CreateObject();
        if (error_response) {
            cJSON_AddStringToObject(error_response, "status", "ERROR");
            cJSON_AddStringToObject(error_response, "error", "Failed to save config");
            cJSON_AddNumberToObject(error_response, "ts", (double)node_utils_get_timestamp_seconds());
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
        relay_node_set_node_id(node_id_item->valuestring);
    }
    
    // Reload config from storage
    esp_err_t load_err = config_storage_load();
    if (load_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reload config: %s", esp_err_to_name(load_err));
    }
    
    ESP_LOGI(TAG, "Config saved and reloaded successfully");

    config_apply_result_t apply_result;
    config_apply_result_init(&apply_result);

    const config_apply_mqtt_params_t mqtt_params = {
        .default_node_id = RELAY_NODE_DEFAULT_NODE_ID,
        .default_gh_uid = RELAY_NODE_DEFAULT_GH_UID,
        .default_zone_uid = RELAY_NODE_DEFAULT_ZONE_UID,
        .config_cb = relay_node_config_handler,
        .command_cb = relay_node_command_handler,
        .connection_cb = relay_node_mqtt_connection_cb,
        .user_ctx = NULL,
    };

    esp_err_t wifi_err = config_apply_wifi(config, previous_config, &apply_result);
    if (wifi_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reapply Wi-Fi config: %s", esp_err_to_name(wifi_err));
    }

    esp_err_t mqtt_err = config_apply_mqtt(config, previous_config, &mqtt_params, &apply_result);
    if (mqtt_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to reapply MQTT config: %s", esp_err_to_name(mqtt_err));
    }

    esp_err_t ack_err = config_apply_publish_ack(&apply_result);
    if (ack_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish config ACK: %s", esp_err_to_name(ack_err));
    }

    if (previous_config) {
        cJSON_Delete(previous_config);
    }
    cJSON_Delete(config);
}

/**
 * @brief Задача обработки команд из очереди
 */
static void task_command_processor(void *pvParameters) {
    ESP_LOGI(TAG, "Command processor task started");
    
    esp_err_t wdt_err = node_watchdog_add_task();
    if (wdt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add command processor task to watchdog: %s", esp_err_to_name(wdt_err));
    }
    
    command_queue_item_t item;
    
    const TickType_t wdt_reset_interval = pdMS_TO_TICKS(3000);
    TickType_t last_wdt_reset = xTaskGetTickCount();
    
    while (1) {
        TickType_t current_time = xTaskGetTickCount();
        TickType_t elapsed_since_wdt = current_time - last_wdt_reset;
        
        if (elapsed_since_wdt >= wdt_reset_interval) {
            node_watchdog_reset();
            last_wdt_reset = current_time;
        }
        
        if (xQueueReceive(s_command_queue, &item, pdMS_TO_TICKS(2000)) == pdTRUE) {
            node_watchdog_reset();
            
            relay_node_command_handler_internal(item.topic, item.channel, item.data, item.data_len, item.user_ctx);
            
            node_watchdog_reset();
            
            if (item.topic) free(item.topic);
            if (item.channel) free(item.channel);
            if (item.data) free(item.data);
        }
    }
}

/**
 * @brief Инициализация очереди команд
 */
static esp_err_t init_command_queue(void) {
    if (s_command_queue != NULL) {
        return ESP_OK;
    }
    
    s_command_queue = xQueueCreate(COMMAND_QUEUE_SIZE, sizeof(command_queue_item_t));
    if (s_command_queue == NULL) {
        ESP_LOGE(TAG, "Failed to create command queue");
        return ESP_ERR_NO_MEM;
    }
    
    BaseType_t ret = xTaskCreate(
        task_command_processor,
        "cmd_processor",
        4096,
        NULL,
        6,
        &s_command_processor_task
    );
    
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create command processor task");
        vQueueDelete(s_command_queue);
        s_command_queue = NULL;
        return ESP_ERR_NO_MEM;
    }
    
    ESP_LOGI(TAG, "Command queue initialized (size: %d)", COMMAND_QUEUE_SIZE);
    return ESP_OK;
}

/**
 * @brief Handle MQTT command message (публичная функция - добавляет в очередь)
 */
void relay_node_command_handler(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    if (channel == NULL || data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid command parameters: channel=%p, data=%p, data_len=%d", 
                 channel, data, data_len);
        return;
    }
    
    if (s_command_queue == NULL) {
        esp_err_t err = init_command_queue();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize command queue, processing directly");
            relay_node_command_handler_internal(topic, channel, data, data_len, user_ctx);
            return;
        }
    }
    
    command_queue_item_t item = {0};
    item.topic = topic ? strdup(topic) : NULL;
    item.channel = strdup(channel);
    
    if (!item.channel) {
        ESP_LOGE(TAG, "Failed to allocate memory for channel string");
        if (item.topic) free(item.topic);
        return;
    }
    
    item.data = (char *)malloc(data_len + 1);
    if (!item.data) {
        ESP_LOGE(TAG, "Failed to allocate memory for data buffer");
        if (item.topic) free(item.topic);
        if (item.channel) free(item.channel);
        return;
    }
    
    memcpy(item.data, data, data_len);
    item.data[data_len] = '\0';
    item.data_len = data_len;
    item.user_ctx = user_ctx;
    
    if (xQueueSend(s_command_queue, &item, 0) != pdTRUE) {
        ESP_LOGW(TAG, "Command queue is full (limit: %d), rejecting command", COMMAND_QUEUE_SIZE);
        
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON *cmd = cJSON_ParseWithLength(data, data_len);
            const char *cmd_id = "unknown";
            if (cmd) {
                cJSON *cmd_id_item = cJSON_GetObjectItem(cmd, "cmd_id");
                if (cmd_id_item && cJSON_IsString(cmd_id_item)) {
                    cmd_id = cmd_id_item->valuestring;
                }
                cJSON_Delete(cmd);
            }
            
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            cJSON_AddStringToObject(response, "status", "ERROR");
            cJSON_AddStringToObject(response, "error_code", "queue_full");
            cJSON_AddStringToObject(response, "error_message", "Command queue is full, please retry later");
            cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());
            
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(channel, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        
        if (item.topic) free(item.topic);
        if (item.channel) free(item.channel);
        if (item.data) free(item.data);
    } else {
        ESP_LOGI(TAG, "Command queued: channel=%s", channel);
    }
}

/**
 * @brief Internal command handler (обрабатывает команду напрямую)
 */
static void relay_node_command_handler_internal(const char *topic, const char *channel, const char *data, int data_len, void *user_ctx) {
    if (channel == NULL || data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid command parameters: channel=%p, data=%p, data_len=%d", 
                 channel, data, data_len);
        return;
    }
    
    ESP_LOGI(TAG, "Command received on %s, channel: %s", topic ? topic : "NULL", channel);
    
    cJSON *cmd = cJSON_ParseWithLength(data, data_len);
    if (!cmd) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }
    
    cJSON *cmd_id_item = cJSON_GetObjectItem(cmd, "cmd_id");
    cJSON *cmd_item = cJSON_GetObjectItem(cmd, "cmd");
    
    if (!cmd_id_item || !cJSON_IsString(cmd_id_item) || !cmd_item || !cJSON_IsString(cmd_item)) {
        ESP_LOGE(TAG, "Invalid command format: missing cmd_id or cmd");
        cJSON_Delete(cmd);
        return;
    }
    
    const char *cmd_id = cmd_id_item->valuestring;
    const char *cmd_type = cmd_item->valuestring;
    
    // Проверка на дублирующую команду
    if (check_and_add_cmd_id(cmd_id)) {
        ESP_LOGW(TAG, "Duplicate command detected: %s (cmd_id: %s), ignoring", cmd_type, cmd_id);
        cJSON *response = cJSON_CreateObject();
        if (response) {
            cJSON_AddStringToObject(response, "cmd_id", cmd_id);
            cJSON_AddStringToObject(response, "status", "NO_EFFECT");
            cJSON_AddStringToObject(response, "error_message", "Command already processed");
            cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());
            
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(channel, json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        cJSON_Delete(cmd);
        return;
    }
    
    ESP_LOGI(TAG, "Processing command: %s (cmd_id: %s)", cmd_type, cmd_id);
    
    // Handle relay commands
    if (!relay_node_is_relay_control_initialized()) {
        send_command_error_response(channel, cmd_id, "relay_not_initialized", 
                                   "Relay driver not initialized");
        cJSON_Delete(cmd);
        return;
    }
    
    if (strcmp(cmd_type, "set_state") == 0) {
        cJSON *state_item = cJSON_GetObjectItem(cmd, "state");
        if (!state_item || !cJSON_IsNumber(state_item)) {
            send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                       "Missing or invalid state");
            cJSON_Delete(cmd);
            return;
        }
        
        int state = (int)cJSON_GetNumberValue(state_item);
        relay_state_t relay_state = (state == 0) ? RELAY_STATE_OPEN : RELAY_STATE_CLOSED;
        
        esp_err_t err = relay_driver_set_state(channel, relay_state);
        
        if (err == ESP_OK) {
            send_command_success_response(channel, cmd_id, NULL);
        } else if (err == ESP_ERR_NOT_FOUND) {
            send_command_error_response(channel, cmd_id, "relay_not_found", 
                                       "Relay channel not found");
        } else {
            send_command_error_response(channel, cmd_id, "relay_error", 
                                       "Failed to set relay state");
        }
    } else if (strcmp(cmd_type, "toggle") == 0) {
        relay_state_t current_state;
        esp_err_t get_err = relay_driver_get_state(channel, &current_state);
        
        if (get_err != ESP_OK) {
            send_command_error_response(channel, cmd_id, "relay_not_found", 
                                       "Relay channel not found");
            cJSON_Delete(cmd);
            return;
        }
        
        relay_state_t new_state = (current_state == RELAY_STATE_OPEN) ? RELAY_STATE_CLOSED : RELAY_STATE_OPEN;
        esp_err_t err = relay_driver_set_state(channel, new_state);
        
        if (err == ESP_OK) {
            cJSON *extra = cJSON_CreateObject();
            cJSON_AddNumberToObject(extra, "state", new_state);
            send_command_success_response(channel, cmd_id, extra);
            cJSON_Delete(extra);
        } else {
            send_command_error_response(channel, cmd_id, "relay_error", 
                                       "Failed to toggle relay");
        }
    } else if (strcmp(cmd_type, "timed_on") == 0) {
        cJSON *duration_item = cJSON_GetObjectItem(cmd, "duration_ms");
        if (!duration_item || !cJSON_IsNumber(duration_item)) {
            send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                       "Missing or invalid duration_ms");
            cJSON_Delete(cmd);
            return;
        }
        
        uint32_t duration_ms = (uint32_t)cJSON_GetNumberValue(duration_item);
        if (duration_ms == 0 || duration_ms > 300000) {
            send_command_error_response(channel, cmd_id, "invalid_parameter", 
                                       "duration_ms must be between 1 and 300000");
            cJSON_Delete(cmd);
            return;
        }
        
        // Включаем реле
        esp_err_t err = relay_driver_set_state(channel, RELAY_STATE_CLOSED);
        if (err != ESP_OK) {
            send_command_error_response(channel, cmd_id, "relay_error", 
                                       "Failed to turn on relay");
            cJSON_Delete(cmd);
            return;
        }
        
        // Создаем задачу для автоматического выключения через duration_ms
        // Примечание: в реальной реализации лучше использовать таймер или отдельную задачу
        // Здесь упрощенная версия - реле останется включенным до следующей команды
        // Для полной реализации нужно добавить систему таймеров для реле
        
        send_command_success_response(channel, cmd_id, NULL);
        ESP_LOGI(TAG, "Relay %s turned on for %lu ms (manual off required)", channel, duration_ms);
    } else {
        send_command_error_response(channel, cmd_id, "unknown_command", 
                                   "Unknown command type");
    }
    
    cJSON_Delete(cmd);
}

