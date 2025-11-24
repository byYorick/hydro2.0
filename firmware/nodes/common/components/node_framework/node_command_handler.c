/**
 * @file node_command_handler.c
 * @brief Реализация обработчика команд
 */

#include "node_command_handler.h"
#include "node_framework.h"
#include "mqtt_manager.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdlib.h>

static const char *TAG = "node_command_handler";

// Структура зарегистрированного обработчика
typedef struct {
    char cmd_name[NODE_COMMAND_NAME_MAX_LEN];
    node_command_handler_func_t handler;
    void *user_ctx;
    bool used;
} command_handler_entry_t;

// Кеш для защиты от дубликатов команд
#define CMD_ID_CACHE_SIZE 20
#define CMD_ID_TTL_MS 60000  // 60 секунд TTL

typedef struct {
    char cmd_id[64];
    uint64_t timestamp_ms;
    bool valid;
} cmd_id_cache_entry_t;

static struct {
    command_handler_entry_t handlers[NODE_COMMAND_HANDLER_MAX];
    size_t handler_count;
    SemaphoreHandle_t mutex;
    
    cmd_id_cache_entry_t cmd_id_cache[CMD_ID_CACHE_SIZE];
    SemaphoreHandle_t cache_mutex;
} s_command_handler = {0};

static void init_mutexes(void) {
    if (s_command_handler.mutex == NULL) {
        s_command_handler.mutex = xSemaphoreCreateMutex();
    }
    if (s_command_handler.cache_mutex == NULL) {
        s_command_handler.cache_mutex = xSemaphoreCreateMutex();
    }
}

esp_err_t node_command_handler_register(
    const char *cmd_name,
    node_command_handler_func_t handler,
    void *user_ctx
) {
    if (cmd_name == NULL || handler == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    init_mutexes();

    if (s_command_handler.mutex == NULL) {
        return ESP_ERR_NO_MEM;
    }

    if (xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Проверяем, не зарегистрирована ли уже команда
        for (size_t i = 0; i < s_command_handler.handler_count; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd_name) == 0) {
                xSemaphoreGive(s_command_handler.mutex);
                ESP_LOGW(TAG, "Command %s already registered", cmd_name);
                return ESP_ERR_INVALID_STATE;
            }
        }

        // Ищем свободный слот
        if (s_command_handler.handler_count >= NODE_COMMAND_HANDLER_MAX) {
            xSemaphoreGive(s_command_handler.mutex);
            ESP_LOGE(TAG, "Command handler registry is full");
            return ESP_ERR_NO_MEM;
        }

        // Регистрируем обработчик
        size_t idx = s_command_handler.handler_count;
        strncpy(s_command_handler.handlers[idx].cmd_name, cmd_name, NODE_COMMAND_NAME_MAX_LEN - 1);
        s_command_handler.handlers[idx].cmd_name[NODE_COMMAND_NAME_MAX_LEN - 1] = '\0';
        s_command_handler.handlers[idx].handler = handler;
        s_command_handler.handlers[idx].user_ctx = user_ctx;
        s_command_handler.handlers[idx].used = true;
        s_command_handler.handler_count++;

        xSemaphoreGive(s_command_handler.mutex);
        ESP_LOGI(TAG, "Command handler registered: %s", cmd_name);
        return ESP_OK;
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t node_command_handler_unregister(const char *cmd_name) {
    if (cmd_name == NULL || s_command_handler.mutex == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        for (size_t i = 0; i < s_command_handler.handler_count; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd_name) == 0) {
                s_command_handler.handlers[i].used = false;
                memset(&s_command_handler.handlers[i], 0, sizeof(command_handler_entry_t));
                s_command_handler.handler_count--;
                xSemaphoreGive(s_command_handler.mutex);
                ESP_LOGI(TAG, "Command handler unregistered: %s", cmd_name);
                return ESP_OK;
            }
        }
        xSemaphoreGive(s_command_handler.mutex);
    }

    return ESP_ERR_NOT_FOUND;
}

void node_command_handler_process(
    const char *topic,
    const char *channel,
    const char *data,
    int data_len,
    void *user_ctx
) {
    (void)topic;
    (void)user_ctx;
    
    if (data == NULL || data_len <= 0) {
        ESP_LOGE(TAG, "Invalid command parameters");
        return;
    }

    // Парсинг JSON команды
    cJSON *json = cJSON_ParseWithLength(data, data_len);
    if (!json) {
        ESP_LOGE(TAG, "Failed to parse command JSON");
        return;
    }

    // Извлечение cmd и cmd_id
    cJSON *cmd_item = cJSON_GetObjectItem(json, "cmd");
    cJSON *cmd_id_item = cJSON_GetObjectItem(json, "cmd_id");

    if (!cJSON_IsString(cmd_item) || !cJSON_IsString(cmd_id_item)) {
        ESP_LOGE(TAG, "Invalid command format: missing cmd or cmd_id");
        cJSON_Delete(json);
        return;
    }

    const char *cmd = cmd_item->valuestring;
    const char *cmd_id = cmd_id_item->valuestring;

    // Проверка на дубликат
    if (node_command_handler_is_duplicate(cmd_id)) {
        ESP_LOGW(TAG, "Duplicate command ignored: %s (id: %s)", cmd, cmd_id);
        cJSON_Delete(json);
        return;
    }

    ESP_LOGI(TAG, "Processing command: %s (id: %s) on channel: %s", cmd, cmd_id, channel ? channel : "default");

    // Проверка safe_mode: блокируем все команды кроме exit_safe_mode
    if (node_framework_is_safe_mode() && strcmp(cmd, "exit_safe_mode") != 0) {
        ESP_LOGW(TAG, "Command %s rejected: node is in safe_mode", cmd);
        cJSON *response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "safe_mode_active",
            "Node is in safe mode. Use 'exit_safe_mode' command to exit.",
            NULL
        );
        if (response) {
            char *json_str = cJSON_PrintUnformatted(response);
            if (json_str) {
                mqtt_manager_publish_command_response(channel ? channel : "default", json_str);
                free(json_str);
            }
            cJSON_Delete(response);
        }
        cJSON_Delete(json);
        return;
    }

    // Поиск обработчика
    init_mutexes();
    node_command_handler_func_t handler = NULL;
    void *handler_ctx = NULL;

    if (s_command_handler.mutex &&
        xSemaphoreTake(s_command_handler.mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        for (size_t i = 0; i < s_command_handler.handler_count; i++) {
            if (s_command_handler.handlers[i].used &&
                strcmp(s_command_handler.handlers[i].cmd_name, cmd) == 0) {
                handler = s_command_handler.handlers[i].handler;
                handler_ctx = s_command_handler.handlers[i].user_ctx;
                break;
            }
        }
        xSemaphoreGive(s_command_handler.mutex);
    }

    // Обработка команды
    cJSON *response = NULL;
    esp_err_t err = ESP_ERR_NOT_FOUND;

    if (handler) {
        // Извлекаем параметры команды (все поля кроме cmd и cmd_id)
        cJSON *params = cJSON_Duplicate(json, 1);
        if (params) {
            cJSON_DeleteItemFromObject(params, "cmd");
            cJSON_DeleteItemFromObject(params, "cmd_id");
            
            err = handler(channel, params, &response, handler_ctx);
            
            // Если обработчик не создал ответ, создаем его здесь
            if (err == ESP_OK && response == NULL) {
                response = node_command_handler_create_response(
                    cmd_id,
                    "ACK",
                    NULL,
                    NULL,
                    NULL
                );
            } else if (err != ESP_OK && response == NULL) {
                response = node_command_handler_create_response(
                    cmd_id,
                    "ERROR",
                    "handler_error",
                    "Command handler failed",
                    NULL
                );
            }
            
            // Убеждаемся, что cmd_id есть в ответе (если ответ был создан)
            if (response != NULL) {
                cJSON *response_cmd_id = cJSON_GetObjectItem(response, "cmd_id");
                if (!response_cmd_id || !cJSON_IsString(response_cmd_id)) {
                    cJSON_AddStringToObject(response, "cmd_id", cmd_id);
                }
            }
            
            cJSON_Delete(params);
        }
    } else {
        ESP_LOGW(TAG, "Unknown command: %s", cmd);
        response = node_command_handler_create_response(
            cmd_id,
            "ERROR",
            "unknown_command",
            "Command not found",
            NULL
        );
    }

    // Публикация ответа
    if (response) {
        char *json_str = cJSON_PrintUnformatted(response);
        if (json_str) {
            // Публикуем ответ через mqtt_manager
            mqtt_manager_publish_command_response(channel ? channel : "default", json_str);
            free(json_str);
        }
        cJSON_Delete(response);
    }

    cJSON_Delete(json);
}

cJSON *node_command_handler_create_response(
    const char *cmd_id,
    const char *status,
    const char *error_code,
    const char *error_message,
    const cJSON *extra_data
) {
    cJSON *response = cJSON_CreateObject();
    if (!response) {
        return NULL;
    }

    if (cmd_id) {
        cJSON_AddStringToObject(response, "cmd_id", cmd_id);
    }

    if (status) {
        cJSON_AddStringToObject(response, "status", status);
    }

    cJSON_AddNumberToObject(response, "ts", (double)(esp_timer_get_time() / 1000000));

    if (error_code && strcmp(status, "ERROR") == 0) {
        cJSON_AddStringToObject(response, "error_code", error_code);
    }

    if (error_message && strcmp(status, "ERROR") == 0) {
        cJSON_AddStringToObject(response, "error_message", error_message);
    }

    if (extra_data) {
        cJSON_AddItemToObject(response, "data", cJSON_Duplicate(extra_data, 1));
    }

    return response;
}

bool node_command_handler_is_duplicate(const char *cmd_id) {
    if (cmd_id == NULL) {
        return false;
    }

    init_mutexes();

    if (s_command_handler.cache_mutex == NULL) {
        return false;
    }

    uint64_t current_time_ms = esp_timer_get_time() / 1000;

    if (xSemaphoreTake(s_command_handler.cache_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        // Проверяем кеш
        for (size_t i = 0; i < CMD_ID_CACHE_SIZE; i++) {
            if (s_command_handler.cmd_id_cache[i].valid) {
                // Проверяем TTL
                if (current_time_ms - s_command_handler.cmd_id_cache[i].timestamp_ms > CMD_ID_TTL_MS) {
                    s_command_handler.cmd_id_cache[i].valid = false;
                    continue;
                }

                // Проверяем совпадение cmd_id
                if (strcmp(s_command_handler.cmd_id_cache[i].cmd_id, cmd_id) == 0) {
                    xSemaphoreGive(s_command_handler.cache_mutex);
                    return true;
                }
            }
        }

        // Добавляем в кеш
        for (size_t i = 0; i < CMD_ID_CACHE_SIZE; i++) {
            if (!s_command_handler.cmd_id_cache[i].valid) {
                strncpy(s_command_handler.cmd_id_cache[i].cmd_id, cmd_id, 63);
                s_command_handler.cmd_id_cache[i].cmd_id[63] = '\0';
                s_command_handler.cmd_id_cache[i].timestamp_ms = current_time_ms;
                s_command_handler.cmd_id_cache[i].valid = true;
                break;
            }
        }

        xSemaphoreGive(s_command_handler.cache_mutex);
    }

    return false;
}

